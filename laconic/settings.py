"""Per-user settings kept on the machine running the server, so they follow the
user across browsers and are shared with the command line: the Greek table
behind Ctrl+G, the global unit definitions, whether the welcome dialog has been shown and the
page's display preferences (PREFS). Kept here rather than in the browser, whose storage belongs
to one origin and so to one port, so the page looks the same whatever port LENS runs on.

The file is JSON, written atomically. `LENS_CONFIG_DIR` overrides where it lives."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()

# The page's display preferences: what each holds is the page's business (theme.js checks a theme).
PREFS = ("theme", "view", "wrap", "wrapText", "markGlobals", "mathkeys", "suggest", "layout", "autoLayout", "layoutAsk")


def config_dir():
    if os.environ.get("LENS_CONFIG_DIR"):
        return Path(os.environ["LENS_CONFIG_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "laconic"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "laconic"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "laconic"


def _path():
    return config_dir() / "settings.json"


def load():
    """{"welcomed": bool, "greek": dict or None, "units": [{"name", "definition"}], "prefs": dict}.
    A missing or unreadable file gives the defaults rather than an error."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    greek = data.get("greek")
    units = data.get("units")
    prefs = data.get("prefs")
    return {
        "welcomed": data.get("welcomed") is True,
        "greek": greek if isinstance(greek, dict) else None,
        "units": [u for u in units if isinstance(u, dict) and isinstance(u.get("name"), str)
                  and isinstance(u.get("definition"), str)] if isinstance(units, list) else [],
        "prefs": {k: v for k, v in prefs.items() if k in PREFS} if isinstance(prefs, dict) else {},
    }


def _write(data):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_greek(greek):
    """`None` goes back to the built-in table."""
    with _lock:
        data = load()
        data["greek"] = greek
        _write(data)


def save_units(units):
    with _lock:
        data = load()
        data["units"] = [{"name": n, "definition": d} for n, d in units]
        _write(data)


def save_welcomed():
    """The welcome dialog has been shown once on this machine."""
    with _lock:
        data = load()
        data["welcomed"] = True
        _write(data)


def save_prefs(changes):
    """Merges `changes` into the stored preferences; None removes one. Other keys are ignored."""
    with _lock:
        data = load()
        for k, v in changes.items():
            if k not in PREFS:
                continue
            if v is None:
                data["prefs"].pop(k, None)
            else:
                data["prefs"][k] = v
        _write(data)


def global_units():
    """(name, definition) pairs, in definition order."""
    return [(u["name"], u["definition"]) for u in load()["units"]]
