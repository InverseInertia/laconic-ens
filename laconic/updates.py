"""Telling the user about a newer release, and installing it (#134).

The check asks the GitHub releases API once per run, in a background thread with a short timeout,
and keeps the answer for the rest of the run. It never raises: offline, or on any odd answer, there
is simply no update. Drafts, prereleases and tags that are not `vX.Y.Z` (the Linux installer's
`installer-vX.Y.Z` tags) are not releases of LENS. A source checkout (`0+dev`) is never told to
update.

What **Update** does depends on how this copy of LENS was installed (`Place`):

- `wizard`: the Windows program the Inno Setup wizard installed (`packaging/lens.iss`; its
  uninstaller is beside `lens.exe`). The release's `...-windows-x64-install-wizard.exe` is
  downloaded and started, and LENS exits so the wizard can replace its files.
- `script`: the Linux program `install-linux.sh` installed, which keeps a copy of itself in the
  install folder. That copy is run for the release (from a temporary folder, since it replaces the
  install folder), and LENS is started again once it has finished; its output goes to `LOG`.
- `manual`: anything else (pip, a source checkout, a program unpacked by hand, a Linux program an
  installer older than 2.2.0 installed, which kept no copy of itself). The dialog says how
  to update and links to the release.

The network, the download, starting a process and exiting are the `Updater`'s seams, so the tests
run all of it without a network or an installer."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ._version import __version__, label

REPO = "InverseInertia/laconic-ens"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
RELEASES = f"https://github.com/{REPO}/releases"
TIMEOUT = 5.0        # seconds for the release lookup
DOWNLOAD_TIMEOUT = 60.0
SCRIPT = "install-linux.sh"   # the copy install-linux.sh keeps of itself in the install folder
WIZARD_SUFFIX = "-windows-x64-install-wizard.exe"
LOG = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "laconic-lens" / "update.log"
# Run by `sh -c` for a Linux update: wait (up to 20 s) for this LENS to exit, so the new one does not
# hand its window to it, run the installer, then start LENS again: the new one, or the old one if the
# installer failed (it changes nothing when it fails). $1 pid, $2 script, $3 version, $4 log, $5 program.
RELAUNCH = ('i=0; while kill -0 "$1" 2>/dev/null && [ $i -lt 40 ]; do sleep 0.5; i=$((i+1)); done; '
            'sh "$2" --release "$3" >"$4" 2>&1; exec "$5" --window')

_TAG = re.compile(r"^v(\d+(?:\.\d+)*)$")


def parse(version):
    """(0, 4, 5) for "0.4.5" or "v0.4.5"; None for a dev, prerelease or otherwise odd version."""
    m = _TAG.match(version if version.startswith("v") else "v" + version)
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def _key(parts):
    """Compare 0.5 with 0.5.0 as equal: trailing zeros do not count."""
    parts = list(parts)
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(version, current=__version__):
    """True when `version` is a later release than `current`. A dev or unstamped `current`
    never is behind, so a source checkout is not told to update."""
    a, b = parse(version), parse(current)
    return a is not None and b is not None and _key(a) > _key(b)


def latest(releases):
    """The newest release of LENS among the API's answer: not a draft, not a prerelease, tagged
    vX.Y.Z. None when there is none."""
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        tag = r.get("tag_name")
        v = parse(tag) if isinstance(tag, str) and tag.startswith("v") else None
        if v is not None and (best is None or _key(v) > _key(best[0])):
            best = (v, r)
    return best and best[1]


@dataclass(frozen=True)
class Place:
    """How this copy of LENS was installed: `kind` is wizard, script or manual (see the module
    docstring); `folder` the program's folder, `exe` the program; `note` what to do instead, for a
    copy that cannot update itself."""
    kind: str
    folder: Path | None = None
    exe: Path | None = None
    note: str | None = None


# A Linux program installed before the installer kept a copy of itself (installer 2.2.0).
LINUX_AGAIN = ("This copy of LENS was installed by an older Linux installer, which did not keep a copy of "
               "itself for Update. Run the installer again (sh lens-install-linux-v2.sh, from the release "
               "page) to update; from then on, Update works from inside LENS.")


def place(frozen=None, platform=sys.platform, exe=sys.executable):
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    if not frozen:
        return Place("manual")
    exe = Path(exe)
    folder = exe.parent
    if platform == "win32" and any(folder.glob("unins*.exe")):
        return Place("wizard", folder, exe)
    if platform.startswith("linux") and (folder / SCRIPT).is_file():
        return Place("script", folder, exe)
    if platform.startswith("linux") and (folder / "version").is_file():   # written by install-linux.sh
        return Place("manual", folder, exe, LINUX_AGAIN)
    return Place("manual", folder, exe)


def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"LENS/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _download(url, to, timeout=DOWNLOAD_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": f"LENS/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as res, open(to, "wb") as f:
        shutil.copyfileobj(res, f)


def _env():
    """The environment for a program LENS starts, without the frozen build's own libraries
    (see __main__._browser_env)."""
    from .__main__ import _browser_env
    return _browser_env()


def _spawn(cmd):
    """Start `cmd` on its own, so it outlives LENS."""
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, close_fds=True, creationflags=flags)
    else:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=_env(), start_new_session=True, close_fds=True)


def _exit_soon(delay=1.5):
    """Leave once the page has its answer, stopping the solver worker first so no file of the
    install folder stays in use."""
    def leave():
        try:
            from .solverjobs import jobs
            jobs.shutdown()
        finally:
            os._exit(0)
    threading.Timer(delay, leave).start()


class Updater:
    """One run's update check and the Update action. `check()` starts the lookup (once) and
    returns at once; `result(wait)` gives the update, waiting up to `wait` seconds for the lookup."""

    def __init__(self, fetch=_fetch, download=_download, spawn=_spawn, exit=_exit_soon, where=None,
                 current=__version__):
        self._fetch, self._download, self._spawn, self._exit = fetch, download, spawn, exit
        self._where = where
        self.current = current
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._thread = None
        self._release = None

    @property
    def where(self):
        if self._where is None:
            self._where = place()
        return self._where

    def check(self):
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._look, daemon=True, name="lens-update-check")
                self._thread.start()

    def _look(self):
        try:
            if parse(self.current) is None:   # a source checkout: nothing to compare with, so no lookup
                return
            r = latest(self._fetch(API, TIMEOUT))
            if r is not None and is_newer(r["tag_name"], self.current):
                self._release = r
        except Exception:   # offline, rate limited, an odd answer: no update, and no fuss
            pass
        finally:
            self._done.set()

    def result(self, wait=0.0):
        """{"checking": bool, "update": None or the update as the page shows it}."""
        self.check()
        done = self._done.wait(wait)
        return {"checking": not done, "update": self.describe(self._release) if done and self._release else None}

    def describe(self, r):
        from .changelog import markdown
        tag = r["tag_name"]
        kind = self.where.kind
        if kind == "wizard" and not self._wizard(r):
            kind = "manual"
        return {
            "version": tag[1:],
            "label": tag,
            "current": label(self.current),
            "url": r.get("html_url") or f"{RELEASES}/tag/{tag}",
            "notes": markdown(r.get("body") or ""),
            "action": kind,
            "how": self._how(kind, tag, self.where.note),
        }

    @staticmethod
    def _wizard(r):
        return next((a for a in r.get("assets") or [] if isinstance(a, dict)
                     and str(a.get("name", "")).endswith(WIZARD_SUFFIX) and a.get("browser_download_url")), None)

    @staticmethod
    def _how(kind, tag, note=None):
        if kind == "wizard":
            return "Update downloads the release's setup wizard and starts it. LENS closes so the wizard can replace its files; your settings are kept."
        if kind == "script":
            return ("Update runs the Linux installer kept in the LENS folder for this release. LENS closes "
                    "while it installs and opens again when it has finished; your settings are kept.")
        if note:
            return note
        return ("This copy of LENS was not installed by a LENS installer, so it cannot update itself. "
                f"Download {tag} from its release page and install it, or, for a copy installed from source "
                "with pip, check out the new release and run pip install again.")

    def update(self):
        """Install the release the check found. {"ok": True} once the installer has started (LENS
        then exits), or {"ok": False, "error": ...}."""
        if not self._done.is_set() or self._release is None:
            return {"ok": False, "error": "There is no newer release to install."}
        r, where = self._release, self.where
        tag = r["tag_name"]
        try:
            if where.kind == "wizard":
                asset = self._wizard(r)
                if asset is None:
                    return {"ok": False, "error": f"Release {tag} has no Windows setup wizard; download it from its page."}
                to = Path(tempfile.mkdtemp(prefix="lens-update-")) / asset["name"]
                self._download(asset["browser_download_url"], to)
                self._spawn([str(to)])
            elif where.kind == "script":
                # The installer replaces the install folder it lives in, so it runs from a copy.
                script = Path(tempfile.mkdtemp(prefix="lens-update-")) / SCRIPT
                shutil.copy(where.folder / SCRIPT, script)
                LOG.parent.mkdir(parents=True, exist_ok=True)
                self._spawn(["sh", "-c", RELAUNCH, "lens-update", str(os.getpid()), str(script), tag[1:],
                             str(LOG), str(where.exe)])
            else:
                return {"ok": False, "error": self._how("manual", tag, where.note)}
        except Exception as e:
            return {"ok": False, "error": f"Could not start the update: {e}"}
        self._exit()
        return {"ok": True, "action": where.kind}


updater = Updater()
