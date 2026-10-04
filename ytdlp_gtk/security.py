"""Input validation. Everything that reaches a command line, a file path or the network passes through here.

Threat model: this is a desktop program run by one user. It never needs (and never asks for) elevated
privileges. The realistic attacks are hostile *data*: a pasted/imported "link" that is really a yt-dlp option
(argument injection -> `--exec`), a playlist or web page that returns crafted URLs, a tampered settings file,
or oversized input meant to exhaust memory.
"""
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .options import EXTRA_ARGS

MAX_URL_LENGTH = 2048
MAX_TEXT_FILE = 2_000_000          # bytes read from an imported URL list
MAX_COOKIE_FILE = 20_000_000       # a real cookies.txt is well under this
MAX_IMAGE = 5_000_000              # a playlist thumbnail
MAX_PLAYLIST_ENTRIES = 1000        # shown and downloaded from one playlist link


def valid_url(text):
    """Return the link if it is a plain http(s) URL, else None.

    Rejects anything starting with '-' (it would be read as an option), whitespace/control characters,
    other schemes (file:, ftp:, javascript:) and absurd lengths."""
    if not isinstance(text, str):
        return None
    url = text.strip()
    if not url or len(url) > MAX_URL_LENGTH or url.startswith("-"):
        return None
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    return url


class _WebOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """urllib would also follow a redirect to ftp:; only http(s) is acceptable here."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if valid_url(newurl) is None:
            raise urllib.error.URLError(f"refusing to follow a redirect to {newurl[:60]!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_WebOnlyRedirects)


def open_web(url, timeout=30):
    """urlopen for http(s) only: the first URL and every redirect target are checked."""
    if valid_url(url) is None:
        raise ValueError("not an http(s) URL")
    # The scheme was checked above and every redirect target is checked by _WebOnlyRedirects.
    return _OPENER.open(url, timeout=timeout)  # nosec B310


def read_limited(path, limit, binary=False):
    """Read at most `limit` bytes from a file; raises ValueError if it is larger."""
    size = os.path.getsize(path)
    if size > limit:
        raise ValueError(f"{Path(path).name} is too large ({size} bytes, limit {limit})")
    with open(path, "rb" if binary else "r", **({} if binary else {"errors": "replace"})) as f:
        return f.read()


def write_private(path, text):
    """Write a file readable only by the owner (created 0600, never briefly world-readable)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


# --- the only options this app ever passes to yt-dlp --------------------------------------------------
VALUE_FLAGS = {"-o", "-f", "--audio-format", "--audio-quality", "--remux-video", "--merge-output-format",
               "--convert-thumbnails", "--sub-langs", "--cookies", "--cookies-from-browser", "--js-runtimes",
               "--progress-template"}
FLAG_ONLY = {"--newline", "--no-playlist", "--yes-playlist", "-x", "--write-thumbnail", "--write-subs",
             "--write-auto-subs", "--embed-subs"}
for _args in EXTRA_ARGS.values():
    for _i, _tok in enumerate(_args):
        if _tok.startswith("-"):
            if _i + 1 < len(_args) and not _args[_i + 1].startswith("-"):
                VALUE_FLAGS.add(_tok)
            else:
                FLAG_ONLY.add(_tok)
# yt-dlp options that run programs or load code; never allowed even if someone edits a saved queue
DANGEROUS = {"--exec", "--exec-before-download", "--external-downloader", "--external-downloader-args",
             "--downloader", "--netrc-cmd", "--use-postprocessor", "--plugin-dirs", "--config-locations",
             "--config-location", "--alias", "--ffmpeg-location", "--update", "-U", "--update-to"}


def validate_cmd(cmd):
    """True only for a command of the exact shape build_cmd() produces: known options, then `--`, one URL.

    argv[0] is ignored (the caller substitutes the real yt-dlp path)."""
    if not isinstance(cmd, list) or len(cmd) < 3 or not all(isinstance(a, str) for a in cmd):
        return False
    i, n = 1, len(cmd)
    while i < n:
        tok = cmd[i]
        if tok == "--":
            return n - i == 2 and valid_url(cmd[i + 1]) is not None
        if tok in DANGEROUS:
            return False
        if tok in VALUE_FLAGS:
            if i + 1 >= n:
                return False
            if tok == "--cookies" and not re.fullmatch(r"vault:[a-z]{2,10}", cmd[i + 1]):
                return False             # a cookie file only ever comes from the vault, never from a path in a command
            if tok == "--cookies-from-browser" and not re.fullmatch(r"[a-z]{2,10}(:/[^\x00\r\n]*)?", cmd[i + 1]):
                return False             # `browser` or `browser:/absolute/profile/path`, nothing else
            i += 2
        elif tok in FLAG_ONLY:
            i += 1
        else:
            return False
    return False
