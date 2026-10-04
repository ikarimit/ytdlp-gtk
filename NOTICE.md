# Third-party software and legal notes

yt-dlp GTK is an independent front-end. It is not affiliated with or endorsed by yt-dlp, GNOME, Google/YouTube,
FFmpeg or any website it can download from.

| Component | How it is used | Licence |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | run as a separate program; the in-app updater downloads the official release | Unlicense (public domain) |
| yt-dlp release signing key (`ytdlp_gtk/keys/`) | public key only, used to verify updates | public key, see `keys/README.txt` |
| GTK 4, libadwaita, PyGObject | imported from the system | LGPL-2.1+ |
| libsecret, gpgv | used from the system | LGPL / GPL |
| FFmpeg | run as a separate program (not included in the source repository; the AppImage build bundles the distro's package) | LGPL/GPL depending on build |

Source code is MIT. If you distribute a binary bundle (AppImage) that contains FFmpeg, GTK and so on, you must also
honour **their** licences (offer their source, keep their notices). The source repository on its own contains none of them.

**Your use of downloads.** The app does not decide what is legal to download. Respect copyright and each site's terms of
service; download only what you have the right to keep. The authors accept no responsibility for misuse.

**Privacy.** The app has no telemetry and no account. It keeps settings, the queue and logs in your own user folders,
and stores imported cookie files in your system keyring. Nothing is sent anywhere except to the sites you download from
and to GitHub when you check for yt-dlp updates.
