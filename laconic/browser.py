"""Finding a Chromium-family browser: for the app window (`lens --serve --app`) and the PDF export.

Any browser built on Chromium will do (Chrome, Chromium, Edge, Brave, Vivaldi, Opera and the
rest all take `--app`, `--class`, `--user-data-dir` and `--print-to-pdf`). The user's default
browser comes first when it is one of them, so a Brave user gets Brave rather than a Chrome that
happens to be installed too (#72). LENS_CHROMIUM names one by hand and beats both."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Command names on PATH (Linux, and anything on PATH elsewhere), most common first.
NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
         "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave-browser-stable", "brave",
         "vivaldi", "vivaldi-stable", "opera", "thorium-browser", "msedge", "chrome")
# Flatpak's launchers, in its exports folder, which is not always on PATH.
FLATPAKS = ("com.google.Chrome", "org.chromium.Chromium", "com.microsoft.Edge", "com.brave.Browser",
            "com.vivaldi.Vivaldi", "com.opera.Opera", "io.github.ungoogled_software.ungoogled_chromium")
# Windows does not put the browsers on PATH: paths under Program Files and the per-user AppData,
# else wherever the registry's App Paths says the program is (a browser installed elsewhere).
# Edge is always there, so it is last: an installed Brave or Chrome is the one the user chose.
WINDOWS = ("BraveSoftware/Brave-Browser/Application/brave.exe", "Google/Chrome/Application/chrome.exe",
           "Vivaldi/Application/vivaldi.exe", "Chromium/Application/chrome.exe",
           "Programs/Opera/opera.exe", "Microsoft/Edge/Application/msedge.exe")
# The default browser's ProgId (from the http UserChoice key) -> the WINDOWS entry it is.
_WINDOWS_PROGIDS = {"BraveHTML": 0, "ChromeHTML": 1, "VivaldiHTM": 2, "ChromiumHTM": 3, "Opera": 4,
                    "MSEdgeHTM": 5}
_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
MACOS = ("Google Chrome", "Brave Browser", "Microsoft Edge", "Chromium", "Vivaldi", "Opera")


def _linux_default():
    """The default browser's command when it is Chromium-family, else None. xdg-settings
    names a .desktop file; its Exec line names the program."""
    try:
        desktop = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not desktop.endswith(".desktop"):
        return None
    if (p := _known(Path(desktop).stem)):   # brave-browser.desktop, com.brave.Browser.desktop
        return p
    dirs = [os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    for d in dirs:
        f = Path(d) / "applications" / desktop
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("Exec="):
                words = line[5:].split()
                return _known(Path(words[0]).name) if words else None
        return None
    return None


def _known(name):
    """The path of `name` when it is a browser NAMES or FLATPAKS lists and it is installed."""
    if name in NAMES:
        return shutil.which(name)
    if name in FLATPAKS:
        return _flatpak(name)
    return None


def _flatpak(app_id):
    for d in (Path.home() / ".local/share/flatpak/exports/bin", Path("/var/lib/flatpak/exports/bin")):
        if (p := d / app_id).is_file():
            return str(p)
    return None


def _windows_roots():
    return [r for r in (os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")) if r]


def _registry(hive, key, name=""):
    """A registry value under HKEY_CURRENT_USER ("HKCU") or HKEY_LOCAL_MACHINE ("HKLM"), or None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except (ImportError, OSError):
        return None


def _windows(rel):
    """Where the WINDOWS entry `rel` is installed: under one of the usual roots, else where App
    Paths says its program is. None when neither has it."""
    for root in _windows_roots():
        if (p := Path(root) / rel).is_file():
            return str(p)
    for hive in ("HKCU", "HKLM"):
        if (p := _registry(hive, rf"{_APP_PATHS}\{Path(rel).name}")) and Path(p := p.strip('"')).is_file():
            return p
    return None


def _windows_default():
    key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
    if not (progid := _registry("HKCU", key, "ProgId")):
        return None
    i = next((i for prefix, i in _WINDOWS_PROGIDS.items() if progid.startswith(prefix)), None)
    return None if i is None else _windows(WINDOWS[i])


def candidates():
    """Every Chromium-family browser found, best first, each once."""
    seen = set()
    for p in _candidates():
        if p and p not in seen:
            seen.add(p)
            yield p


def _candidates():
    if (p := os.environ.get("LENS_CHROMIUM")) and Path(p).is_file():
        yield p
    if sys.platform.startswith("linux"):
        yield _linux_default()
    if sys.platform == "win32":
        yield _windows_default()
    for exe in NAMES:
        yield shutil.which(exe)
    if sys.platform.startswith("linux"):
        for app_id in FLATPAKS:
            yield _flatpak(app_id)
    if sys.platform == "win32":
        for rel in WINDOWS:
            yield _windows(rel)
    if sys.platform == "darwin":
        for app in MACOS:
            for root in (Path("/Applications"), Path.home() / "Applications"):
                if (p := root / f"{app}.app" / "Contents" / "MacOS" / app).is_file():
                    yield str(p)


def find():
    """The best Chromium-family browser's path, or None."""
    return next(candidates(), None)


def app_candidates():
    """candidates() for the app window: on Linux, browsers installed natively come before
    flatpak and snap ones. The desktop ties a window from a sandboxed browser to that browser
    (Cinnamon and GNOME look up a window's sandbox before its WM_CLASS), so only a native
    browser's window can show as LENS, with the LENS icon (#93). A sandboxed one is still
    used when it is all there is."""
    found = list(candidates())
    if not sys.platform.startswith("linux"):
        return iter(found)
    return iter([p for p in found if not sandbox(p)] + [p for p in found if sandbox(p)])


_SNAP_EXEC = re.compile(rb"/snap/bin/([A-Za-z0-9][A-Za-z0-9.+_-]*)")


def sandbox(exe):
    """("flatpak", app id) or ("snap", snap name) when `exe` runs a sandboxed browser, else
    None. Besides /snap/bin, a snap is reached through /usr/bin/snap itself, or through a
    small script that runs it: Ubuntu's /usr/bin/chromium-browser is one."""
    exe = Path(exe)
    if exe.parent.name == "bin" and exe.parent.parent.name == "exports" and exe.name in FLATPAKS:
        return ("flatpak", exe.name)
    if exe.parent == Path("/snap/bin") or os.path.realpath(exe).endswith("/snap"):
        return ("snap", exe.name.split(".")[0])
    try:
        with open(exe, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if head.startswith(b"#!") and (m := _SNAP_EXEC.search(head)):
        return ("snap", m.group(1).decode().split(".")[0])
    return None


def profile_dir(exe):
    """Where the app window's own browser profile goes: one per browser, so a window is never
    handed to another browser's process (or to one LENS started with other flags), which
    would open it under that process's identity. A snap or flatpak browser is confined and
    cannot write to ~/.cache, so its profile goes in the folder its sandbox gives it."""
    kind = sandbox(exe)
    if kind and kind[0] == "snap":
        return Path.home() / "snap" / kind[1] / "common" / "laconic-lens"
    if kind:
        return Path.home() / ".var" / "app" / kind[1] / "cache" / "laconic-lens"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(os.path.realpath(exe)).name) or "browser"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "laconic-lens" / f"browser-{name}"
