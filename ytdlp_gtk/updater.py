"""Keeping yt-dlp current without root: a private, signature- and hash-verified copy in ~/.local/share/ytdlp-gtk/.

Only https://github.com/yt-dlp/yt-dlp/releases is contacted. For a release the SHA2-256SUMS file and its GPG
signature are fetched; the signature must verify (with `gpgv`) against yt-dlp's release key, which ships with this
app and is pinned by fingerprint. Only then are the hashes trusted; the download must match the hash for `yt-dlp`,
stay under a size cap and report the expected version before it replaces anything. Everything fails closed: no
`gpgv`, no valid signature, no update.

Command line (used by the packaging scripts):  python3 -m ytdlp_gtk.updater INSTALL_PATH
"""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .security import open_web
from .tools import UPDATED_YTDLP, child_env

RELEASES = "https://github.com/yt-dlp/yt-dlp/releases"
TAG_RE = re.compile(r"\d{4}\.\d{2}\.\d{2}(?:\.\d+)?")
SHA_RE = re.compile(r"[0-9a-f]{64}")
MAX_BINARY = 90_000_000
KEYRING = Path(__file__).resolve().parent / "keys" / "yt-dlp-release.gpg"
SIGNING_FINGERPRINT = "AC0CBBE6848D6A873464AF4E57CF65933B5A7581"      # Simon Sawicki (yt-dlp signing key)


def release_asset():
    """The release file to use: the self-contained build (bundles the cookie-decryption libraries etc., so it behaves
    the same from source, deb or AppImage); the plain zipapp where no such build exists."""
    return {"x86_64": "yt-dlp_linux", "amd64": "yt-dlp_linux", "aarch64": "yt-dlp_linux_aarch64",
            "arm64": "yt-dlp_linux_aarch64"}.get(platform.machine().lower(), "yt-dlp")


class SignatureError(ValueError):
    """The release could not be proven authentic."""


def verify_signature(data, sig, keyring=KEYRING, fingerprint=SIGNING_FINGERPRINT):
    """Check a detached GPG signature with gpgv against one pinned key. Returns gpgv's status text."""
    gpgv = shutil.which("gpgv")
    if not gpgv:
        raise SignatureError("gpgv is not installed, so the download cannot be verified (sudo apt install gpgv)")
    with tempfile.TemporaryDirectory(prefix="ytdlp-gtk-gpg-") as tmp:
        data_path, sig_path = os.path.join(tmp, "data"), os.path.join(tmp, "data.sig")
        Path(data_path).write_bytes(data)
        Path(sig_path).write_bytes(sig)
        env = {**child_env(), "GNUPGHOME": tmp, "LC_ALL": "C"}
        out = subprocess.run([gpgv, "--status-fd", "1", "--keyring", os.fspath(keyring), sig_path, data_path],
                             capture_output=True, text=True, timeout=30, env=env)
    status = out.stdout
    bad = ("BADSIG", "ERRSIG", "EXPSIG", "EXPKEYSIG", "REVKEYSIG", "NO_PUBKEY")
    if out.returncode != 0 or any(f"[GNUPG:] {word}" in status for word in bad):
        raise SignatureError("the release signature is not valid")
    for line in status.splitlines():
        parts = line.split()
        # [GNUPG:] VALIDSIG <signing key fpr> <date> <ts> <exp> <ver> <res> <pk-algo> <hash-algo> <class> <primary fpr>
        if parts[:2] == ["[GNUPG:]", "VALIDSIG"] and parts[-1].upper() == fingerprint.upper():
            return status
    raise SignatureError("the release was signed by a key other than yt-dlp's release key")


def installed_version(path):
    """The version a yt-dlp executable reports ('' if it cannot be run)."""
    try:
        out = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=30, env=child_env())
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def version_key(version):
    """Sortable form of a yt-dlp version such as 2026.08.19 or 2026.08.19.123456."""
    if not TAG_RE.fullmatch(version or ""):
        return ()
    return tuple(int(part) for part in version.split("."))


def _open(url, timeout=30):
    if not url.startswith("https://"):
        raise ValueError("only https is allowed")
    resp = open_web(url, timeout=timeout)
    if not resp.geturl().startswith("https://"):
        resp.close()
        raise ValueError("redirected to a non-https address")
    return resp


def latest_release():
    """(tag, sha256 of this platform's yt-dlp file) of the newest release, signature of the checksums verified."""
    with _open(f"{RELEASES}/latest") as resp:                # GitHub redirects this to .../releases/tag/<tag>
        final = resp.geturl()
    match = re.search(r"/releases/tag/([^/?#]+)", final)
    tag = match[1] if match else ""
    if not TAG_RE.fullmatch(tag):
        raise ValueError(f"unexpected release name {tag!r}")
    with _open(f"{RELEASES}/download/{tag}/SHA2-256SUMS") as resp:
        sums = resp.read(200_000)
    with _open(f"{RELEASES}/download/{tag}/SHA2-256SUMS.sig") as resp:
        sig = resp.read(20_000)
    verify_signature(sums, sig)                                # fails closed
    for line in sums.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == release_asset() and SHA_RE.fullmatch(parts[0]):
            return tag, parts[0]
    raise ValueError(f"the release has no checksum for {release_asset()}")


def download_release(tag, sha256, dest=UPDATED_YTDLP, progress=None):
    """Download, verify and install yt-dlp `tag` at `dest` (atomic replace). Returns the installed version."""
    if not TAG_RE.fullmatch(tag) or not SHA_RE.fullmatch(sha256):
        raise ValueError("bad release data")
    dest = os.fspath(dest)
    fd, tmp = tempfile.mkstemp(prefix=".yt-dlp-", dir=os.path.dirname(dest))      # mkstemp: created 0600
    try:
        digest, total = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as out, _open(f"{RELEASES}/download/{tag}/{release_asset()}", timeout=120) as resp:
            expected = int(resp.headers.get("Content-Length") or 0)
            while chunk := resp.read(65536):
                total += len(chunk)
                if total > MAX_BINARY:
                    raise ValueError("download is larger than expected")
                digest.update(chunk)
                out.write(chunk)
                if progress and expected:
                    progress(min(1.0, total / expected))
        if digest.hexdigest() != sha256:
            raise ValueError("checksum mismatch: the download was not what GitHub published")
        os.chmod(tmp, 0o700)                  # runnable by you only
        version = installed_version(tmp)
        if version != tag:
            raise ValueError(f"downloaded file reports version {version!r}, expected {tag!r}")
        os.replace(tmp, dest)
        return version
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv):
    """Download, verify and install the newest yt-dlp at argv[1] (used when building packages)."""
    if len(argv) != 2:
        print("usage: python3 -m ytdlp_gtk.updater INSTALL_PATH")
        return 2
    tag, sha = latest_release()
    print(f"release {tag}: signature OK")
    print(f"installed yt-dlp {download_release(tag, sha, argv[1])} at {argv[1]} (checksum OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
