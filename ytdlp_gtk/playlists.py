"""Playlist entry helpers."""
import re

from .security import valid_url


def is_playlist(info):
    return bool(info) and info.get("_type") == "playlist" and bool(info.get("entries"))


def entry_url(e):
    """The video link of a playlist entry, or "" if it is not a plain http(s) URL (data from the web is untrusted)."""
    u = e.get("url") or e.get("webpage_url") or ""
    if not valid_url(u) and e.get("id") and "youtube" in (e.get("ie_key") or "").lower() \
            and re.fullmatch(r"[\w-]{6,20}", str(e["id"])):
        u = f"https://www.youtube.com/watch?v={e['id']}"
    return valid_url(u) or ""


def new_state():
    return {"off": set(), "thumbs": set()}      # unticked videos; videos whose thumbnail is wanted


def entry_thumb(e):
    """A small jpg thumbnail URL for a playlist entry."""
    ok = (".jpg", ".jpeg", ".png")
    ths = sorted((t for t in (e.get("thumbnails") or []) if t.get("url")), key=lambda t: t.get("width") or 0)
    for t in ths:
        if (t.get("width") or 0) >= 160 and t["url"].split("?")[0].lower().endswith(ok):
            return t["url"]
    for t in ths:
        if t["url"].split("?")[0].lower().endswith(ok):
            return t["url"]
    if e.get("id") and "youtube" in (e.get("ie_key") or "").lower():
        return f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"
    return ""
