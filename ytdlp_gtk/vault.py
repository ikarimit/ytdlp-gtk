"""The cookie vault: imported cookies live in the system keyring (libsecret), never as a file at rest.

- At rest: one keyring item per source (firefox, chromium, file, ...), encrypted by the login keyring.
- In use: a download that needs cookies gets a short-lived copy in a private folder on tmpfs
  ($XDG_RUNTIME_DIR, RAM only, mode 0600) which is deleted as soon as yt-dlp exits; leftovers from a crash
  are swept at the next start.
- Only cookies for the sites you list are stored (see browsers.filter_cookies).
- No keyring available (no Secret Service)? The vault falls back to a private 0600 file in the config folder
  and says so, instead of failing.
"""
import contextlib
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path

import gi

try:
    gi.require_version("Secret", "1")
    from gi.repository import GLib, Secret
except (ValueError, ImportError):          # libsecret typelib missing -> file fallback
    Secret = None

from .config import CONFIG_DIR, log
from .security import MAX_COOKIE_FILE, read_limited, write_private

KEY_RE = re.compile(r"[a-z]{2,10}")
PLACEHOLDER = re.compile(r"vault:([a-z]{2,10})")


def _private_dir(path):
    """Create `path` (0700) and prove it is a real folder owned by us, not a symlink or a folder someone else
    prepared in a shared place like /dev/shm. Raises OSError otherwise."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
        raise OSError(f"{path} is not a private folder of this user")
    os.chmod(path, 0o700)
    return path


def _runtime_base():
    """A private folder in RAM ($XDG_RUNTIME_DIR, else /dev/shm), else one under the config folder."""
    # /dev/shm is shared between users, so _private_dir proves the folder is ours before anything is written.
    for base in (os.environ.get("XDG_RUNTIME_DIR"), "/dev/shm"):  # nosec B108
        if base and os.path.isdir(base) and os.access(base, os.W_OK):
            candidate = Path(base) / ("ytdlp-gtk" if base == os.environ.get("XDG_RUNTIME_DIR") else f"ytdlp-gtk-{os.geteuid()}")
            try:
                return _private_dir(candidate)
            except OSError as e:
                log.warning("Not using %s for cookie scratch files: %s", candidate, e)
    return _private_dir(CONFIG_DIR / "tmp")


def sweep_stale_runtime():
    """Delete runtime folders of app instances that are no longer running (crash leftovers)."""
    try:
        base = _runtime_base()
    except OSError:
        return
    for d in base.iterdir():
        if d.is_dir() and d.name.isdigit():
            try:
                os.kill(int(d.name), 0)
            except ProcessLookupError:
                shutil.rmtree(d, ignore_errors=True)
            except PermissionError:
                pass


def runtime_dir():
    """This process's private scratch folder (RAM-backed when possible)."""
    return _private_dir(_runtime_base() / str(os.getpid()))


@contextlib.contextmanager
def temp_file(prefix="tmp-"):
    """A private, empty scratch file path that is removed afterwards."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".txt", dir=runtime_dir())      # mkstemp: created 0600
    os.close(fd)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


class Vault:
    def __init__(self, schema_name="local.ytdlp.gtk.Cookies"):
        self._mode = None
        self.schema = None
        if Secret is not None:
            self.schema = Secret.Schema.new(schema_name, Secret.SchemaFlags.NONE,
                                            {"key": Secret.SchemaAttributeType.STRING})

    # --- which storage is in use -------------------------------------------------------
    def mode(self):
        """'keyring' if a Secret Service answers, else 'file'."""
        if self._mode is None:
            self._mode = "file"
            if self.schema is not None:
                try:
                    Secret.Service.get_sync(Secret.ServiceFlags.NONE, None)
                    self._mode = "keyring"
                except GLib.Error as e:
                    log.warning("No keyring available (%s); cookies will use a private file instead", e.message)
        return self._mode

    @staticmethod
    def _check(key):
        if not KEY_RE.fullmatch(key):
            raise ValueError(f"bad cookie source name {key!r}")

    def _file(self, key):
        return CONFIG_DIR / f"cookies-{key}.txt"

    # --- storage ----------------------------------------------------------------------------
    def store(self, key, text):
        self._check(key)
        if len(text.encode()) > MAX_COOKIE_FILE:
            raise ValueError("cookie data is too large")
        if self.mode() == "keyring":
            ok = Secret.password_store_sync(self.schema, {"key": key}, Secret.COLLECTION_DEFAULT,
                                            f"yt-dlp GTK cookies ({key})", text, None)
            if not ok:
                raise RuntimeError("the keyring refused to store the cookies")
        else:
            write_private(self._file(key), text)

    def load(self, key):
        self._check(key)
        if self.mode() == "keyring":
            try:
                return Secret.password_lookup_sync(self.schema, {"key": key}, None)
            except GLib.Error as e:
                log.error("Keyring lookup failed: %s", e.message)
                return None
        f = self._file(key)
        return read_limited(f, MAX_COOKIE_FILE) if f.exists() else None

    def has(self, key):
        return self.load(key) is not None

    def forget(self, key):
        self._check(key)
        if self.mode() == "keyring":
            with contextlib.suppress(GLib.Error):
                Secret.password_clear_sync(self.schema, {"key": key}, None)
        with contextlib.suppress(OSError):
            self._file(key).unlink()

    # --- use -----------------------------------------------------------------------------------
    @contextlib.contextmanager
    def resolve(self, cmd):
        """Yield `cmd` with any `--cookies vault:KEY` replaced by a short-lived private file path."""
        cmd = list(cmd)
        path_cm = None
        for i, tok in enumerate(cmd[:-1]):
            m = tok == "--cookies" and PLACEHOLDER.fullmatch(cmd[i + 1])
            if m:
                text = self.load(m[1])
                if text is None:
                    log.warning("Saved cookies %r are missing; running without them", m[1])
                    del cmd[i:i + 2]
                else:
                    path_cm = temp_file("cookies-")
                    path = path_cm.__enter__()
                    write_private(path, text)
                    cmd[i + 1] = path
                break
        try:
            yield cmd
        finally:
            if path_cm is not None:
                path_cm.__exit__(None, None, None)

    def shred_file(self, path):
        """Best-effort overwrite then delete (used when moving an old cookie file into the keyring)."""
        try:
            size = os.path.getsize(path)
            with open(path, "r+b") as f:
                f.write(b"\0" * size)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass
        with contextlib.suppress(OSError):
            os.unlink(path)
