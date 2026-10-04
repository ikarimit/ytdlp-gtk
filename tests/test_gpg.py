"""Real gpg/gpgv with throw-away keys: good signatures pass, everything else fails closed."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="ytdlp-gtk-gpg-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_tmp, "data")
os.environ["YTDLP_GTK_APP_ID"] = "local.ytdlp.gtk.test"

from ytdlp_gtk import updater   # noqa: E402

DATA = b"abc  yt-dlp\n"


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "needs gpg and gpgv")
class GpgVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(dir=_tmp)
        os.chmod(cls.home, 0o700)
        cls.env = {**os.environ, "GNUPGHOME": cls.home}
        cls.keys = {}
        for name in ("release", "stranger"):
            subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-generate-key", f"{name} <{name}@test>",
                            "ed25519", "sign", "never"], env=cls.env, capture_output=True, check=True)
            colons = subprocess.run(["gpg", "--list-keys", "--with-colons", f"{name}@test"], env=cls.env,
                                    capture_output=True, text=True).stdout
            fpr = next(line.split(":")[9] for line in colons.splitlines() if line.startswith("fpr"))
            ring = os.path.join(cls.home, f"{name}.gpg")
            Path(ring).write_bytes(subprocess.run(["gpg", "--export", f"{name}@test"], env=cls.env,
                                                  capture_output=True).stdout)
            cls.keys[name] = (fpr, ring)

    def sign(self, name, data):
        path = os.path.join(self.home, "data")
        Path(path).write_bytes(data)
        subprocess.run(["gpg", "--batch", "--yes", "--local-user", f"{name}@test", "--detach-sign", "-o",
                        path + ".sig", path], env=self.env, capture_output=True, check=True)
        return Path(path + ".sig").read_bytes()

    def test_good_signature_passes(self):
        fpr, ring = self.keys["release"]
        self.assertIn("VALIDSIG", updater.verify_signature(DATA, self.sign("release", DATA), ring, fpr))

    def test_tampered_data_fails(self):
        fpr, ring = self.keys["release"]
        with self.assertRaises(updater.SignatureError):
            updater.verify_signature(b"evil  yt-dlp\n", self.sign("release", DATA), ring, fpr)

    def test_signature_by_another_key_fails(self):
        fpr, ring = self.keys["release"]
        with self.assertRaises(updater.SignatureError):                     # that key is not in the pinned keyring
            updater.verify_signature(DATA, self.sign("stranger", DATA), ring, fpr)

    def test_right_keyring_but_wrong_pinned_fingerprint_fails(self):
        _fpr, ring = self.keys["release"]
        with self.assertRaises(updater.SignatureError):
            updater.verify_signature(DATA, self.sign("release", DATA), ring, self.keys["stranger"][0])

    def test_garbage_signature_fails(self):
        fpr, ring = self.keys["release"]
        with self.assertRaises(updater.SignatureError):
            updater.verify_signature(b"abc", b"not a signature", ring, fpr)

    def test_bundled_key_is_the_pinned_one(self):
        out = subprocess.run(["gpg", "--show-keys", "--with-colons", str(updater.KEYRING)], capture_output=True,
                             text=True, env=self.env).stdout
        fprs = [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr")]
        self.assertEqual(fprs[0], updater.SIGNING_FINGERPRINT)


class LiveRelease(unittest.TestCase):
    """The real yt-dlp release must verify with the bundled key (skipped when offline)."""

    def test_latest_release_signature(self):
        try:
            tag, sha = updater.latest_release()
        except updater.SignatureError:
            raise
        except Exception as e:                                    # no network
            self.skipTest(f"offline: {e}")
        self.assertRegex(tag, r"\d{4}\.\d{2}\.\d{2}")
        self.assertRegex(sha, r"[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
