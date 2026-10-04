"""Locating yt-dlp / JS runtime, sounds, moving finished files, safe image download."""
import os
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib  # noqa: E402

from .config import DATA_DIR
from .security import MAX_IMAGE, open_web, valid_url

UPDATED_YTDLP = DATA_DIR / "yt-dlp"          # the copy the in-app updater maintains


def child_env():
    """Environment for programs we start. Inside the AppImage the launcher points Python and the loader at the
    bundled copies; programs of the system (and the self-contained yt-dlp) must not inherit that."""
    env = dict(os.environ)
    if "APPDIR" in env:
        orig = env.pop("YTDLP_GTK_ORIG_LD_LIBRARY_PATH", "")
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
        for name in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "GI_TYPELIB_PATH"):
            env.pop(name, None)
    return env


def find_ytdlp():
    """The yt-dlp to use: updated copy, then the one inside an AppImage, PATH, usual install spots.
    (A menu launcher may not have ~/.local/bin on PATH, hence the explicit candidates.)"""
    if UPDATED_YTDLP.exists() and os.access(UPDATED_YTDLP, os.X_OK):
        return str(UPDATED_YTDLP)
    bundled = Path(os.environ.get("APPDIR", "/nonexistent")) / "usr/bin/yt-dlp"      # inside the AppImage
    if bundled.exists():
        return str(bundled)
    exe = shutil.which("yt-dlp")
    if exe:
        return exe
    for cand in ("~/.local/bin/yt-dlp", "/usr/local/bin/yt-dlp", "/usr/bin/yt-dlp", "~/bin/yt-dlp"):
        path = Path(cand).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return "yt-dlp"


_current = {"path": find_ytdlp()}


def ytdlp():
    """The yt-dlp executable in use right now."""
    return _current["path"]


def refresh_ytdlp():
    """Re-detect after the updater installed a newer copy."""
    _current["path"] = find_ytdlp()
    return _current["path"]


def js_runtime_args():
    """YouTube needs a JavaScript runtime to solve its challenges (without one, age-restricted and
    many other videos fail). yt-dlp only enables deno by default, so point it at node/bun/quickjs."""
    if shutil.which("deno"):
        return []
    for exe, name in (("node", "node"), ("nodejs", "node"), ("bun", "bun"), ("qjs", "quickjs")):
        if shutil.which(exe):
            return ["--js-runtimes", name]
    return []


def pdeath_prefix():
    """Run yt-dlp under `setpriv --pdeathsig TERM` so it dies if this app dies (no orphan downloads).
    (A Python preexec_fn would do the same but can deadlock in a multi-threaded program.)"""
    return ["setpriv", "--pdeathsig", "TERM", "--"] if shutil.which("setpriv") else []


def play_sound(kind):
    """Audible cue: 'done' or 'error', via the desktop's sound theme."""
    ev = "dialog-error" if kind == "error" else "complete"
    oga = f"/usr/share/sounds/freedesktop/stereo/{ev}.oga"
    for cmd in (["canberra-gtk-play", "-i", ev], ["pw-play", oga], ["paplay", oga]):
        if shutil.which(cmd[0]) and (cmd[0] == "canberra-gtk-play" or Path(oga).exists()):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_env())
            return
    display = Gdk.Display.get_default()
    if display:
        display.beep()


def move_files(files, dest, root):
    """Move each finished file and its sidecars (thumbnail, subtitles, …) into dest.

    Only files inside `root` (the folder the download was told to write to) are ever touched.
    Returns [(old_path, new_path)] for the main files."""
    dest, root = Path(dest), Path(root).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in files:
        main = Path(f)
        if not main.exists() or not main.resolve().is_relative_to(root) or main.parent.resolve() == dest.resolve():
            continue
        for item in sorted(main.parent.iterdir()):
            if item == main or item.name.startswith(main.stem + "."):
                target, i = dest / item.name, 1
                while target.exists():
                    target = dest / f"{item.stem} ({i}){item.suffix}"
                    i += 1
                shutil.move(str(item), str(target))
                if item == main:
                    moved.append((str(main), str(target)))
    return moved


def download_image(url):
    """Fetch an http(s) image (at most MAX_IMAGE bytes) and return it as a Gdk.Texture."""
    if not valid_url(url):
        raise ValueError("not an http(s) URL")
    with open_web(url, timeout=15) as resp:
        data = resp.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise ValueError("image too large")
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
