"""Paths, app identity, logging (hidden, size-limited, private debug log) and the global exception hook."""
import logging
import logging.handlers
import os
import sys
import threading
import traceback
import warnings
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)  # Gtk.TreeView is deprecated but fine here

ICON = "local.ytdlp.gtk"
APP_ID = os.environ.get("YTDLP_GTK_APP_ID", ICON)   # override to run a second instance
APP_NAME, VERSION, CREATED = "yt-dlp GTK", "0.1.0", "3 October 2026"
AUTHOR = "yt-dlp GTK contributors"   # shown in the About dialog
GITHUB_URL = "https://github.com/ikarimit/ytdlp-gtk"   # shown in the About dialog

# Everything the app stores is private to the user (0700 folders, 0600 files).
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "ytdlp-gtk"
CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(CONFIG_DIR, 0o700)        # tighten folders created by earlier versions
DATA_DIR = Path(GLib.get_user_data_dir()) / "ytdlp-gtk"          # the updated yt-dlp lives here
DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
LOG_FILE = CONFIG_DIR / ".debug.log"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def _private_rotating_handler():
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    for f in (LOG_FILE, *LOG_FILE.parent.glob(LOG_FILE.name + ".*")):
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return handler


logging.basicConfig(handlers=[_private_rotating_handler()], level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(threadName)s: %(message)s")
log = logging.getLogger("ytdlp-gtk")


def _excepthook(*exc):
    log.critical("Uncaught exception:\n%s", "".join(traceback.format_exception(*exc)))
    sys.__excepthook__(*exc)


sys.excepthook = _excepthook
threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback)
