#!/usr/bin/env bash
# Build dist/ytdlp-gtk_<version>_all.deb from this folder.  Usage: packaging/build-deb.sh
set -euo pipefail

MAINTAINER="${DEB_MAINTAINER:-yt-dlp GTK contributors <noreply@example.invalid>}"   # export DEB_MAINTAINER to override
here="$(cd "$(dirname "$0")/.." && pwd)"
version="$(python3 - "$here/ytdlp_gtk/config.py" <<'PY'
import re, sys
print(re.search(r'VERSION, CREATED = "[^"]*", "([^"]*)"', open(sys.argv[1]).read())[1])
PY
)"
pkg="ytdlp-gtk"
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

install -d "$root/DEBIAN" "$root/usr/bin" "$root/usr/lib/$pkg" \
           "$root/usr/share/applications" "$root/usr/share/icons/hicolor/scalable/apps" \
           "$root/usr/share/doc/$pkg"

install -m 644 "$here/main.py" "$root/usr/lib/$pkg/main.py"
install -d "$root/usr/lib/$pkg/ytdlp_gtk"
install -m 644 "$here"/ytdlp_gtk/*.py "$root/usr/lib/$pkg/ytdlp_gtk/"
install -d "$root/usr/lib/$pkg/ytdlp_gtk/keys"
install -m 644 "$here"/ytdlp_gtk/keys/* "$root/usr/lib/$pkg/ytdlp_gtk/keys/"
install -m 755 "$here/packaging/ytdlp-gtk" "$root/usr/bin/ytdlp-gtk"
install -m 644 "$here/icons/hicolor/scalable/apps/local.ytdlp.gtk.svg" \
        "$root/usr/share/icons/hicolor/scalable/apps/local.ytdlp.gtk.svg"
sed 's|^Exec=.*|Exec=ytdlp-gtk|' "$here/local.ytdlp.gtk.desktop" > "$root/usr/share/applications/local.ytdlp.gtk.desktop"
chmod 644 "$root/usr/share/applications/local.ytdlp.gtk.desktop"

cat > "$root/usr/share/doc/$pkg/copyright" <<COPY
Copyright: 2026 yt-dlp GTK contributors
License: MIT (see the LICENSE file in the source repository)

This program only drives yt-dlp (Unlicense) and uses GTK 4 / libadwaita (LGPL).
Created with help from AI (Claude, by Anthropic).
COPY
chmod 644 "$root/usr/share/doc/$pkg/copyright"

find "$root" -type d -exec chmod 755 {} +          # dpkg applies directory modes literally
size="$(du -sk "$root/usr" | cut -f1)"
cat > "$root/DEBIAN/control" <<CTRL
Package: $pkg
Version: $version
Section: video
Priority: optional
Architecture: all
Maintainer: $MAINTAINER
Installed-Size: $size
Depends: python3 (>= 3.9), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5), gir1.2-secret-1, gpgv, ffmpeg
Recommends: yt-dlp, nodejs, sound-theme-freedesktop
Description: GTK front-end for yt-dlp
 Download video and audio with yt-dlp from a simple GTK 4 / libadwaita window:
 URL list and playlists with per-video selection, audio/video options, a
 download queue with simultaneous downloads and resume after closing, browser
 cookie setup for age-restricted videos, and finished/error notifications.
 .
 Created with help from AI.
CTRL

mkdir -p "$here/dist"
out="$here/dist/${pkg}_${version}_all.deb"
dpkg-deb --root-owner-group --build "$root" "$out" >/dev/null
echo "Built $out"
