"""Cookie vault: filtering, keyring round trip, short-lived RAM copies, fallback file."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="ytdlp-gtk-vault-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_tmp, "data")
RUN = os.path.join(_tmp, "run")             # stands in for $XDG_RUNTIME_DIR (not set globally: the GUI test needs the real one)
os.makedirs(RUN, mode=0o700)
os.environ["YTDLP_GTK_APP_ID"] = "local.ytdlp.gtk.test"

from ytdlp_gtk import vault as vault_mod                                    # noqa: E402

vault_mod._runtime_base = lambda: vault_mod._private_dir(Path(RUN) / "ytdlp-gtk")
from ytdlp_gtk.browsers import count_cookie_lines, filter_cookies, parse_domains   # noqa: E402
from ytdlp_gtk.security import validate_cmd                                  # noqa: E402

JAR = ("# Netscape HTTP Cookie File\n"
       ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tsecret-yt\n"
       "#HttpOnly_.accounts.google.com\tTRUE\t/\tTRUE\t2000000000\tHSID\tsecret-g\n"
       ".bank.example\tTRUE\t/\tTRUE\t2000000000\tsession\tDO-NOT-KEEP\n"
       "notyoutube.com\tFALSE\t/\tFALSE\t0\tx\tDO-NOT-KEEP-2\n")


class Filtering(unittest.TestCase):
    def test_keeps_only_listed_sites_and_subdomains(self):
        kept = filter_cookies(JAR, ["youtube.com", "google.com"])
        self.assertIn("secret-yt", kept)
        self.assertIn("secret-g", kept)
        self.assertNotIn("DO-NOT-KEEP", kept)             # other sites are dropped (also look-alike hosts)
        self.assertEqual(count_cookie_lines(kept), 2)

    def test_parse_domains(self):
        self.assertEqual(parse_domains("YouTube.com, .google.com  vimeo.com"), ["youtube.com", "google.com", "vimeo.com"])
        self.assertEqual(parse_domains("../etc, ;rm, localhost, a b"), [])


class CommandRule(unittest.TestCase):
    BASE = ["yt-dlp", "--cookies", "X", "--", "https://youtu.be/x"]

    def test_cookies_only_from_the_vault(self):
        self.assertTrue(validate_cmd([*self.BASE[:2], "vault:chromium", *self.BASE[3:]]))
        self.assertFalse(validate_cmd([*self.BASE[:2], "/etc/passwd", *self.BASE[3:]]))
        self.assertFalse(validate_cmd([*self.BASE[:2], "vault:../x", *self.BASE[3:]]))

    def test_browser_source_is_a_name_and_optional_absolute_profile(self):
        ok = ["yt-dlp", "--cookies-from-browser", "chromium", "--", "https://youtu.be/x"]
        self.assertTrue(validate_cmd(ok))
        self.assertTrue(validate_cmd([*ok[:2], "chromium:/home/u/snap/chromium/common/chromium/Default", *ok[3:]]))
        for bad in ("chromium:relative/path", "../x", "chromium;rm", "CHROMIUM", "chromium:/a\nb"):
            self.assertFalse(validate_cmd([*ok[:2], bad, *ok[3:]]), bad)


class VaultStorage(unittest.TestCase):
    def setUp(self):
        self.vault = vault_mod.Vault("local.ytdlp.gtk.Test")

    def test_keyring_round_trip_and_ram_copy(self):
        if self.vault.mode() != "keyring":
            self.skipTest("no keyring in this session")
        self.vault.store("testkey", JAR)
        try:
            self.assertEqual(self.vault.load("testkey"), JAR)
            self.assertFalse(list(Path(_tmp, "config").rglob("cookies-testkey*")))     # never a file at rest
            with self.vault.resolve(["yt-dlp", "--cookies", "vault:testkey", "--", "https://x.test/a"]) as cmd:
                path = cmd[2]
                self.assertTrue(path.startswith(RUN))
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
                self.assertEqual(Path(path).read_text(), JAR)
            self.assertFalse(os.path.exists(path))                                       # gone after use
        finally:
            self.vault.forget("testkey")
        self.assertIsNone(self.vault.load("testkey"))

    def test_missing_entry_runs_without_cookies(self):
        with self.vault.resolve(["yt-dlp", "--cookies", "vault:nothing", "--", "https://x.test/a"]) as cmd:
            self.assertEqual(cmd, ["yt-dlp", "--", "https://x.test/a"])

    def test_file_fallback_is_private(self):
        self.vault._mode = "file"
        self.vault.store("fallback", JAR)
        try:
            f = vault_mod.CONFIG_DIR / "cookies-fallback.txt"
            self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
            self.assertEqual(self.vault.load("fallback"), JAR)
        finally:
            self.vault.forget("fallback")
        self.assertFalse((vault_mod.CONFIG_DIR / "cookies-fallback.txt").exists())

    def test_bad_names_are_refused(self):
        for bad in ("../x", "UPPER", "a", "with space", "x" * 20):
            with self.assertRaises(ValueError):
                self.vault.store(bad, "x")

    def test_scratch_folder_must_be_ours(self):
        elsewhere = Path(tempfile.mkdtemp(dir=_tmp))
        link = Path(tempfile.mkdtemp(dir=_tmp)) / "ytdlp-gtk"
        link.symlink_to(elsewhere)                                 # someone pre-created a symlink
        with self.assertRaises(OSError):
            vault_mod._private_dir(link)
        ok = vault_mod._private_dir(Path(tempfile.mkdtemp(dir=_tmp)) / "fresh")
        self.assertEqual(stat.S_IMODE(os.stat(ok).st_mode), 0o700)

    def test_stale_scratch_folders_are_swept(self):
        base = vault_mod._runtime_base()
        stale = base / "99999999"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "cookies-leftover.txt").write_text("x")
        vault_mod.sweep_stale_runtime()
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
