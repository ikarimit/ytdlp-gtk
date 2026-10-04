"""Window mixin: the yt-dlp updater (dialog, background check, install)."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .config import log
from .tools import UPDATED_YTDLP, refresh_ytdlp, ytdlp
from .updater import download_release, installed_version, latest_release, version_key

CHECK_EVERY = 24 * 3600          # background check at most once a day


class UpdateMixin:
    """Methods of the main window (yt-dlp updates)."""

    def check_updates_quietly(self):
        """At start-up: if a day has passed, look for a newer yt-dlp and offer it with a toast."""
        if time.time() - self.last_update_check < CHECK_EVERY:
            return False

        def work():
            try:
                tag, sha = latest_release()
            except Exception as e:
                log.info("Update check failed: %s", e)
                return
            have = installed_version(ytdlp())
            GLib.idle_add(self._update_checked_quietly, tag, have)

        threading.Thread(target=work, daemon=True, name="update-check").start()
        return False

    def _update_checked_quietly(self, tag, have):
        self.last_update_check = time.time()
        self.save_settings()
        if version_key(tag) > version_key(have):
            toast = Adw.Toast(title=f"yt-dlp {tag} is available (you have {have or 'none'})",
                              button_label="Update", timeout=0)
            toast.connect("button-clicked", lambda *_: self.show_update_dialog())
            self.toasts.add_toast(toast)
        return False

    def show_update_dialog(self, *_):
        if self.update_dialog is not None:
            return
        dlg = self.update_dialog = Adw.Dialog(title="yt-dlp updates", content_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12, margin_bottom=18,
                      margin_start=18, margin_end=18)
        info = Gtk.Label(wrap=True, xalign=0, selectable=True)
        status = Gtk.Label(wrap=True, xalign=0)
        bar = Gtk.ProgressBar(visible=False)
        note = Gtk.Label(wrap=True, xalign=0, css_classes=["dim-label"],
                         label="Updates come only from github.com/yt-dlp/yt-dlp. The download is checked against "
                               "the checksum GitHub publishes and is saved privately in your user folder; "
                               "nothing needs administrator rights.")
        check = Gtk.Button(label="Check for updates")
        install = Gtk.Button(label="Update now", css_classes=["suggested-action"], sensitive=False)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        row.append(check)
        row.append(install)
        for w in (info, status, bar, note, row):
            box.append(w)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(box)
        dlg.set_child(view)
        dlg.connect("closed", lambda *_: setattr(self, "update_dialog", None))
        state = {"tag": "", "sha": ""}

        def refresh_info():
            path = ytdlp()
            where = "updated copy" if path == str(UPDATED_YTDLP) else "system copy"
            info.set_label(f"In use: yt-dlp {installed_version(path) or 'unknown'}\n{path} ({where})")

        def do_check(*_):
            check.set_sensitive(False)
            install.set_sensitive(False)
            status.set_label("Checking…")

            def work():
                try:
                    tag, sha = latest_release()
                    err = ""
                except Exception as e:
                    tag = sha = ""
                    err = str(e)
                GLib.idle_add(done, tag, sha, err)

            def done(tag, sha, err):
                check.set_sensitive(True)
                self.last_update_check = time.time()
                if err:
                    status.set_label(f"Could not check: {err}")
                    return False
                have = installed_version(ytdlp())
                state.update(tag=tag, sha=sha)
                if version_key(tag) > version_key(have):
                    status.set_label(f"Version {tag} is available.")
                    install.set_sensitive(True)
                else:
                    status.set_label(f"You have the newest version ({have}).")
                return False

            threading.Thread(target=work, daemon=True, name="update-check").start()

        def do_install(*_):
            install.set_sensitive(False)
            check.set_sensitive(False)
            bar.set_visible(True)
            bar.set_fraction(0)
            status.set_label(f"Downloading {state['tag']}…")

            def work():
                try:
                    version = download_release(state["tag"], state["sha"],
                                               progress=lambda f: GLib.idle_add(bar.set_fraction, f))
                    err = ""
                except Exception as e:
                    log.exception("yt-dlp update failed")
                    version, err = "", str(e)
                GLib.idle_add(finished, version, err)

            def finished(version, err):
                check.set_sensitive(True)
                bar.set_visible(False)
                if err:
                    status.set_label(f"Update failed: {err}")
                    install.set_sensitive(True)
                    return False
                refresh_ytdlp()
                refresh_info()
                status.set_label(f"Updated to {version}.")
                self.toasts.add_toast(Adw.Toast(title=f"yt-dlp updated to {version}", timeout=5))
                for u in [u for u, v in self.cache.items() if v is None]:      # retry links that failed before
                    del self.cache[u]
                self.scan_urls()
                self.save_settings()
                return False

            threading.Thread(target=work, daemon=True, name="update-install").start()

        check.connect("clicked", do_check)
        install.connect("clicked", do_install)
        refresh_info()
        dlg.present(self)
        do_check()
