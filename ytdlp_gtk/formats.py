"""Turning yt-dlp's format list into rows the user can pick from."""
import re

MAX_FORMATS = 60
_ID = re.compile(r"[\w.+\-]{1,40}")
COLUMNS = ("Quality", "Type", "Ext", "Codec", "Size")      # headings of the Formats tab (width in characters below)
WIDTHS = (8, 5, 4, 5, 7)


def format_rows(info):
    """[{id, cells, label, video, audio}] for a single video's formats, best first.

    `cells` line up with COLUMNS. Storyboards and odd ids are skipped."""
    rows = []
    for f in (info or {}).get("formats") or []:
        fid = str(f.get("format_id") or "")
        vcodec, acodec = f.get("vcodec") or "none", f.get("acodec") or "none"
        has_v, has_a = vcodec != "none", acodec != "none"
        if not _ID.fullmatch(fid) or f.get("protocol") == "mhtml" or f.get("ext") == "mhtml" or not (has_v or has_a):
            continue
        fps = f.get("fps") or 0
        quality = f"{f.get('height') or '?'}p" + (f"{int(fps)}" if fps and fps > 30 else "") if has_v else "audio"
        size = f.get("filesize") or f.get("filesize_approx")
        size_text = "" if not size else f"{round(size / 1048576)} MB" if size >= 1048576 else "<1 MB"
        kind = "both" if has_v and has_a else "video" if has_v else "audio"
        cells = (quality, kind, str(f.get("ext") or ""), (vcodec if has_v else acodec).split(".")[0], size_text)
        key = (has_v, f.get("height") or 0, f.get("tbr") or f.get("abr") or 0)
        label = f"{quality}, {kind}, {cells[2]}, {cells[3]}" + (f", {size_text}" if size_text else "")
        rows.append((key, {"id": fid, "cells": cells, "label": label, "video": has_v, "audio": has_a}))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r for _k, r in rows][:MAX_FORMATS]
