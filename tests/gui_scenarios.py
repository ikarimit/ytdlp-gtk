"""GUI checks, run in their own process by test_gui.py (GTK can only start once per process).

Prints `PASS name` / `FAIL name: why` per scenario and `DONE` at the end. Uses an isolated config folder and
a separate application id, so a running copy of the app and its settings are never touched.
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp(prefix="ytdlp-gtk-gui-")
os.environ.update(XDG_CONFIG_HOME=f"{tmp}/config", XDG_DATA_HOME=f"{tmp}/data", YTDLP_GTK_APP_ID="local.ytdlp.gtk.test")

from gi.repository import Gio, GLib, Gtk      # noqa: E402

from ytdlp_gtk import tools, win_queue, win_updates     # noqa: E402
from ytdlp_gtk.app import App                            # noqa: E402
from ytdlp_gtk.security import validate_cmd              # noqa: E402

win_queue.play_sound = lambda kind: None                 # no sounds while testing
INFO = {"title": "Sample", "formats": [
    {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 1080},
    {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 130},
]}


def row(w, title, status, url="https://example.com/v", path=""):
    return w.store.append([title, "—", 0, status, "", "", url, json.dumps([tools.ytdlp(), "--", url]), "", path])


def statuses(w):
    return [r[3] for r in w.store]


def t_layout(w):
    labels = [w.tabs.get_tab_label(w.tabs.get_nth_page(i)).get_label() for i in range(w.tabs.get_n_pages())]
    assert labels == ["Metadata", "Queue", "Logs", "Debug"], labels


def t_url_box_ignores_non_links(w):
    w.url_buf.set_text("--exec id\nhttps://example.com/a\nfile:///etc/passwd\n-x\nhttps://example.com/a\n")
    assert w.get_urls() == ["https://example.com/a"], w.get_urls()


def t_commands_are_safe(w):
    cmd = w.build_cmd("https://example.com/a")
    assert cmd[-2:] == ["--", "https://example.com/a"] and validate_cmd(cmd), cmd
    w.format_choice["https://example.com/a"] = {"id": "137", "video": True, "audio": False}
    assert "137+bestaudio" in w.build_cmd("https://example.com/a")
    w.format_choice.clear()


def t_queue_removal(w):
    w.store.clear()
    for t, st in (("a", "Failed"), ("b", "Done"), ("c", "Downloading"), ("d", "Stopped")):
        row(w, t, st)
    sel = w.tv.get_selection()
    sel.select_path(Gtk.TreePath.new_from_string("0"))
    sel.select_path(Gtk.TreePath.new_from_string("2"))
    w.remove_selected()
    assert statuses(w) == ["Done", "Downloading", "Stopped"], statuses(w)          # running row kept
    w.clear_status(("Done",)); w.clear_status(("Stopped",))
    assert statuses(w) == ["Downloading"], statuses(w)
    w.store.clear()


def t_removed_waiting_job_never_starts(w):
    w.store.clear()
    it = row(w, "ghost", "Queued")
    w.jobs.append(w.job_for(it))
    w.store.remove(it)
    w.schedule()
    assert not w.active and not w.jobs


def t_tampered_saved_queue(w):
    good = {"title": "ok", "url": "https://example.com/v", "status": "Failed", "cmd": [tools.ytdlp(), "--no-playlist", "--", "https://example.com/v"]}
    evil = {"title": "evil", "url": "https://example.com/v", "status": "Queued", "cmd": [tools.ytdlp(), "--exec", "id", "--", "https://example.com/v"]}
    evil2 = {"title": "evil2", "url": "--exec id", "status": "Queued", "cmd": [tools.ytdlp(), "--", "--exec id"]}
    legacy = {"title": "legacy", "url": "https://example.com/old", "status": "Queued",       # saved before `--` existed
              "cmd": [tools.ytdlp(), "--newline", "-f", "b", "https://example.com/old"]}
    Path(f"{tmp}/config/ytdlp-gtk/settings.json").write_text(json.dumps({"queue": [good, evil, evil2, legacy]}))
    w.store.clear()
    w.load_settings()
    assert [r[0] for r in w.store] == ["ok", "legacy"], [r[0] for r in w.store]
    assert json.loads(w.store[1][7])[-2:] == ["--", "https://example.com/old"]
    w.store.clear()


def t_double_click_opens_only_media(w):
    launched = []
    real = Gio.AppInfo.launch_default_for_uri
    Gio.AppInfo.launch_default_for_uri = staticmethod(lambda uri, ctx: launched.append(uri))
    try:
        d = Path(tmp)
        (d / "clip.mp4").write_bytes(b"x"); (d / "run.sh").write_text("echo hi"); (d / "note.txt").write_text("t")
        w.store.clear()
        for name in ("clip.mp4", "run.sh", "note.txt", "missing.mp4"):
            row(w, name, "Done", path=str(d / name))
        row(w, "failed", "Failed", path=str(d / "clip.mp4"))
        for i in range(5):
            w.on_row_activated(w.tv, Gtk.TreePath.new_from_string(str(i)), None)
        assert len(launched) == 1 and launched[0].endswith("clip.mp4"), launched      # not .sh, .txt, missing or failed
    finally:
        Gio.AppInfo.launch_default_for_uri = real
        w.store.clear()


def t_formats_tab(w):
    url = "https://example.com/f"
    w.url_buf.set_text(url + "\n")
    w.cache[url] = (INFO, None)
    w.show_current()
    assert len(w.fmt_checks) == 3, len(w.fmt_checks)            # Automatic + 137 + 140
    w.fmt_checks[1].set_active(True)                              # pick format 137
    assert w.format_choice.get(url, {}).get("id") == "137", w.format_choice
    assert "-f 137+bestaudio" in w.summary["Command"].get_label(), w.summary["Command"].get_label()
    w.fmt_checks[0].set_active(True)                              # back to Automatic
    assert url not in w.format_choice
    w.format_choice.clear()


def t_old_cookie_files_are_migrated(w):
    """Browser copies were stale snapshots: shredded. An imported cookies.txt moves into the keyring."""
    if w.vault.mode() != "keyring":
        return
    jar = ("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tkeep-me\n")
    cfg = Path(f"{tmp}/config/ytdlp-gtk")
    (cfg / "cookies-chromium.txt").write_text(jar)
    (cfg / "cookies-file.txt").write_text(jar)
    try:
        w.migrate_cookie_files()
        assert not (cfg / "cookies-chromium.txt").exists() and not (cfg / "cookies-file.txt").exists()
        assert w.vault.load("chromium") is None, "browser cookies must never be stored"
        assert "keep-me" in (w.vault.load("file") or ""), "the imported cookies.txt belongs in the keyring"
    finally:
        w.vault.forget("file")


def t_cookie_arguments(w):
    w.sel["cookies"] = "chromium"
    args = w.cookie_args()
    assert args[0] == "--cookies-from-browser" and args[1].startswith("chromium"), args
    assert validate_cmd(w.build_cmd("https://example.com/a")), w.build_cmd("https://example.com/a")
    w.vault_keys.add("file")
    w.sel["cookies"] = "file"
    assert w.cookie_args() == ["--cookies", "vault:file"]
    assert validate_cmd(w.build_cmd("https://example.com/a"))
    w.vault_keys.discard("file")
    assert w.cookie_args() == []                      # no imported file yet: nothing to pass
    w.sel["cookies"] = "none"
    assert w.cookie_args() == []


def t_log_follows_and_scrollbar_styled(w):
    for i in range(80):
        w.append(f"line {i}\n")
    scroll = w.log_view.get_parent()
    assert scroll.get_overlay_scrolling() is False
    assert "logscroll" in scroll.get_css_classes()


def t_update_dialog(w):
    win_updates.latest_release = lambda: ("2099.01.01", "a" * 64)
    w.show_update_dialog()
    assert w.update_dialog is not None


def t_update_dialog_offers_install(w):
    child = w.update_dialog.get_child()
    found = []

    def walk(widget):
        if isinstance(widget, Gtk.Button) and widget.get_label() == "Update now":
            found.append(widget.get_sensitive())
        c = widget.get_first_child()
        while c:
            walk(c); c = c.get_next_sibling()

    walk(child)
    assert found == [True], found
    w.update_dialog.close()


SCENARIOS = [t_layout, t_url_box_ignores_non_links, t_commands_are_safe, t_queue_removal,
             t_removed_waiting_job_never_starts, t_tampered_saved_queue, t_double_click_opens_only_media,
             t_formats_tab, t_old_cookie_files_are_migrated, t_cookie_arguments,
             t_log_follows_and_scrollbar_styled, t_update_dialog, t_update_dialog_offers_install]


def run(app):
    w = app.get_active_window()
    w.cookies_asked = True
    from ytdlp_gtk.vault import Vault
    w.vault = Vault("local.ytdlp.gtk.Test")           # never touch the real cookie entries while testing
    if w.cookie_dialog:
        w.cookie_dialog.close()
    it = iter(SCENARIOS)

    def step():
        fn = next(it, None)
        if fn is None:
            print("DONE", flush=True)
            app.quit()
            return False
        try:
            fn(w)
            print("PASS", fn.__name__, flush=True)
        except Exception:
            print("FAIL", fn.__name__, traceback.format_exc().strip().splitlines()[-1], flush=True)
        return True

    GLib.timeout_add(700, step)


app = App()
app.connect("activate", lambda a: GLib.idle_add(lambda: (GLib.timeout_add(1500, run, a), False)[1]))
app.run([])
