"""Window mixin: Log and Debug log views."""
import shutil
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .config import LOG_FILE, log
from .errors import is_bad


DEBUG_TAB = 3                      # index of the Debug tab in the tab bar


class LogMixin:
    """Methods of the main window (logs)."""

    def on_log_tab(self, _nb, _page, num):
        if num == DEBUG_TAB:
            GLib.idle_add(self.refresh_debug)
            if not self._dbg_timer:
                self._dbg_timer = GLib.timeout_add(1500, self._dbg_tick)

    def _dbg_tick(self):
        if self.tabs.get_current_page() != DEBUG_TAB:
            self._dbg_timer = 0
            return False
        self.refresh_debug()
        return True

    def refresh_debug(self):
        """Show the tail of the hidden debug file; follows new lines while the tab is open."""
        try:
            size = LOG_FILE.stat().st_size
            if size == self._dbg_size:
                return False
            with open(LOG_FILE, "rb") as f:
                f.seek(max(0, size - 200_000))
                text = f.read().decode(errors="replace")
        except OSError:
            return False
        self._dbg_size = size
        if size > 200_000:
            text = text.split("\n", 1)[-1]
        buf = self.dbg_view.get_buffer()
        buf.set_text("")
        for line in text.splitlines(keepends=True):
            if " ERROR " in line or " CRITICAL " in line or line.startswith("Traceback"):
                buf.insert_with_tags(buf.get_end_iter(), line, self.dbg_bad)
            else:
                buf.insert(buf.get_end_iter(), line)
        self.dbg_follow["follow"] = True          # always open at the newest line
        return False

    def export_log(self, *_, debug=False):
        dialog = Gtk.FileDialog(title="Export debug log" if debug else "Export log",
                                initial_name="yt-dlp-gtk-debug.txt" if debug else "yt-dlp-gtk-log.txt")

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
            except GLib.Error:
                return
            try:
                if debug:
                    shutil.copyfile(LOG_FILE, path)
                else:
                    buf = self.log_view.get_buffer()
                    Path(path).write_text(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
                self.toasts.add_toast(Adw.Toast(title=f"Saved to {path}", timeout=5))
            except Exception:
                log.exception("Export failed")
                self.append("[export failed — see the Debug log tab]\n")

        dialog.save(self, None, done)

    def append(self, text, bad=None):
        buf = self.log_view.get_buffer()
        if bad is None:
            bad = is_bad(text)
        if bad:
            buf.insert_with_tags(buf.get_end_iter(), text, self.bad_tag)
        else:
            buf.insert(buf.get_end_iter(), text)
        return False
