# Bugs

Status: **open** · **fixed** (in the working tree, not yet released) · **external** (not this app) · **needs-check** (could not reproduce, please confirm)
Newest first. Add the version where it was found/fixed when releases start.

## B-001 · Pinning an app to the dock freezes GNOME Shell 50.1 — external
- **What happened:** on one machine, dragging any app onto the dock locked the desktop and needed a hard reset.
- **Cause (from `journalctl -b -1`):** a GNOME Shell 50.1 bug, not this app. Adding a favourite runs
  `AppFavorites._addFavorite` → app-grid `_redisplay`, which throws `Cannot add … to page 1` over and over when the
  app grid contains a broken entry (in this case a leftover snap launcher).
- **If you see it:** check `journalctl -b -1 | grep "Cannot add"` for the broken entry, remove or repair that app, log out
  and back in, and pin once with unsaved work closed.
- **App side:** nothing to fix.

## B-010 · Cookies stopped working after a while — fixed
- **Cause:** a saved copy of browser cookies goes stale because YouTube rotates account cookies while the browser is open.
  Verified: a saved copy was rejected ("Sign in to confirm your age") hours later while a live read from
  the same Chromium and from Firefox worked.
- **Fix:** browser cookies are now read live for every lookup and download; nothing is copied or stored. Only an imported
  cookies.txt is kept (keyring). Old copies are deleted on start. See SECURITY.md.

## B-011 · AppImage did not look or behave like the script — fixed
- linuxdeploy's GTK hook forced `GTK_THEME=Adwaita:dark` (lost the pink accent and icon theme) and `GDK_BACKEND=x11`
  (XWayland). The AppImage no longer uses that hook. `tests/parity.py` now compares both side by side: 19 environment checks
  (versions, font, icon/cursor theme, dark mode, accent, keyring, yt-dlp, ffmpeg, gpgv, node, sound player, window size)
  plus a pixel comparison of the window (0.00% different with the same renderer).

## B-002 · No way to remove failed downloads — fixed
- Select rows and press Delete to remove them (the trash button was dropped; the **Clear ▾** menu covers the rest).
  Running rows are kept with a message. **Clear ▾**: Completed / Failed / Stopped. A removed row that was still
  waiting never starts.

## B-003 · Debug log tab opened at the top instead of the newest line — fixed
- The log views now follow new lines (pause while you scroll up to read, resume when you return to the bottom).
  The Debug log tab always opens at its end.

## B-004 · Log side scrollbar "disappears" after a download starts — needs-check
- Could not reproduce: screenshots during and after a real download show the scrollbar.
- Likely causes found and fixed: very low-contrast scrollbar, a log that did not follow wrapped lines,
  and fading overlay scrollbars on the outer page. All scrollbars are now classic and high-contrast.
- If it still happens, note which scrollbar (Log, Debug log, queue or whole page) and what you did just before.

## B-005 · Log did not follow the last line when text wrapped — fixed
- Fixed together with B-003.

## B-006 · Window once asked for 1750 px width on a 1080 px portrait monitor — needs-check
- Seen once in the journal (2026-10-03 11:52). Measured minimum width is 894 px, so it is probably a one-off
  during testing. If a window ever comes up wider than the screen, write down the monitor and saved size
  (`~/.config/ytdlp-gtk/settings.json` → `size`).

## B-008 · Loading settings stopped at the first missing key — fixed
- Found by the new tests: a settings file without `folder` aborted loading (an empty path counted as the current
  folder). Loading now checks every value's type.

## B-009 · yt-dlp updater could not read the release name — fixed
- Found by testing against GitHub: the redirect no longer contains the tag. The release is now read from
  `/releases/latest`.

## B-007 · Some thumbnails in a playlist never load — external
- Videos that no longer exist on YouTube return 404 for their thumbnail; those tiles stay blank. Cosmetic.

## Known limitations (not bugs)
- AppImage is built from this machine's libraries: runs on the same or newer distributions only.
- No JavaScript runtime is bundled; age-restricted YouTube videos need node or deno on the system.
- An AppImage's bundled yt-dlp is read-only, but the in-app updater keeps its own copy in `~/.local/share/ytdlp-gtk/`, which takes priority.
- The AppImage uses the default Adwaita accent (blue), not the desktop's accent colour.

## Not yet verified
- Real cookie import from Firefox (snap) and Chromium (snap): files were created, age-restricted fetch worked;
  other browsers (Chrome, Brave, Edge, Vivaldi, Opera) untested.
- Parallel downloads above 2 and playlists above ~200 videos.
