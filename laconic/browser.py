"""Finding a Chromium-family browser: for the app window (`lens --serve --app`) and the PDF export.

Any browser built on Chromium will do (Chrome, Chromium, Edge, Brave, Vivaldi, Opera and the
rest all take `--app`, `--class`, `--user-data-dir` and `--print-to-pdf`). The user's default
browser comes first when it is one of them, so a Brave user gets Brave rather than a Chrome that
happens to be installed too (#72). LENS_CHROMIUM names one by hand and beats both."""
import os
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
# Windows does not put the browsers on PATH: paths under Program Files and the per-user AppData.
# Edge is always there, so it is last: an installed Brave or Chrome is the one the user chose.
WINDOWS = ("BraveSoftware/Brave-Browser/Application/brave.exe", "Google/Chrome/Application/chrome.exe",
           "Vivaldi/Application/vivaldi.exe", "Chromium/Application/chrome.exe",
           "Microsoft/Edge/Application/msedge.exe")
# The default browser's ProgId (from the http UserChoice key) -> the WINDOWS entry it is.
_WINDOWS_PROGIDS = {"BraveHTML": 0, "ChromeHTML": 1, "VivaldiHTM": 2, "ChromiumHTM": 3, "MSEdgeHTM": 4}
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


def _windows_default():
    try:
        import winreg
        key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            progid = winreg.QueryValueEx(k, "ProgId")[0]
    except (ImportError, OSError):
        return None
    i = next((i for prefix, i in _WINDOWS_PROGIDS.items() if progid.startswith(prefix)), None)
    if i is None:
        return None
    return next((str(p) for r in _windows_roots() if (p := Path(r) / WINDOWS[i]).is_file()), None)


def find():
    """A Chromium-family browser's path, or None."""
    if (p := os.environ.get("LENS_CHROMIUM")) and Path(p).is_file():
        return p
    if sys.platform.startswith("linux") and (p := _linux_default()):
        return p
    if sys.platform == "win32" and (p := _windows_default()):
        return p
    for exe in NAMES:
        if p := shutil.which(exe):
            return p
    if sys.platform.startswith("linux"):
        for app_id in FLATPAKS:
            if p := _flatpak(app_id):
                return p
    if sys.platform == "win32":
        for rel in WINDOWS:
            for root in _windows_roots():
                if (p := Path(root) / rel).is_file():
                    return str(p)
    if sys.platform == "darwin":
        for app in MACOS:
            for root in (Path("/Applications"), Path.home() / "Applications"):
                if (p := root / f"{app}.app" / "Contents" / "MacOS" / app).is_file():
                    return str(p)
    return None


def profile_dir(exe):
    """Where the app window's own browser profile goes. A snap or flatpak browser is confined
    and cannot write to ~/.cache, so its profile goes in the folder its sandbox gives it."""
    exe = Path(exe)
    if exe.parent == Path("/snap/bin"):
        return Path.home() / "snap" / exe.name.split(".")[0] / "common" / "laconic-lens"
    if exe.parent.name == "bin" and exe.parent.parent.name == "exports" and exe.name in FLATPAKS:
        return Path.home() / ".var" / "app" / exe.name / "cache" / "laconic-lens"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "laconic-lens" / "browser"
