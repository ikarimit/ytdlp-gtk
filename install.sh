#!/usr/bin/env bash
# Install the launcher and icon for the current user (~/.local/share). Safe to re-run.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/share/icons/hicolor/scalable/apps ~/.local/share/applications
cp "$here/icons/hicolor/scalable/apps/local.ytdlp.gtk.svg" ~/.local/share/icons/hicolor/scalable/apps/
sed "s|^Exec=.*|Exec=$here/main.py|" "$here/local.ytdlp.gtk.desktop" > ~/.local/share/applications/local.ytdlp.gtk.desktop
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "Installed icon and launcher for yt-dlp GTK."
