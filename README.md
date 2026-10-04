# yt-dlp GTK

A GTK 4 / libadwaita front-end for yt-dlp (Python, PyGObject). Created with help from AI.

Bugs: `BUGS.md` · Ideas and release checklist: `FEATURES.md`

## Run from source (the everyday loop)

    ./main.py                 # edit main.py, relaunch, repeat
    ./main.py --selftest      # print what the app can see (python/gtk/yt-dlp/ffmpeg/icons), then quit

Settings and the hidden debug log live in `~/.config/ytdlp-gtk/`.
`YTDLP_GTK_APP_ID=local.ytdlp.gtk.test ./main.py` runs a second, separate instance (handy while testing),
and `XDG_CONFIG_HOME=/some/dir` gives it its own settings.

## Make a new release

1. Change something in `ytdlp_gtk/`.
2. Bump `VERSION` (and `CREATED` if you like) in `ytdlp_gtk/config.py` (`APP_NAME, VERSION, CREATED = ...`).
3. Run the tests.
4. Build whichever package you need:

       packaging/build-appimage.sh      # dist/yt-dlp-GTK-<version>-x86_64.AppImage  (self-contained, ~100 MB)
       packaging/build-deb.sh           # dist/ytdlp-gtk_<version>_all.deb           (small, uses system libraries)

   `--keep` leaves `packaging/build/AppDir` for inspection. Every AppImage build downloads the newest yt-dlp from
   GitHub and checks its GPG signature and SHA-256 (the self-contained build, so cookie decryption works the same
   everywhere). ffmpeg is taken from the installed Ubuntu package after `dpkg --verify` says its files are unmodified.
   The first build also downloads appimagetool, linuxdeploy and the GTK plugin into `packaging/.cache/`; each is pinned
   by SHA-256 in `packaging/tools.sha256`.
5. Check it: `python3 tests/parity.py` (runs the script and the AppImage side by side and compares them).

The AppImage bundles Python 3.14, PyGObject, GTK 4, libadwaita, libsecret, gpgv, ffmpeg and yt-dlp. It does not bundle
a JavaScript runtime (node/deno, needed for age-restricted YouTube videos) or the sound-theme tools; those come from
the system, the same as when running the script. It is built from this machine's libraries, so it runs on the same
or newer distributions (Ubuntu 26.04-ish).

## Tests

    python3 -m unittest discover -s tests -v     # unit tests + GUI scenarios (isolated config, needs a display)
    tests/static_checks.sh                       # pyflakes + bandit + shellcheck (sudo apt install bandit python3-pyflakes shellcheck)
    python3 tests/parity.py                      # AppImage vs script, side by side (after packaging/build-appimage.sh)

## Layout

    main.py                     tiny launcher
    ytdlp_gtk/                  the app: config, options, security, tools, updater, formats, widgets,
                                window.py (builds the UI) + win_core/urls/queue/cookies/logs/updates mixins, app.py
    tests/                      unittest suites
    SECURITY.md                 review, protections, remaining risks
    icons/                      app icon (SVG)
    local.ytdlp.gtk.desktop     menu entry template
    install.sh                  per-user menu entry + icon (~/.local/share)
    packaging/                  build-appimage.sh, build-deb.sh, AppRun, launcher

## Licence

MIT, see [LICENSE](LICENSE). Third-party components and legal notes: [NOTICE.md](NOTICE.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
