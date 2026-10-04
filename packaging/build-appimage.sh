#!/usr/bin/env bash
# Build dist/yt-dlp-GTK-<version>-x86_64.AppImage from this folder.
#   packaging/build-appimage.sh            build (downloads the build tools the first time)
#   packaging/build-appimage.sh --keep     keep packaging/build/AppDir for inspection
# Edit main.py, bump VERSION in main.py, run this again: that is the whole repackage loop.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cache="$here/packaging/.cache"
build="$here/packaging/build"
appdir="$build/AppDir"
lib=/usr/lib/x86_64-linux-gnu
pyver=3.14
version="$(python3 - "$here/ytdlp_gtk/config.py" <<'PY'
import re, sys
print(re.search(r'VERSION, CREATED = "[^"]*", "([^"]*)"', open(sys.argv[1]).read())[1])
PY
)"
export APPIMAGE_EXTRACT_AND_RUN=1          # work even where FUSE isn't available

mkdir -p "$cache"
pins="$here/packaging/tools.sha256"
fetch() {   # fetch <file> <url>: download once, then every build checks the file against the pinned SHA-256
    [ -s "$cache/$1" ] || { echo "Downloading $1"; curl -fL --retry 3 -o "$cache/$1" "$2"; }
    local sum; sum="$(sha256sum "$cache/$1" | cut -d' ' -f1)"
    if grep -q " $1\$" "$pins" 2>/dev/null; then
        [ "$(grep " $1\$" "$pins" | cut -d' ' -f1)" = "$sum" ] || { echo "CHECKSUM MISMATCH for $1 (expected pin differs). Delete packaging/.cache/$1 and its line in packaging/tools.sha256 if you meant to update it."; exit 1; }
    else
        echo "$sum  $1" >> "$pins"; echo "Pinned $1 ($sum)"
    fi
}
fetch appimagetool-x86_64.AppImage https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
fetch linuxdeploy-x86_64.AppImage https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
fetch linuxdeploy-plugin-gtk.sh https://raw.githubusercontent.com/linuxdeploy/linuxdeploy-plugin-gtk/master/linuxdeploy-plugin-gtk.sh
chmod +x "$cache"/*.AppImage "$cache"/*.sh

rm -rf "$build"
mkdir -p "$appdir/usr/bin" "$appdir/usr/lib/ytdlp-gtk" "$appdir/usr/lib/girepository-1.0" \
         "$appdir/usr/lib/python3/dist-packages" "$appdir/usr/share/applications" \
         "$appdir/usr/share/icons/hicolor/scalable/apps"

echo "== app"
install -m 644 "$here/main.py" "$appdir/usr/lib/ytdlp-gtk/main.py"
mkdir -p "$appdir/usr/lib/ytdlp-gtk/ytdlp_gtk"
install -m 644 "$here"/ytdlp_gtk/*.py "$appdir/usr/lib/ytdlp-gtk/ytdlp_gtk/"
mkdir -p "$appdir/usr/lib/ytdlp-gtk/ytdlp_gtk/keys"
install -m 644 "$here"/ytdlp_gtk/keys/* "$appdir/usr/lib/ytdlp-gtk/ytdlp_gtk/keys/"
cp -r "$here/icons" "$appdir/usr/lib/ytdlp-gtk/icons"
icon="$here/icons/hicolor/scalable/apps/local.ytdlp.gtk.svg"
cp "$icon" "$appdir/usr/share/icons/hicolor/scalable/apps/"
sed 's|^Exec=.*|Exec=ytdlp-gtk|' "$here/local.ytdlp.gtk.desktop" > "$appdir/usr/share/applications/local.ytdlp.gtk.desktop"

echo "== python $pyver + PyGObject"
install -m 755 "/usr/bin/python$pyver" "$appdir/usr/bin/python$pyver"
ln -s "python$pyver" "$appdir/usr/bin/python3"
cp -r "/usr/lib/python$pyver" "$appdir/usr/lib/python$pyver"
( cd "$appdir/usr/lib/python$pyver" && rm -rf test idlelib tkinter turtledemo ensurepip lib2to3 config-* EXTERNALLY-MANAGED \
    && find . -name __pycache__ -type d -prune -exec rm -rf {} + )
cp -r /usr/lib/python3/dist-packages/gi "$appdir/usr/lib/python3/dist-packages/gi"
find "$appdir/usr/lib/python3" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$lib"/girepository-1.0/*.typelib "$appdir/usr/lib/girepository-1.0/"

echo "== yt-dlp (downloaded from GitHub, GPG signature and SHA-256 checked) "
XDG_CONFIG_HOME="$build/xdg-config" XDG_DATA_HOME="$build/xdg-data" PYTHONPATH="$here" \
    python3 -m ytdlp_gtk.updater "$appdir/usr/bin/yt-dlp"

echo "== ffmpeg (the Ubuntu package: signed by the archive, files re-checked against its checksums)"
mapfile -t pkgs < <(ldd /usr/bin/ffmpeg /usr/bin/ffprobe | awk '/=> \//{print $3}' | sort -u | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u)
changed="$(dpkg --verify ffmpeg "${pkgs[@]}" 2>&1 | grep -v ' c /' || true)"
[ -z "$changed" ] || { echo "Installed ffmpeg files differ from their packages (not bundling):"; echo "$changed"; exit 1; }
mkdir -p "$appdir/usr/lib/gio/modules"
cp "$lib/gio/modules/libdconfsettings.so" "$appdir/usr/lib/gio/modules/"     # lets GTK read your desktop settings

echo "== libraries (linuxdeploy + GTK plugin)"
libs=()
for so in "$appdir/usr/lib/python$pyver"/lib-dynload/*.so "$appdir"/usr/lib/python3/dist-packages/gi/_gi*.so; do
    libs+=(-l "$so")
done
for name in libsecret-1.so.0 libdconf.so.1 libgtk-4.so.1 libadwaita-1.so.0 libgdk_pixbuf-2.0.so.0 libpangocairo-1.0.so.0 libcairo-gobject.so.2 \
            libgraphene-1.0.so.0 libgirepository-2.0.so.0 libgio-2.0.so.0 libgmodule-2.0.so.0; do
    path="$(ldconfig -p | awk -v n="$name" '$1 == n {print $NF; exit}')"
    [ -n "$path" ] && libs+=(-l "$path")
done
# The GTK plugin asks pkg-config for gtk4's directories; the -dev package isn't installed, so give it a stub.
mkdir -p "$build/pc-stub"
cat > "$build/pc-stub/gtk4.pc" <<PC
prefix=/usr
exec_prefix=/usr
libdir=$lib
Name: gtk4
Description: stub for linuxdeploy-plugin-gtk
Version: 4.0
PC
export PKG_CONFIG_PATH="$build/pc-stub${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export PATH="$cache:$PATH"
export DEPLOY_GTK_VERSION=4
export VERSION="$version"
( cd "$build" && "$cache/linuxdeploy-x86_64.AppImage" --appdir "$appdir" --plugin gtk \
    -e "$appdir/usr/bin/python$pyver" -e /usr/bin/ffmpeg -e /usr/bin/ffprobe -e /usr/bin/gpgv "${libs[@]}" \
    -d "$appdir/usr/share/applications/local.ytdlp.gtk.desktop" -i "$icon" \
    --custom-apprun="$here/packaging/AppRun" )

# linuxdeploy wraps our AppRun in a launcher that first sources its GTK hook; that hook forces GTK_THEME=Adwaita and
# GDK_BACKEND=x11, so the AppImage would not look or behave like the script. Use our AppRun directly.
install -m 755 "$here/packaging/AppRun" "$appdir/AppRun"
rm -f "$appdir/AppRun.wrapped" "$appdir"/apprun-hooks/linuxdeploy-plugin-gtk.sh
# linuxdeploy also copied the Python extension modules next to the shared libraries; drop the duplicates
rm -f "$appdir"/usr/lib/*.cpython-*.so
echo "== AppImage"
mkdir -p "$here/dist"
out="$here/dist/yt-dlp-GTK-${version}-x86_64.AppImage"
ARCH=x86_64 "$cache/appimagetool-x86_64.AppImage" --no-appstream "$appdir" "$out"
[ "${1:-}" = "--keep" ] || rm -rf "$build"
echo "Built $out ($(du -h "$out" | cut -f1))"
