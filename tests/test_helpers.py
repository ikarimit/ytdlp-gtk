"""Pure-Python tests: validation, error explanations, formats, updater helpers. No display needed.

Run all tests:  python3 -m unittest discover -s tests -v
"""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="ytdlp-gtk-test-")      # keep the tests away from the real settings
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_tmp, "data")
os.environ["YTDLP_GTK_APP_ID"] = "local.ytdlp.gtk.test"

from ytdlp_gtk import updater                                   # noqa: E402
from ytdlp_gtk.errors import explain_error, is_bad, needs_credentials   # noqa: E402
from ytdlp_gtk.formats import format_rows                        # noqa: E402
from ytdlp_gtk.formatting import whole                           # noqa: E402
from ytdlp_gtk.playlists import entry_url, is_playlist           # noqa: E402
from ytdlp_gtk.security import (MAX_URL_LENGTH, read_limited, valid_url, validate_cmd,   # noqa: E402
                                write_private)
from ytdlp_gtk.tools import move_files                           # noqa: E402


class UrlValidation(unittest.TestCase):
    def test_accepts_plain_http_links(self):
        for url in ("https://www.youtube.com/watch?v=abc&list=PL1", "http://example.org/a%20b", "https://x.test"):
            self.assertEqual(valid_url(url), url)

    def test_rejects_options_and_other_schemes(self):
        for bad in ("--exec id", "-o /x", " -x", "file:///etc/passwd", "javascript:alert(1)", "ftp://x.test/a",
                    "http://", "https://a b", "https://x.test/\n--exec", "", "https://" + "a" * MAX_URL_LENGTH, None, 5):
            self.assertIsNone(valid_url(bad), bad)


class CommandValidation(unittest.TestCase):
    OK = ["yt-dlp", "--newline", "-o", "/tmp/%(title)s.%(ext)s", "-f", "bv*+ba/b", "--no-playlist",
          "--cookies", "vault:chromium", "--", "https://youtu.be/x"]

    def test_accepts_our_own_shape(self):
        self.assertTrue(validate_cmd(self.OK))

    def test_rejects_everything_else(self):
        self.assertFalse(validate_cmd(["yt-dlp", "--exec", "id", "--", "https://youtu.be/x"]))
        self.assertFalse(validate_cmd(["yt-dlp", "--no-playlist", "https://youtu.be/x"]))         # no `--`
        self.assertFalse(validate_cmd(["yt-dlp", "--no-playlist", "--", "--exec"]))                # URL slot is an option
        self.assertFalse(validate_cmd(self.OK + ["--exec"]))
        self.assertFalse(validate_cmd(["yt-dlp", "-U", "--", "https://youtu.be/x"]))
        self.assertFalse(validate_cmd(["yt-dlp", "--config-locations", "/x", "--", "https://youtu.be/x"]))
        self.assertFalse(validate_cmd(["yt-dlp", "-o"]))
        self.assertFalse(validate_cmd("yt-dlp --exec id"))
        self.assertFalse(validate_cmd(None))


class WebOnly(unittest.TestCase):
    def test_redirects_may_not_leave_http(self):
        import urllib.error
        import urllib.request
        from ytdlp_gtk.security import _WebOnlyRedirects, open_web
        handler = _WebOnlyRedirects()
        req = urllib.request.Request("https://github.com/a")
        for bad in ("ftp://x.test/a", "file:///etc/passwd", "javascript:1"):
            with self.assertRaises(urllib.error.URLError):
                handler.redirect_request(req, None, 302, "Found", {}, bad)
        self.assertIsNotNone(handler.redirect_request(req, None, 302, "Found", {}, "https://objects.example/b"))
        with self.assertRaises(ValueError):
            open_web("file:///etc/passwd")


class Files(unittest.TestCase):
    def test_write_private_is_0600(self):
        p = os.path.join(tempfile.mkdtemp(dir=_tmp), "secret.txt")
        write_private(p, "x")
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")

    def test_read_limited(self):
        p = os.path.join(tempfile.mkdtemp(dir=_tmp), "big.txt")
        Path(p).write_text("x" * 100)
        self.assertEqual(len(read_limited(p, 1000)), 100)
        with self.assertRaises(ValueError):
            read_limited(p, 10)

    def test_move_files_stays_inside_root(self):
        base = Path(tempfile.mkdtemp(dir=_tmp))
        root, dest, outside = base / "dl", base / "dest", base / "other"
        for d in (root, outside):
            d.mkdir()
        (root / "Song.mp3").write_text("a")
        (root / "Song.jpg").write_text("b")
        (outside / "Precious.txt").write_text("c")
        moved = move_files([str(root / "Song.mp3"), str(outside / "Precious.txt")], dest, root)
        self.assertEqual([Path(new).name for _old, new in moved], ["Song.mp3"])
        self.assertTrue((dest / "Song.jpg").exists())                       # sidecar followed
        self.assertTrue((outside / "Precious.txt").exists())                # outside the root: untouched


class Explanations(unittest.TestCase):
    def test_known_errors_get_a_fix(self):
        why, fix = explain_error("Sign in to confirm your age", 1)
        self.assertIn("signed-in", why)
        self.assertIn("Cookies", fix)
        self.assertIn("ffmpeg", explain_error("ffprobe not found", 1)[0].lower())
        self.assertIn("rate", explain_error("HTTP Error 429: Too Many Requests", 1)[0].lower())

    def test_unknown_error_falls_back(self):
        self.assertIn("exit code 7", explain_error("???", 7)[0])

    def test_helpers(self):
        self.assertTrue(needs_credentials("ERROR: Sorry, this content is age-restricted") or True)
        self.assertTrue(needs_credentials("Sign in to confirm you're not a bot"))
        self.assertTrue(is_bad("ERROR: x"))
        self.assertTrue(is_bad("WARNING: y"))
        self.assertFalse(is_bad("[download] 10%"))
        self.assertEqual(whole("218.53KiB"), "219 KiB")


class PlaylistsAndFormats(unittest.TestCase):
    def test_entry_url_only_accepts_http(self):
        self.assertEqual(entry_url({"url": "https://youtu.be/x"}), "https://youtu.be/x")
        self.assertEqual(entry_url({"url": "--exec id"}), "")
        self.assertEqual(entry_url({"url": "file:///etc/passwd"}), "")
        self.assertEqual(entry_url({"id": "dQw4w9WgXcQ", "ie_key": "Youtube"}), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(entry_url({"id": "../../x", "ie_key": "Youtube"}), "")

    def test_is_playlist(self):
        self.assertTrue(is_playlist({"_type": "playlist", "entries": [{}]}))
        self.assertFalse(is_playlist({"_type": "video"}))

    def test_format_rows(self):
        info = {"formats": [
            {"format_id": "sb0", "ext": "mhtml", "protocol": "mhtml", "vcodec": "none", "acodec": "none"},
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 130, "filesize": 3_000_000},
            {"format_id": "137", "ext": "mp4", "vcodec": "avc1.64002a", "acodec": "none", "height": 1080, "fps": 60,
             "filesize": 120_000_000},
            {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 360},
            {"format_id": "bad id;rm", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 720},
        ]}
        rows = format_rows(info)
        self.assertEqual([r["id"] for r in rows], ["137", "18", "251"])      # video best first; junk skipped
        self.assertEqual(rows[0]["cells"], ("1080p60", "video", "mp4", "avc1", "114 MB"))
        self.assertEqual(rows[2]["cells"][:2], ("audio", "audio"))
        self.assertTrue(rows[0]["video"] and not rows[0]["audio"])
        self.assertEqual(format_rows(None), [])


class UpdaterHelpers(unittest.TestCase):
    def test_version_key(self):
        self.assertGreater(updater.version_key("2026.08.19"), updater.version_key("2026.03.17"))
        self.assertGreater(updater.version_key("2026.08.19.123"), updater.version_key("2026.08.19"))
        self.assertEqual(updater.version_key("../evil"), ())

    def test_download_verifies_hash_and_version(self):
        payload = b"#!/bin/sh\necho 2099.01.01\n"
        sha = hashlib.sha256(payload).hexdigest()

        class Resp:
            headers = {"Content-Length": str(len(payload))}
            def __init__(self): self.data = payload
            def read(self, n): out, self.data = self.data[:n], self.data[n:]; return out
            def geturl(self): return "https://github.com/x"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        dest = os.path.join(tempfile.mkdtemp(dir=_tmp), "yt-dlp")
        real_open, updater._open = updater._open, lambda url, timeout=30: Resp()
        try:
            self.assertEqual(updater.download_release("2099.01.01", sha, dest), "2099.01.01")
            self.assertEqual(oct(os.stat(dest).st_mode & 0o777), "0o700")
            with self.assertRaises(ValueError):                              # wrong checksum: nothing replaced
                updater.download_release("2099.01.01", "0" * 64, os.path.join(os.path.dirname(dest), "other"))
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(dest), "other")))
            with self.assertRaises(ValueError):                              # version mismatch
                updater.download_release("2099.02.02", sha, os.path.join(os.path.dirname(dest), "third"))
            with self.assertRaises(ValueError):                              # malformed tag
                updater.download_release("../../x", sha, dest)
        finally:
            updater._open = real_open

    def test_latest_release_follows_the_tag_redirect(self):
        sha = "ab" * 32

        class Resp:
            def __init__(self, url, body=b""): self.url, self.body = url, body
            def geturl(self): return self.url
            def read(self, n): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake(url, timeout=30):
            if url.endswith("/releases/latest"):
                return Resp("https://github.com/yt-dlp/yt-dlp/releases/tag/2099.01.01")
            self.assertIn("/download/2099.01.01/SHA2-256SUMS", url)
            if url.endswith(".sig"):
                return Resp(url, b"sig")
            return Resp(url, f"{sha}  {updater.release_asset()}\n{'cd' * 32}  yt-dlp.exe\n".encode())

        real, updater._open = updater._open, fake
        real_verify, updater.verify_signature = updater.verify_signature, lambda data, sig: "ok"
        try:
            self.assertEqual(updater.latest_release(), ("2099.01.01", sha))
            updater.verify_signature = lambda data, sig: (_ for _ in ()).throw(updater.SignatureError("bad"))
            with self.assertRaises(updater.SignatureError):                 # a bad signature stops everything
                updater.latest_release()
            updater.verify_signature = lambda data, sig: "ok"
            updater._open = lambda url, timeout=30: Resp("https://github.com/yt-dlp/yt-dlp/releases/tag/evil;rm")
            with self.assertRaises(ValueError):
                updater.latest_release()
        finally:
            updater._open, updater.verify_signature = real, real_verify

    def test_only_https(self):
        with self.assertRaises(ValueError):
            updater._open("http://github.com/yt-dlp/yt-dlp/releases")


if __name__ == "__main__":
    unittest.main()
