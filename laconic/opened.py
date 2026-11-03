"""Opened sheets: the worksheet files this server's windows were opened on, and which of them the
page may write back to.

    sheets.start(path)        the program was started with this sheet (`lens --window FILE`)
    sheets.serve(open_window) how to open a browser window on a path of this server, when serving
    sheets.hand(path)         another launch handed its sheet over (or None, no sheet): the path of
                              the window to open for it, "/?sheet=TOKEN"
    sheets.show(path)         opens that window; False when this server opens no windows
    sheets.get(sheet)         the file a window opened on: the start file for a window without
                              ?sheet=, a handed-over one for its token, else None
    sheets.claim(path)        a token for the page to keep, so the file can be saved to again
                              after LENS is closed and opened without it (#168)
    sheets.reclaim(path, claim) a window's ?sheet= token for that file again, or None
    writable(path)            whether the page may write the file back

A token is not guessable, so no other page can ask for a handed-over file. Only a .lens file is
written back; a .cs or .txt file is read but never overwritten, as savefile.js does for a file
the browser opened.

A claim is an HMAC of the file's path under a key kept in the settings folder, so only a page
this server once served that file to can name it again; no other page can have LENS write to a
path of its choosing."""
import hashlib
import hmac
import secrets
from pathlib import Path


def writable(path):
    return path.suffix.lower() == ".lens"


class Opened:
    def __init__(self):
        self.clear()

    def clear(self):
        """Forget every sheet and the window opener."""
        self._start = None
        self._handed = {}   # token -> Path: sheets other launches handed over, each in a window of its own
        self._open = None

    def start(self, path):
        self._start = Path(path).resolve()

    def serve(self, open_window):
        self._open = open_window

    @property
    def opens_windows(self):
        return self._open is not None

    def hand(self, path):
        if not path:
            return "/?sheet="
        token = secrets.token_urlsafe(12)
        self._handed[token] = Path(path).resolve()
        return f"/?sheet={token}"

    def show(self, path):
        if self._open is None:
            return False
        self._open(path)
        return True

    def claim(self, path):
        key = _key()
        return hmac.new(key, str(Path(path).resolve()).encode(), hashlib.sha256).hexdigest() if key else None

    def reclaim(self, path, claim):
        try:
            path = Path(path).resolve()
        except (OSError, ValueError):
            return None
        good = self.claim(path)
        if not good or not isinstance(claim, str) or not hmac.compare_digest(good, claim):
            return None
        if not writable(path) or not path.is_file():
            return None
        token = secrets.token_urlsafe(12)
        self._handed[token] = path
        return token

    def get(self, sheet=None):
        return self._start if sheet is None else self._handed.get(sheet)


def _key():
    """The claim key, made the first time it is needed; None if the settings folder cannot hold it."""
    from .settings import config_dir
    return _key_in(config_dir())


def _key_in(folder):
    path = Path(folder) / "opened.key"
    try:
        return path.read_bytes()
    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        path.write_bytes(key)
        return path.read_bytes()
    except OSError:
        return None


sheets = Opened()
