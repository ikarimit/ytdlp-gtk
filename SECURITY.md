# Security notes

Review dates: 2026-10-03 (full read-through) and a second pass the same day for cookies, updates and third-party code.
Checked by reading all of the code and exercising it with tests (`python3 -m unittest discover -s tests`).
This is a careful self-review, not an independent audit, backed by static analysis (`tests/static_checks.sh`):
pyflakes (bugs), bandit (security) and shellcheck (scripts) are all clean. bandit's first run found 4 medium items,
all fixed or reviewed: redirects could lead to `ftp:`, the downloaded yt-dlp was mode 0755 (now 0700), and the RAM
scratch folder in the shared `/dev/shm` fallback now has to be a real folder owned by you (no symlink or folder prepared
by someone else). The remaining 13 low notes are "subprocess is used", always with argument lists, never a shell.
Debian's bandit cannot parse with Python 3.14, so the script runs it under python3.11.

## Privileges
- The app never uses `sudo`, `pkexec`, setuid files, polkit or system folders. It runs entirely as the logged-in user.
- It writes only to: `~/.config/ytdlp-gtk/` (0700), `~/.local/share/ytdlp-gtk/` (0700, the updated yt-dlp), the
  download folder, and the "move to" folder you choose.
- The `.deb` installs root-owned files (0755/0644) under `/usr`; nothing in it runs code at install time (no maintainer scripts).

## What could go wrong, and what stops it
| Risk | Where it could happen | Protection |
|---|---|---|
| **Argument injection**: a pasted/imported "link" such as `--exec <command>` becomes a yt-dlp option and runs a program | URL box, imported files, dropped text, playlist entries returned by a website | `security.valid_url()` accepts only http(s) URLs with no spaces/control characters and never one starting with `-`; every command ends with `--` before the link; playlist entry URLs are validated the same way |
| **Tampered saved queue / settings** (`settings.json`) causing an arbitrary command to run on resume | start-up, Start button | Every command is re-checked by `security.validate_cmd()` before it runs: only options this app generates are allowed, a deny-list blocks `--exec`, `--external-downloader`, config/plugin loading, updates; rows that fail are dropped on load. Paths and statuses read from the file are type- and range-checked |
| **Path abuse when moving finished files** | "Move when finished" | Only files inside the download folder are moved (`tools.move_files` resolves paths and checks containment) |
| **Opening a hostile file by double-click** | queue rows | Opens only when the file exists and its content type is video, audio, image or subtitles; never scripts or documents |
| **Memory exhaustion / freezing** | huge URL files, cookie files, thumbnails, playlists | size limits: URL lists 2 MB, cookies 20 MB, thumbnails 5 MB, playlist entries 1000, saved queue 2000 rows, URL length 2048 |
| **Fetching local or odd resources** | thumbnails, updater | only `http(s)`; the updater accepts only `https://github.com/yt-dlp/yt-dlp/releases` and refuses a redirect to a non-https address |
| **Poisoned yt-dlp update** | updater | the release's `SHA2-256SUMS` must carry a valid GPG signature from yt-dlp's release key (pinned by fingerprint, shipped in `ytdlp_gtk/keys/`, checked with `gpgv`); the download must match the signed hash, stay under 90 MB and report the expected version before it replaces anything (atomic replace). Fails closed: no `gpgv`, no valid signature, no update |
| **Secrets readable by others** | settings, cookies, debug log, temp files | created with mode 0600 (never briefly world-readable); folders 0700; the debug log is size-limited (1 MB x 3) |
| **Orphan processes / deadlock** | closing the app mid-download | children run under `setpriv --pdeathsig TERM` (a Python `preexec_fn` was removed because it can deadlock a multi-threaded program) |
| **Shell injection** | all subprocess calls | no `shell=True`, no `os.system`, no `eval`/`exec`, no `pickle`; every call passes an argument list |

Buffer overflows: the app is pure Python (memory-safe) and uses no `ctypes`/native code of its own.
Native code that touches untrusted data is the system's: image decoding (GdkPixbuf) and yt-dlp's helpers (ffmpeg).
Keep the system updated; thumbnails are size-capped before decoding.

## Cookies
- **Browser cookies are never copied or stored.** yt-dlp reads them straight from the browser (`--cookies-from-browser`) each
  time a download or lookup needs them, and they live only in that process's memory. This is also what fixed "cookies stop
  working": YouTube rotates account cookies while a browser is open, so any saved copy goes stale (verified: a copy made
  hours earlier was rejected, a live read of the same browser worked).
- An imported **cookies.txt** is the only thing stored: filtered to the sites you list, encrypted by the system keyring
  (libsecret, same protection as your saved passwords). When a download needs it, a copy is written to a private folder on
  tmpfs (`$XDG_RUNTIME_DIR`, RAM only, 0600) and deleted when yt-dlp exits; leftovers from a crash are swept at the next start.
  Without a keyring the app falls back to a private 0600 file and says so.
- Old cookie copies from earlier versions are overwritten and deleted on first start.

## Third-party code and how it is validated against the originals
| Component | Validation |
|---|---|
| yt-dlp (updater, AppImage build) | GPG signature of `SHA2-256SUMS` against yt-dlp's release key (fingerprint `AC0C BBE6 848D 6A87 3464 AF4E 57CF 6593 3B5A 7581`, confirmed against two independent sources: the yt-dlp repository and keys.openpgp.org), then SHA-256 of the file, then the reported version |
| ffmpeg (AppImage) | taken from the installed Ubuntu package (signed by the Ubuntu archive); the build re-checks those files and their libraries against the package checksums (`dpkg --verify`) and refuses to bundle modified files. No unsigned static builds |
| Python, GTK, libadwaita, libsecret, gpgv (AppImage, .deb) | from the distribution packages |
| AppImage build tools (appimagetool, linuxdeploy + GTK plugin) | pinned by SHA-256 after the first download (trust on first use); upstream publishes no signatures for these builds |
| Self-contained yt-dlp build | it bundles its own Python and the cookie-decryption libraries, so it behaves the same from source, `.deb` and AppImage |

## Remaining risks you should know about
- **yt-dlp itself is third-party code** that downloads and parses data from websites. Keep it current (header button).
- The update check trusts GitHub's TLS for *which* release is newest; the signature then proves the files are yt-dlp's.
  A rolled-back release is refused because the downloaded file must report the version being installed.
- If yt-dlp ever rotates its signing key the updater refuses until the key in `ytdlp_gtk/keys/` is replaced (confirm the new
  fingerprint in the yt-dlp README and on a keyserver first).
- Thumbnail downloads follow HTTP redirects (http/https only) and are decoded by system libraries.
- The debug log contains links you downloaded (private permissions, rotated).
- AppImage build tools are pinned by SHA-256 after the first download (trust on first use), not by an upstream signature.

## Reporting
Add findings to `BUGS.md` (mark them **security**).
