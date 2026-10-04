#!/usr/bin/env python3
"""Does the AppImage behave exactly like the Python script?

Runs `main.py --selftest` and `dist/yt-dlp-GTK-*-x86_64.AppImage --selftest` side by side (same display, same
separate test configuration, same renderer) and compares what each can see: versions, theme, fonts, icons, the
keyring, the helper programs, and a screenshot of the window, pixel by pixel.

    python3 tests/parity.py            # exit status 0 only when everything matches
"""
import glob
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = {"renderer"}                 # decided by the graphics drivers, not by us (forced equal below anyway)


def run(cmd, label, shot):
    tmp = tempfile.mkdtemp(prefix=f"ytdlp-gtk-parity-{label}-")
    env = {**os.environ, "XDG_CONFIG_HOME": f"{tmp}/config", "XDG_DATA_HOME": f"{tmp}/data",
           "YTDLP_GTK_APP_ID": f"local.ytdlp.gtk.parity{label}", "YTDLP_GTK_SELFTEST_PNG": shot,
           "GSK_RENDERER": "cairo"}
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env).stdout
    return dict(line.split(": ", 1) for line in out.splitlines() if ": " in line and not line.startswith("screenshot"))


def pixel_diff(a, b):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    pa, pb = GdkPixbuf.Pixbuf.new_from_file(a), GdkPixbuf.Pixbuf.new_from_file(b)
    if (pa.get_width(), pa.get_height()) != (pb.get_width(), pb.get_height()):
        return None, f"sizes differ: {pa.get_width()}x{pa.get_height()} vs {pb.get_width()}x{pb.get_height()}"
    da, db, n = pa.get_pixels(), pb.get_pixels(), pa.get_n_channels()
    different = sum(1 for i in range(0, len(da), n) if max(abs(da[i + c] - db[i + c]) for c in range(3)) > 12)
    return different / (len(da) // n), ""


def main():
    images = sorted(glob.glob(str(ROOT / "dist" / "yt-dlp-GTK-*-x86_64.AppImage")))
    if not images:
        print("No AppImage in dist/: run packaging/build-appimage.sh first")
        return 2
    shots = tempfile.mkdtemp(prefix="ytdlp-gtk-parity-shots-")
    src = run([sys.executable, str(ROOT / "main.py"), "--selftest"], "src", f"{shots}/source.png")
    app = run([images[-1], "--selftest"], "img", f"{shots}/appimage.png")
    bad = 0
    print(f"{'check':26} {'python script':34} AppImage")
    for key in src:
        if key in IGNORE:
            continue
        same = src[key] == app.get(key)
        bad += not same
        print(f"{key:26} {src[key][:33]:34} {app.get(key, '(missing)')[:33]}  {'ok' if same else '<-- DIFFERENT'}")
    for key in app:
        if key not in src and key not in IGNORE:
            bad += 1
            print(f"{key:26} (missing)  {app[key]}  <-- only in the AppImage")
    frac, note = pixel_diff(f"{shots}/source.png", f"{shots}/appimage.png")
    if frac is None:
        bad += 1
        print("screenshot:", note)
    else:
        print(f"screenshot: {frac * 100:.2f}% of pixels differ (limit 0.5%)")
        bad += frac > 0.005
    print("PARITY OK" if not bad else f"PARITY BROKEN: {int(bad)} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
