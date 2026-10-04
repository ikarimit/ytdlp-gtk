# Feature requests and ideas

Priority: **P1** next · **P2** soon · **P3** nice to have. Status: idea / planned / done.
Rule of thumb: finish the app here first, build the AppImage afterwards (see "Before the AppImage").

## Layout and usability
- **F-001 · Layout (done).** Metadata | Queue | Logs | Debug tabs, compact Download block, option groups in columns.
  The page is now close to one screen.
- **F-010 · Queue rows (partly done).** Double-click opens the finished file (done). No right-click menu, by choice.
- **F-011 · Keyboard shortcuts (P3).** Ctrl+V adds a link, Ctrl+Enter downloads, Delete removes, F11 full screen (done).
- **F-012 · Clipboard helper (P2).** Offer to add a link when one is on the clipboard at launch/focus.
- **F-013 · Notification actions (P3).** "Open folder" / "Play" buttons on the finished notification.

## Downloading
- **F-002 · yt-dlp updater (done).** Header button, daily background check with a toast, hash-verified private copy in
  `~/.local/share/ytdlp-gtk/`. Idea left: also verify yt-dlp's GPG signature.
- **F-003 · Format picker (done).** Settings → Formats lists what the selected video offers; pick one or stay Automatic.
- **F-004 · Named presets (P2).** "Music MP3", "1080p MP4", "Archive" — one click applies a set of options.
- **F-005 · Pause / resume / reorder (P2).** Per-row pause, drag to reorder, priorities.
- **F-006 · Retry with back-off (P2).** Automatic retries for network errors and rate limits.
- **F-007 · Download archive (parked).** Not for now, by request.
- **F-008 · Scheduling and limits (P3).** Start at night, bandwidth limit by time of day.
- **F-009 · Audio-language picker (P3).** Flags for the audio track, like the subtitle flags.

## Cookies and accounts
- **F-020 · Cookie health check (P2).** Show "signed in as …" / "cookies expire in N days" and refresh automatically.
- **F-021 · Test the other browsers (P2).** Chrome, Brave, Edge, Vivaldi, Opera need a real check (Firefox and Chromium, both snap, work).

## Code quality (do before publishing)
- **F-030 · Split `main.py` (done).** `ytdlp_gtk/` package: config, options, security, tools, updater, formats, widgets and
  window mixins (core, urls, queue, cookies, logs, updates).
- **F-031 · Tests (done, grow them).** `python3 -m unittest discover -s tests -v` (unit tests + GUI scenarios).
- **F-034 · Static analysis (done).** `tests/static_checks.sh` runs pyflakes, bandit and shellcheck; all clean.
- **F-035 · Security: see SECURITY.md** for the review and remaining risks.
- **F-032 · Licence and maintainer (done: MIT; set DEB_MAINTAINER when building packages).** Set the GitHub link in `ytdlp_gtk/config.py` (`GITHUB_URL`) once the repository exists.
- **F-033 · Translations (P3).**

## Before the AppImage (release checklist)
- [ ] Bugs B-004 and B-006 confirmed fixed or closed.
- [ ] F-001 layout settled, F-002 updater done, F-032 licence chosen (MIT).
- [ ] Decide whether to bundle a JavaScript runtime (deno ≈ 100 MB, or quickjs, much smaller).
- [ ] Bump `VERSION` in `main.py`; `packaging/build-appimage.sh`; `dist/*.AppImage --selftest`.
- [ ] Try it on a second machine / clean user account.
- [ ] Optional: AppStream metadata, then submit to AppImageHub.
