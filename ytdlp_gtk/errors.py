"""Explaining yt-dlp errors in plain language; log-line colouring helpers."""
import re

from .options import CRED_NEEDLES


BAD_LINE = re.compile(r"^(ERROR|WARNING)\b|^\[(import|fetch|export) failed")


def is_bad(line):
    return bool(BAD_LINE.match(line.strip()))


def needs_credentials(text):
    low = (text or "").lower()
    return any(n in low for n in CRED_NEEDLES)


ERROR_HELP = [
    (("ffmpeg is not installed", "ffprobe and ffmpeg not found", "ffmpeg not found", "ffprobe not found",
      "requested merging of multiple formats"),
     ("ffmpeg is missing. It is needed to merge video and audio, convert audio, or embed subtitles.",
      "Install it (Ubuntu/Debian: sudo apt install ffmpeg), then press Retry.")),
    (("sign in to confirm", "not a bot", "login required", "confirm your age", "age-restricted",
      "private video", "members-only", "join this channel"),
     ("The site wants a signed-in account (bot check, age restriction, or a private / members-only video).",
      "Open the Options tab, set Cookies to the browser where you're logged in, then Retry. If you already did, "
      "check that this account is signed in and age-verified on the site.")),
    (("not available in your country", "blocked it", "geo", "video unavailable", "this video is not available",
      "has been removed", "no longer available", "is unavailable", "does not exist"),
     ("The video was removed, is private, or is blocked in your region.",
      "Open the link in your browser to check it still plays. If it's region-locked, use a VPN; if it's private, try cookies from your browser.")),
    (("http error 429", "too many requests"),
     ("The site is rate-limiting you because of too many requests.",
      "Wait a few minutes, set Simultaneous downloads to 1, and optionally add a Speed limit in the Options tab. Then Retry.")),
    (("http error 403", "forbidden"),
     ("The site refused the request (blocked, expired link, or yt-dlp is out of date).",
      "Update yt-dlp, try Cookies from browser in the Options tab, and lower Simultaneous downloads. Then Retry.")),
    (("http error 404",),
     ("The page or file no longer exists (404).", "Check the link in your browser; it may be deleted or mistyped.")),
    (("requested format is not available", "requested format not available"),
     ("The resolution or container you chose isn't offered for this video.",
      "On the Video tab set Resolution to Best available and Container to Original, then Retry.")),
    (("no space left",),
     ("The disk is full.", "Free some space or choose another Download folder, then Retry.")),
    (("permission denied", "read-only file system"),
     ("The app isn't allowed to write to that folder.", "Choose a Download folder you own (for example inside your home folder).")),
    (("temporary failure in name resolution", "network is unreachable", "timed out", "connection reset",
      "connection refused", "unable to download webpage", "remote end closed", "incompleteread", "getaddrinfo",
      "urlopen error"),
     ("The connection to the site failed or dropped.",
      "Check your internet connection, then press Start or Retry. Partial downloads continue where they stopped.")),
    (("unsupported url",),
     ("yt-dlp doesn't recognise this link as a video page.",
      "Check the link points to a single video. If it's a supported site, update yt-dlp.")),
    (("javascript runtime", "n challenge", "nsig"),
     ("YouTube needs a JavaScript runtime that isn't installed.",
      "Install deno (or node: sudo apt install nodejs), then restart the app and Retry.")),
    (("unable to extract", "unable to download video data", "extractor error", "sign in"),
     ("yt-dlp couldn't read the page, which usually means the site changed.",
      "Update yt-dlp to the latest version, then Retry.")),
    (("could not move",),
     ("The finished files couldn't be moved to your chosen folder.",
      "Pick another folder under 'Move when finished'. The download itself is safe in the Download folder.")),
]


def explain_error(text, code):
    low = text.lower()
    for needles, (why, fix) in ERROR_HELP:
        if any(n in low for n in needles):
            return why, fix
    return (f"yt-dlp stopped with an error (exit code {code}).",
            "Check the Log for the full output, then press Retry. If it keeps failing, update yt-dlp.")
