"""Window mixin: cookie setup.

Browser cookies are read live from the browser each time a download needs them: YouTube rotates account cookies
while a browser is open, so any saved copy goes stale (the old "cookies stop working" problem), and nothing
sensitive is left on disk. Only an imported cookies.txt is stored, in the system keyring (vault.py).
"""
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gio, Gtk  # noqa: E402

from .browsers import (DEFAULT_DOMAINS, auto_profile, browser_location, cookie_error_hint, count_cookie_lines,
                       filter_cookies, parse_domains, profile_arg, where_label)
from .config import CONFIG_DIR, log
from .options import BROWSERS, TEST_URL
from .security import MAX_COOKIE_FILE, read_limited
from .tools import child_env, ytdlp
from .vault import sweep_stale_runtime, temp_file



class CookieMixin:
    """Methods of the main window (cookies)."""

    def cookie_args(self):
        """Browsers: read live (`--cookies-from-browser`). cookies.txt: `--cookies vault:file` is a placeholder the
        vault turns into a short-lived private RAM file at run time."""
        key = self.sel.get("cookies", "none")
        if key == "none":
            return []
        if key == "file":
            return ["--cookies", "vault:file"] if "file" in self.vault_keys else []
        return ["--cookies-from-browser", self.browser_spec(key)]

    def browser_spec(self, key):
        """`chromium` or `chromium:/path/to/profile` (snap/Flatpak/located profiles need the explicit path)."""
        spec = self._spec_cache.get(key)
        if spec is None:
            paths = next(p for k, _n, p in BROWSERS if k == key)
            profile = self.cookie_profiles.get(key, "")
            if profile and Path(profile).expanduser().is_dir():
                profile = str(Path(profile).expanduser()) if key == "firefox" else profile_arg(key, profile)
            else:
                profile = auto_profile(key, paths)
            spec = self._spec_cache[key] = f"{key}:{profile}" if profile else key
        return spec

    def storage_note(self):
        where = ("saved encrypted in your system keyring and unpacked into memory only while a download runs"
                 if self.vault.mode() == "keyring" else
                 "saved in a private file (no system keyring was found; only you can read it) in ~/.config/ytdlp-gtk/")
        return ("Browser cookies are read straight from the browser each time a download needs them, so they never go "
                "stale (YouTube rotates them) and nothing is copied. An imported cookies.txt is " + where + ".")

    def refresh_vault_keys(self):
        """At start: sweep crash leftovers, move old cookie files into the keyring, learn what is stored."""
        sweep_stale_runtime()
        for tmp in CONFIG_DIR.glob(".cookies-*.tmp"):            # export scratch files of earlier versions
            self.vault.shred_file(tmp)
        moved = self.migrate_cookie_files()
        self.vault_keys = {"file"} if self.vault.has("file") else set()
        if moved:
            self.toasts.add_toast(Adw.Toast(title="Old saved cookie copies were removed; browser cookies are now read "
                                                  "live (they never go stale)", timeout=8))

    def migrate_cookie_files(self):
        """Cookie files from earlier versions: browser copies were stale snapshots, so they are shredded; an imported
        cookies.txt (cookies-file.txt) moves into the keyring (verified first), or stays as the private fallback file."""
        moved = 0
        for path in sorted(CONFIG_DIR.glob("cookies-*.txt")):
            key = path.stem.removeprefix("cookies-")
            try:
                if key != "file":
                    self.vault.shred_file(path)
                    moved += 1
                    log.info("Removed stale cookie copy %s (browser cookies are read live now)", path.name)
                elif self.vault.mode() == "keyring":
                    text = read_limited(path, MAX_COOKIE_FILE)
                    self.vault.store("file", text)
                    if self.vault.load("file") != text:
                        raise RuntimeError("the keyring did not return what was stored")
                    self.vault.shred_file(path)
                    moved += 1
                    log.info("Moved %s into the keyring", path.name)
            except Exception:
                log.exception("Could not process %s; it stays where it is", path.name)
        return moved

    def set_cookie_choice(self, key):
        """Select a cookies radio without re-opening the setup dialog."""
        self._cookie_quiet = True
        try:
            btn = self.buttons.get(("cookies", key))
            if btn:
                btn.set_active(True)
            self.sel["cookies"] = key
        finally:
            self._cookie_quiet = False

    def forget_cookies(self, *_):
        key = self.sel["cookies"]
        if key == "none":
            return
        if key == "file":
            self.vault.forget("file")
            self.vault_keys.discard("file")
        self.set_cookie_choice("none")
        self.cookie_prev = "none"
        self.toasts.add_toast(Adw.Toast(title="Cookies are no longer used" + (" (the imported file was deleted)"
                                                                               if key == "file" else ""), timeout=4))
        self.save_settings()
        self.refresh_summary()

    def show_cookie_setup(self, preselect=None, reason=None, first=False):
        if self.cookie_dialog is not None:
            return
        self.cookies_asked = True
        self.save_settings()
        self._cookie_ok = False
        found = {k: browser_location(k, paths) for k, _n, paths in BROWSERS}
        keys = [k for k, _n, _p in BROWSERS if found[k]] + ["file"]
        choice = {"key": preselect if preselect in keys else keys[0], "file": ""}

        dlg = self.cookie_dialog = Adw.Dialog(title="Set up cookies", content_width=500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=18,
                      margin_start=18, margin_end=18)
        intro = ("Some videos (age-restricted, private, members-only, or behind YouTube's bot check) only play "
                 "when you're signed in. Pick the browser you're signed in with. " + self.storage_note())
        if first:
            intro = "First-time setup.\n\n" + intro
        box.append(Gtk.Label(label=intro, wrap=True, xalign=0))
        if reason:
            box.append(Gtk.Label(label=reason, wrap=True, xalign=0, css_classes=["error"]))
        sites = Adw.EntryRow(title="Keep cookies only for these sites (separate with commas)",
                             text=", ".join(self.cookie_domains or DEFAULT_DOMAINS))
        sites.set_tooltip_text("Cookies of every other site are dropped before the cookies.txt is stored. "
                               "Add sites you sign in to, for example vimeo.com.")
        sites_group = Adw.PreferencesGroup()
        sites_group.add(sites)
        go = Gtk.Button(label="Test and use", css_classes=["suggested-action"])

        def picked(key):
            choice["key"] = key
            sites_group.set_visible(key == "file")
            go.set_label("Import" if key == "file" else "Test and use")

        group = Adw.PreferencesGroup(
            title="Which browser are you signed in with?",
            description=("Only browsers found on this computer are listed. Using another one? "
                         "Export a cookies.txt file from it and import that file here."))
        first_chk = None
        for key, name, paths in [b for b in BROWSERS if found[b[0]]] + [("file", "Import a cookies.txt file", [])]:
            sub = ("Already imported; importing again replaces it" if key in self.vault_keys
                   else ("Found on this computer" + (f" ({where_label(found[key])})" if where_label(found[key]) else ""))
                   if found.get(key)
                   else "" if key == "file" else "Not found; use the folder button if it's installed elsewhere")
            row = Adw.ActionRow(title=name, subtitle=sub)
            chk = Gtk.CheckButton()
            if first_chk is None:
                first_chk = chk
            else:
                chk.set_group(first_chk)
            chk.set_active(key == choice["key"])
            chk.connect("toggled", lambda c, k=key: c.get_active() and picked(k))
            row.add_prefix(chk)
            row.set_activatable_widget(chk)
            pick = Gtk.Button(icon_name="document-open-symbolic" if key == "file" else "folder-open-symbolic",
                              valign=Gtk.Align.CENTER, css_classes=["flat"],
                              tooltip_text="Choose the cookies.txt file" if key == "file"
                              else "Locate this browser's profile folder")
            pick.connect("clicked", self._cookie_pick, key, row, chk, choice, paths)
            row.add_suffix(pick)
            group.add(row)
        box.append(group)
        box.append(sites_group)
        picked(choice["key"])
        status = Gtk.Label(wrap=True, xalign=0, visible=False)
        spinner = Gtk.Spinner(visible=False, halign=Gtk.Align.START)
        box.append(status)
        box.append(spinner)
        skip = Gtk.Button(label="Skip", css_classes=["flat"], tooltip_text="Set this up later from the Options tab")
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        buttons.append(skip)
        buttons.append(go)
        box.append(buttons)
        skip.connect("clicked", lambda *_: dlg.close())
        go.connect("clicked", lambda *_: self._cookie_import(dlg, choice, sites, status, spinner, go))
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(Gtk.ScrolledWindow(child=box, propagate_natural_height=True,
                                            hscrollbar_policy=Gtk.PolicyType.NEVER, max_content_height=640))
        dlg.set_child(view)
        dlg.connect("closed", self._cookie_closed)
        dlg.present(self)

    def _cookie_pick(self, _btn, key, row, chk, choice, paths):
        if key == "file":
            fd = Gtk.FileDialog(title="Choose cookies.txt")

            def done(d, res):
                try:
                    path = d.open_finish(res).get_path()
                except GLib.Error:
                    return
                choice["file"] = path
                row.set_subtitle(path)
                chk.set_active(True)

            fd.open(self, None, done)
            return
        fd = Gtk.FileDialog(title="Locate the browser profile folder")
        start = next((Path(p).expanduser() for p in paths if Path(p).expanduser().exists()), Path.home())
        fd.set_initial_folder(Gio.File.new_for_path(str(start)))

        def done_folder(d, res):
            try:
                path = d.select_folder_finish(res).get_path()
            except GLib.Error:
                return
            self.cookie_profiles[key] = path
            self._spec_cache.pop(key, None)
            row.set_subtitle(f"Profile: {path}")
            chk.set_active(True)

        fd.select_folder(self, None, done_folder)

    def _cookie_import(self, dlg, choice, sites, status, spinner, go):
        key = choice["key"]
        status.remove_css_class("error")

        def fail(message):
            status.set_label(message)
            status.add_css_class("error")
            status.set_visible(True)

        domains = parse_domains(sites.get_text()) if key == "file" else []
        if key == "file":
            if not domains:
                return fail("List at least one site (for example youtube.com).")
            if not choice["file"]:
                return fail("Choose a cookies.txt file first (the file button on its row).")
            self.cookie_domains = domains
        go.set_sensitive(False)
        spinner.set_visible(True)
        spinner.start()
        status.set_label("Checking… this can take a few seconds.")
        status.set_visible(True)
        src = choice["file"]

        def work():
            ok, msg, count = self.do_cookie_import(key, src, domains)
            GLib.idle_add(self._cookie_result, dlg, key, ok, msg, count, status, spinner, go)

        threading.Thread(target=work, daemon=True, name="cookies").start()

    def do_cookie_import(self, key, src, domains):
        """Returns (ok, message, cookie_count). A browser is only *tested* (cookies are read live later, nothing is
        kept); a cookies.txt is filtered and stored in the vault. Never logs cookie contents; scratch is RAM-only."""
        try:
            if key == "file":
                kept = filter_cookies(read_limited(src, MAX_COOKIE_FILE), domains)
                count = count_cookie_lines(kept)
                if not count:
                    return False, ("That doesn't look like a cookies.txt file, or it has no cookies for "
                                   + ", ".join(domains) + "."), 0
                self.vault.store("file", kept)
                return True, "", count
            self._spec_cache.pop(key, None)
            spec = self.browser_spec(key)
            with temp_file("check-") as tmp:             # private, in RAM, removed when this block ends
                cmd = [ytdlp(), "--cookies-from-browser", spec, "--cookies", tmp, "--skip-download",
                       "--simulate", "--no-warnings", "--no-playlist", "--", TEST_URL]
                log.info("Cookie check: reading from %s", spec)
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=150, env=child_env())
                text = read_limited(tmp, MAX_COOKIE_FILE)
            if not count_cookie_lines(text):
                log.error("Cookie check failed (%s): %s", r.returncode, r.stderr.strip()[-500:])
                return False, cookie_error_hint(r.stderr), 0
            signed_in = count_cookie_lines(filter_cookies(text, DEFAULT_DOMAINS))
            if not signed_in:
                return False, "That browser has no YouTube or Google cookies: sign in to YouTube in it first.", 0
            return True, "", signed_in
        except Exception as e:
            log.exception("Cookie check crashed")
            return False, f"That did not work: {e}", 0

    def _cookie_result(self, dlg, key, ok, msg, count, status, spinner, go):
        spinner.stop()
        spinner.set_visible(False)
        go.set_sensitive(True)
        if not ok:
            status.set_label(msg)
            status.add_css_class("error")
            return False
        self._cookie_ok = True
        if key == "file":
            self.vault_keys.add("file")
        self.set_cookie_choice(key)
        self.cookie_prev = key
        name = next((n for k, n, _p in BROWSERS if k == key), "cookies.txt")
        if key == "file":
            where = "the system keyring" if self.vault.mode() == "keyring" else "a private file"
            title = f"Saved {count} cookies from your cookies.txt in {where}"
        else:
            title = f"{name} cookies work ({count} for YouTube and Google); they are read live for every download"
        self.toasts.add_toast(Adw.Toast(title=title, timeout=6))
        self.save_settings()
        dlg.close()
        for u in [u for u, v in self.cache.items() if v is None]:     # retry links that needed sign-in
            del self.cache[u]
        self.cred_prompted.clear()
        self.scan_urls()
        self.refresh_summary()
        return False

    def _cookie_closed(self, _dlg):
        self.cookie_dialog = None
        if not self._cookie_ok and self.sel["cookies"] != self.cookie_prev:   # skipped: undo the radio
            self.set_cookie_choice(self.cookie_prev)
            self.refresh_summary()
