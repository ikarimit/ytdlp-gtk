yt-dlp release signing key
==========================
Fingerprint: AC0C BBE6 848D 6A87 3464  AF4E 57CF 6593 3B5A 7581
Owner:       Simon Sawicki (yt-dlp signing key) <contact@grub4k.xyz>

yt-dlp-release.asc  the public key as published in the yt-dlp repository (public.key)
yt-dlp-release.gpg  the same key as a binary keyring, the format `gpgv` reads

Checked on 2026-10-03 against two independent sources (the yt-dlp repository and keys.openpgp.org, by
fingerprint) and against the signature of release 2026.08.19.
If yt-dlp ever rotates its key, replace both files and the fingerprint in ytdlp_gtk/updater.py after
confirming it in the yt-dlp README (the "public key" link) and on a keyserver.
