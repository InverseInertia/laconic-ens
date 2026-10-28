"""Opened sheets: the worksheet files this server's windows were opened on, and which of them the
page may write back to.

    sheets.start(path)        the program was started with this sheet (`lens --window FILE`)
    sheets.serve(open_window) how to open a browser window on a path of this server, when serving
    sheets.hand(path)         another launch handed its sheet over (or None, no sheet): the path of
                              the window to open for it, "/?sheet=TOKEN"
    sheets.show(path)         opens that window; False when this server opens no windows
    sheets.get(sheet)         the file a window opened on: the start file for a window without
                              ?sheet=, a handed-over one for its token, else None
    writable(path)            whether the page may write the file back

A token is not guessable, so no other page can ask for a handed-over file. Only a .lens file is
written back; a .cs or .txt file is read but never overwritten, as savefile.js does for a file
the browser opened."""
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

    def get(self, sheet=None):
        return self._start if sheet is None else self._handed.get(sheet)


sheets = Opened()
