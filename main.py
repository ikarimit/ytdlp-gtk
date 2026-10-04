#!/usr/bin/env python3
"""yt-dlp GTK launcher: the application itself lives in the ytdlp_gtk package next to this file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ytdlp_gtk.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
