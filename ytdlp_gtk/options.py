"""Static tables: audio/video choices, extra yt-dlp options, browsers, progress template."""


AUDIO_FORMAT = [
    ("best", "Best", "Keep the original audio stream without re-encoding. Highest quality, fastest."),
    ("mp3", "MP3", "Convert to MP3. Plays everywhere; lossy."),
    ("m4a", "M4A", "Convert to M4A/AAC. Good quality for its size; works on Apple devices."),
    ("opus", "Opus", "Convert to Opus. Best quality per bit among lossy formats."),
    ("flac", "FLAC", "Convert to FLAC. Lossless, large files."),
    ("wav", "WAV", "Convert to uncompressed WAV. Largest files."),
]


AUDIO_QUALITY = [
    ("0", "Best", "Highest quality / bitrate the encoder offers (VBR 0)."),
    ("2", "High", "High quality, noticeably smaller than Best (VBR 2)."),
    ("5", "Medium", "Balanced quality and size (VBR 5)."),
    ("9", "Low", "Smallest files, lowest quality (VBR 9)."),
]


VIDEO_RES = [
    ("best", "Best available", "Download the highest resolution offered."),
    ("2160", "2160p", "Up to 4K Ultra HD, if the video provides it."),
    ("1440", "1440p", "Up to 2K / QHD."),
    ("1080", "1080p", "Up to Full HD."),
    ("720", "720p", "Up to HD."),
    ("480", "480p", "Standard definition."),
    ("360", "360p", "Low resolution, smallest files."),
]


VIDEO_CONTAINER = [
    ("best", "Original", "Keep whatever container yt-dlp picks (usually mkv or webm)."),
    ("mp4", "MP4", "Most compatible container for players and devices."),
    ("mkv", "MKV", "Flexible container that holds any codec."),
    ("webm", "WebM", "Open web format (VP9/AV1 + Opus)."),
]


MODES = [
    ("audio", "Audio only", "Download only the best audio, using the Audio tab settings."),
    ("video", "Video only", "Download the video stream without sound, using the Video tab settings."),
    ("both", "Video + Audio", "Download best video and best audio merged into one file (Video tab settings)."),
]


SUB_LANGS = [
    ("en", "🇬🇧", "English"), ("es", "🇪🇸", "Spanish"), ("fr", "🇫🇷", "French"),
    ("de", "🇩🇪", "German"), ("it", "🇮🇹", "Italian"), ("pt", "🇵🇹", "Portuguese"),
    ("nl", "🇳🇱", "Dutch"), ("sv", "🇸🇪", "Swedish"), ("pl", "🇵🇱", "Polish"),
    ("tr", "🇹🇷", "Turkish"), ("ru", "🇷🇺", "Russian"), ("uk", "🇺🇦", "Ukrainian"),
    ("ar", "🇸🇦", "Arabic"), ("hi", "🇮🇳", "Hindi"), ("zh", "🇨🇳", "Chinese"),
    ("ja", "🇯🇵", "Japanese"), ("ko", "🇰🇷", "Korean"),
]


SUB_NAMES = {c: f"{f} {n}" for c, f, n in SUB_LANGS} | {"all": "🌐 All languages"}


def _locs(snap, rel, flatpak):
    """Standard, snap (common/current) and Flatpak profile locations of a Chromium-style browser."""
    return [f"~/.config/{rel}", f"~/snap/{snap}/common/.config/{rel}", f"~/snap/{snap}/current/.config/{rel}",
            f"~/.var/app/{flatpak}/config/{rel}"]


BROWSERS = [      # key (yt-dlp name), label, profile locations to look for
    ("firefox", "Firefox", ["~/.mozilla/firefox", "~/.config/mozilla/firefox", "~/snap/firefox/common/.mozilla/firefox",
                            "~/.var/app/org.mozilla.firefox/.mozilla/firefox",
                            "~/.var/app/org.mozilla.firefox/config/mozilla/firefox"]),
    ("chrome", "Google Chrome", _locs("google-chrome", "google-chrome", "com.google.Chrome")),
    ("chromium", "Chromium", _locs("chromium", "chromium", "org.chromium.Chromium") + ["~/snap/chromium/common/chromium"]),
    ("brave", "Brave", _locs("brave", "BraveSoftware/Brave-Browser", "com.brave.Browser")),
    ("edge", "Microsoft Edge", _locs("microsoft-edge", "microsoft-edge", "com.microsoft.Edge")),
    ("vivaldi", "Vivaldi", _locs("vivaldi", "vivaldi", "com.vivaldi.Vivaldi")),
    ("opera", "Opera", _locs("opera", "opera", "com.opera.Opera")),
]


YTDLP_KNOWS = {"firefox": {"~/.mozilla/firefox", "~/snap/firefox/common/.mozilla/firefox",
                           "~/.var/app/org.mozilla.firefox/.mozilla/firefox",
                           "~/.var/app/org.mozilla.firefox/config/mozilla/firefox"}}


COOKIE_OPTIONS = []        # filled in below, once browser_location() exists


CRED_NEEDLES = ("sign in to confirm", "not a bot", "login required", "confirm your age", "age-restricted",
                "private video", "members-only", "join this channel", "this video is private",
                "sign in to view", "sign in if you've been granted")


TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


OFF = ("off", "Off", "Don't do this (yt-dlp default).")


ON = ("on", "On", "Enable this option.")


EXTRA_OPTIONS = [
    ("playlist", "Playlists", [
        ("single", "Single video", "If the link is in a playlist, download only that video."),
        ("all", "Whole playlist", "Download every video in the playlist the link belongs to."),
    ], "single"),
    ("embed_thumb", "Embed thumbnail in file", [OFF, ("on", "On", "Embed the thumbnail as cover art inside the media file.")], "off"),
    ("embed_meta", "Embed metadata", [OFF, ("on", "On", "Write title, artist, date and description tags into the file.")], "off"),
    ("subs", "Subtitles",
     [(c, f, f"{n} subtitles, including auto-generated ones.") for c, f, n in SUB_LANGS] +
     [("all", "🌐", "Every available subtitle language.")], "off"),
    ("embed_subs", "Embed subtitles in video", [OFF, ("on", "On", "Mux downloaded subtitles into the video file (needs a subtitle choice above).")], "off"),
    ("sponsorblock", "SponsorBlock", [
        ("off", "Off", "Leave sponsor segments in."),
        ("mark", "Mark as chapters", "Mark sponsor, intro and outro segments as chapters."),
        ("remove", "Remove sponsors", "Cut sponsor segments out of the file (re-encodes cuts)."),
    ], "off"),
    ("split", "Split by chapters", [OFF, ("on", "On", "Also save each chapter as a separate file.")], "off"),
    ("description", "Save description", [OFF, ("on", "On", "Save the video description to a .description text file.")], "off"),
    ("infojson", "Save info JSON", [OFF, ("on", "On", "Save all metadata to a .info.json file.")], "off"),
    ("filenames", "Filenames", [
        ("normal", "Normal", "Use the video title as-is for the file name."),
        ("safe", "Underscores", "Replaces spaces with underscores and strips special characters. Leave on Normal for clean, readable file names."),
    ], "normal"),
    ("rate", "Speed limit", [
        ("none", "Unlimited", "Download at full speed."),
        ("1M", "1 MB/s", "Limit the download to about 1 MB/s."),
        ("5M", "5 MB/s", "Limit the download to about 5 MB/s."),
    ], "none"),
    ("cookies", "Cookies", COOKIE_OPTIONS, "none"),
    ("mtime", "File modified date", [
        ("upload", "Upload date", "Set the file's modified time to the video's upload date (yt-dlp default)."),
        ("now", "Download time", "Leave the modified time as the moment of download."),
    ], "upload"),
    ("overwrite", "Existing files", [
        ("skip", "Skip", "Don't re-download files that already exist (yt-dlp default)."),
        ("overwrite", "Overwrite", "Replace files that already exist."),
    ], "skip"),
]


EXTRA_ARGS = {
    ("playlist", "single"): ["--no-playlist"],
    ("playlist", "all"): ["--yes-playlist"],
    ("embed_thumb", "on"): ["--embed-thumbnail"],
    ("embed_meta", "on"): ["--embed-metadata"],
    ("embed_subs", "on"): ["--embed-subs"],
    ("sponsorblock", "mark"): ["--sponsorblock-mark", "all"],
    ("sponsorblock", "remove"): ["--sponsorblock-remove", "sponsor"],
    ("split", "on"): ["--split-chapters"],
    ("description", "on"): ["--write-description"],
    ("infojson", "on"): ["--write-info-json"],
    ("filenames", "safe"): ["--restrict-filenames"],
    ("rate", "1M"): ["--limit-rate", "1M"],
    ("rate", "5M"): ["--limit-rate", "5M"],
    ("mtime", "now"): ["--no-mtime"],
    ("overwrite", "overwrite"): ["--force-overwrites"],
}


PROGRESS_TEMPLATE = ("download:[PROG]%(progress.status)s|%(progress._percent_str)s|"
                     "%(progress._total_bytes_str)s|%(progress._total_bytes_estimate_str)s|"
                     "%(progress._speed_str)s|%(progress._eta_str)s")


PP_PREFIXES = ("[Merger]", "[ExtractAudio]", "[VideoRemuxer]", "[EmbedThumbnail]", "[Metadata]",
               "[SponsorBlock]", "[ModifyChapters]", "[SplitChapters]", "[EmbedSubtitle]",
               "[FixupM3u8]", "[ThumbnailsConvertor]", "[MoveFiles]")


NA = ("", "NA", "N/A", "Unknown", "Unknown B", "Unknown B/s")


TITLE_TIPS = {
    "cookies": "Reuses your browser's login for age-restricted, private or bot-checked videos. Choosing a "
               "browser starts a short setup that saves a copy of its cookies in ~/.config/ytdlp-gtk/ "
               "(readable only by you).",
    "subs": "Select as many languages as you like; no flag selected means no subtitles. "
            "Dimmed flags aren't offered by the selected video.",
}
