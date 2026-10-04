"""Application object, self-test and entry point."""
import os
import shutil
import subprocess
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gdk, Gtk  # noqa: E402

from .config import APP_ID, ICON, VERSION
from . import updater
from .tools import child_env, ytdlp
from .window import Window


class App(Adw.Application):
    def __init__(self, selftest_mode=False):
        super().__init__(application_id=APP_ID)
        self.selftest_mode = selftest_mode

    def do_activate(self):
        win = self.props.active_window or Window(self)    # one window; relaunch just raises it
        win.present()
        if self.selftest_mode:
            GLib.timeout_add(3000, self.selftest, win)

    def selftest(self, win):
        """`main.py --selftest`: print what the running copy can see (one `name: value` per line), optionally save a
        screenshot (YTDLP_GTK_SELFTEST_PNG=/path.png), then quit. tests/parity.py compares these lines between the
        source and the AppImage."""
        if win.cookie_dialog:
            win.cookie_dialog.close()
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        settings, style = Gtk.Settings.get_default(), Adw.StyleManager.get_default()

        def first_line(cmd):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=child_env()).stdout
                return (out.strip().splitlines() or ["(no output)"])[0][:80]
            except (OSError, subprocess.SubprocessError) as e:
                return f"FAILED: {e}"

        info = {
            "python": sys.version.split()[0],
            "gtk": f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}",
            "libadwaita": f"{Adw.get_major_version()}.{Adw.get_minor_version()}",
            "app version": VERSION,
            "yt-dlp": first_line([ytdlp(), "--version"]),
            "ffmpeg": first_line(["ffmpeg", "-version"]),
            "gpgv": first_line(["gpgv", "--version"]),
            "node": first_line(["node", "--version"]),
            "icon app/symbolic/folder": f"{theme.has_icon(ICON)}/{theme.has_icon('list-add-symbolic')}/"
                                        f"{theme.has_icon('folder-open-symbolic')}",
            "gtk font": settings.get_property("gtk-font-name"),
            "gtk icon theme": settings.get_property("gtk-icon-theme-name"),
            "gtk cursor theme": settings.get_property("gtk-cursor-theme-name"),
            "dark": style.get_dark(),
            "color scheme": style.get_color_scheme().value_nick,
            "accent": style.get_accent_color().value_nick if hasattr(style, "get_accent_color") else "n/a",
            "cookie storage": win.vault.mode(),
            "update signing key": "present" if updater.KEYRING.exists() else "MISSING",
            "sound player": next((c for c in ("canberra-gtk-play", "pw-play", "paplay") if shutil.which(c)), "none"),
            "locale": os.environ.get("LANG", ""),
            "window": f"{win.get_width()}x{win.get_height()}",
            "renderer": type(win.get_native().get_renderer()).__name__,
        }
        for name, value in info.items():
            print(f"{name}: {value}")
        GLib.timeout_add(1200, self.selftest_finish, win)       # let a frame draw after closing the dialog
        return False

    def selftest_finish(self, win):
        shot = os.environ.get("YTDLP_GTK_SELFTEST_PNG")
        if shot:
            try:
                paintable = Gtk.WidgetPaintable.new(win)
                snap = Gtk.Snapshot()
                paintable.snapshot(snap, win.get_width(), win.get_height())
                win.get_native().get_renderer().render_texture(snap.to_node(), None).save_to_png(shot)
                print("screenshot:", shot)
            except Exception as e:
                print("screenshot failed:", e)
        print("selftest ok", flush=True)
        self.quit()
        return False


def main(argv):
    """Entry point used by main.py. `--selftest` prints diagnostics and quits (for checking builds)."""
    selftest = "--selftest" in argv
    return App(selftest_mode=selftest).run([a for a in argv if a != "--selftest"])
