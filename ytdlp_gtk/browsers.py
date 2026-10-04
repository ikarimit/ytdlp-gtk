"""Finding browser profiles (standard, snap, Flatpak) and cookie-file helpers."""
import re
from pathlib import Path

from .options import BROWSERS, COOKIE_OPTIONS, YTDLP_KNOWS
from .security import MAX_COOKIE_FILE, read_limited


def browser_location(key, paths):
    """First profile location (standard, snap or Flatpak) that holds a cookie database, else None.
    Empty config folders left by native-messaging hosts don't count."""
    for raw in paths:
        base = Path(raw).expanduser()
        if not base.is_dir():
            continue
        pats = ["*/cookies.sqlite"] if key == "firefox" else \
               ["*/Network/Cookies", "*/Cookies", "Network/Cookies", "Cookies"]
        if any(next(base.glob(pat), None) for pat in pats):
            return raw
    return None


def where_label(raw):
    return "snap" if raw and "/snap/" in raw else "Flatpak" if raw and "/.var/app/" in raw else ""


def auto_profile(key, paths):
    """Explicit profile for a browser living where yt-dlp doesn't look ('' = let yt-dlp find it)."""
    raw = browser_location(key, paths)
    if not raw:
        return ""
    if key == "firefox":
        return "" if raw in YTDLP_KNOWS["firefox"] else str(Path(raw).expanduser())
    return "" if raw == paths[0] else profile_arg(key, raw)


def profile_arg(key, base):
    """The profile path to hand to yt-dlp for a located browser folder."""
    base = Path(base).expanduser()
    if key == "firefox":
        return str(base)
    files = [f for pat in ("*/Network/Cookies", "*/Cookies", "Network/Cookies", "Cookies") for f in base.glob(pat)]
    if not files:
        return str(base)
    d = max(files, key=lambda f: f.stat().st_mtime).parent
    return str(d.parent if d.name == "Network" else d)


COOKIE_OPTIONS[:] = ([("none", "None", "Don't use cookies.")] +
                     [(k, n, f"Use your signed-in {n} session. Choosing it starts a short cookie setup.")
                      for k, n, p in BROWSERS if browser_location(k, p)] +
                     [("file", "cookies.txt", "Use a cookies.txt file you exported from your browser.")])


def count_cookies(path):
    """Number of cookie lines in a Netscape-format cookies.txt (0 if it isn't one)."""
    try:
        lines = read_limited(path, MAX_COOKIE_FILE).splitlines()
    except (OSError, ValueError):
        return 0
    return sum(1 for l in lines if l.count("\t") >= 6 and (not l.startswith("#") or l.startswith("#HttpOnly_")))


def cookie_error_hint(stderr):
    low = stderr.lower()
    if "database is locked" in low or "could not copy" in low or "permission denied" in low:
        return "The browser has its cookie file locked. Close the browser completely, then try again."
    if "could not find" in low or "no such file" in low or "not found" in low:
        return "Couldn't find that browser's profile. Use the folder button to locate its profile folder."
    if "keyring" in low or "decrypt" in low or "secretstorage" in low or "kwallet" in low:
        return ("Your system keyring wouldn't release the browser's encryption key. Unlock it "
                "(log in to your desktop) and retry, or import a cookies.txt file instead.")
    last = [l for l in stderr.strip().splitlines() if l.strip()]
    return (last[-1] if last else "yt-dlp could not read cookies from that browser.")[:220]


DEFAULT_DOMAINS = ["youtube.com", "google.com"]
_DOMAIN = re.compile(r"[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)*\.[a-z]{2,}")


def parse_domains(text):
    """'YouTube.com, google.com' -> ['youtube.com', 'google.com'] (only valid site names, at most 20)."""
    names = [d.strip().lower().lstrip(".") for d in re.split(r"[,\s]+", text or "") if d.strip()]
    return [d for d in dict.fromkeys(names) if _DOMAIN.fullmatch(d)][:20]


def filter_cookies(text, domains):
    """Keep only the cookies of the listed sites (and their subdomains) from a Netscape cookies.txt."""
    keep = ["# Netscape HTTP Cookie File"]
    for line in text.splitlines():
        if line.startswith("#") and not line.startswith("#HttpOnly_") or not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        host = fields[0].removeprefix("#HttpOnly_").lstrip(".").lower()
        if any(host == d or host.endswith("." + d) for d in domains):
            keep.append(line)
    return "\n".join(keep) + "\n"


def count_cookie_lines(text):
    return sum(1 for l in text.splitlines()
               if l.count("\t") >= 6 and (not l.startswith("#") or l.startswith("#HttpOnly_")))
