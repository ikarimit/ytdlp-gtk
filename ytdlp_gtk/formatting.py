"""Small text formatting helpers."""
import re


def whole(text):
    """'218.53KiB' -> '219 KiB' (whole numbers keep the narrow columns tidy)."""
    m = re.match(r"~?\s*([\d.]+)\s*([A-Za-z/]+)", text)
    return f"{round(float(m[1]))} {m[2]}" if m else text


def fmt_duration(sec):
    if not sec:
        return "—"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
