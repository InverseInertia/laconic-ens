"""Finding a Chromium-family browser: for the app window (`--app`) and for printing PDFs.

Every browser built on Chromium takes the same switches, so any of them will do. The user's
default browser comes first when it is one of them (a Brave user gets Brave, not the Edge that
Windows ships with); then the browsers in BROWSERS order. LENS_CHROMIUM names one by hand.
"""
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Browser:
    name: str
    linux: tuple = ()       # executable names on PATH (snap's /snap/bin among them)
    flatpak: str = ""       # Flatpak application ID
    mac: str = ""           # app bundle name; the executable is Contents/MacOS/<bundle name>
    mac_id: str = ""        # bundle ID, as Launch Services names the default browser
    windows: tuple = ()     # paths under Program Files or LocalAppData
    app_path: str = ""      # the key under the registry's App Paths
    progid: str = ""        # the start of the ProgId Windows names the default browser by


BROWSERS = (
    Browser("Chrome", ("google-chrome", "google-chrome-stable", "chrome"), "com.google.Chrome",
            "Google Chrome", "com.google.chrome", (r"Google\Chrome\Application\chrome.exe",),
            "chrome.exe", "ChromeHTML"),
    Browser("Chromium", ("chromium", "chromium-browser"), "org.chromium.Chromium",
            "Chromium", "org.chromium.chromium", (r"Chromium\Application\chrome.exe",),
            "", "ChromiumHTM"),
    Browser("Edge", ("microsoft-edge", "microsoft-edge-stable", "msedge"), "com.microsoft.Edge",
            "Microsoft Edge", "com.microsoft.edgemac", (r"Microsoft\Edge\Application\msedge.exe",),
            "msedge.exe", "MSEdgeHTM"),
    Browser("Brave", ("brave-browser", "brave-browser-stable", "brave"), "com.brave.Browser",
            "Brave Browser", "com.brave.browser",
            (r"BraveSoftware\Brave-Browser\Application\brave.exe",), "brave.exe", "BraveHTML"),
    Browser("Vivaldi", ("vivaldi", "vivaldi-stable"), "com.vivaldi.Vivaldi",
            "Vivaldi", "com.vivaldi.vivaldi", (r"Vivaldi\Application\vivaldi.exe",),
            "vivaldi.exe", "VivaldiHTM"),
    Browser("Opera", ("opera",), "com.opera.Opera",
            "Opera", "com.operasoftware.opera", (r"Programs\Opera\opera.exe", r"Opera\opera.exe"),
            "opera.exe", "Opera"),
)

FLATPAK_BINS = ("/var/lib/flatpak/exports/bin", "~/.local/share/flatpak/exports/bin")


def is_sandboxed(path):
    """A Flatpak browser cannot reach a profile or a file outside its sandbox."""
    return "/flatpak/exports/bin/" in str(path).replace("\\", "/")


def _registry(root, key, name=""):
    """A registry value, or None. root is "HKCU" or "HKLM"."""
    try:
        import winreg
        with winreg.OpenKey(getattr(winreg, "HKEY_CURRENT_USER" if root == "HKCU" else "HKEY_LOCAL_MACHINE"),
                            key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except (ImportError, OSError):
        return None


def _default_id(platform):
    """What names the user's default browser: a desktop file ID on Linux, a ProgId on Windows,
    a bundle ID on macOS. None when it cannot be told."""
    try:
        if platform == "win32":
            return _registry("HKCU", r"Software\Microsoft\Windows\Shell\Associations"
                                     r"\UrlAssociations\https\UserChoice", "ProgId")
        if platform == "darwin":
            f = Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
            for h in plistlib.loads(f.read_bytes()).get("LSHandlers", []):
                if h.get("LSHandlerURLScheme") in ("https", "http"):
                    return h.get("LSHandlerRoleAll")
            return None
        if shutil.which("xdg-settings"):
            out = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True,
                                 text=True, timeout=5, check=False).stdout
            return out.strip() or None
    except (OSError, ValueError, plistlib.InvalidFileException, subprocess.SubprocessError):
        pass
    return None


def default_browser(platform=None):
    """The entry of BROWSERS that is the user's default browser, or None."""
    platform = platform or sys.platform
    ident = _default_id(platform)
    if not ident:
        return None
    ident = ident.lower()
    for b in BROWSERS:
        if platform == "win32":
            if b.progid and ident.startswith(b.progid.lower()):
                return b
        elif platform == "darwin":
            if ident == b.mac_id:
                return b
        else:
            # brave-browser.desktop, com.brave.Browser.desktop (Flatpak), chromium_chromium.desktop (snap)
            stem = ident.removesuffix(".desktop").split("_")[-1]
            if stem in b.linux or stem == b.flatpak.lower():
                return b
    return None


def _paths(b, platform, env):
    """Where browser b is on this system, best first: on PATH first except on Windows, which
    does not put browsers there."""
    names = {"win32": (b.app_path,) if b.app_path else (), "darwin": ()}.get(platform, b.linux)
    on_path = [p for exe in names if (p := shutil.which(exe))]   # which() has checked they are there
    installed = [p for p in _places(b, platform, env) if Path(p).is_file()]
    return installed + on_path if platform == "win32" else on_path + installed


def _places(b, platform, env):
    """Where browser b may be installed, other than on PATH. Not checked to exist."""
    if platform == "win32":
        for root in ("HKCU", "HKLM"):
            if b.app_path and (p := _registry(root, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{b.app_path}")):
                yield p.strip('"')
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if root := env.get(var):
                for rel in b.windows:
                    yield str(Path(root) / rel)
    elif platform == "darwin":
        for apps in ("/Applications", Path.home() / "Applications"):
            yield str(Path(apps) / f"{b.mac}.app" / "Contents" / "MacOS" / b.mac)
    else:
        for exe in b.linux:
            yield f"/snap/bin/{exe}"    # not on PATH in every desktop session
        for d in FLATPAK_BINS:
            yield str(Path(d).expanduser() / b.flatpak)


def candidates(platform=None, env=None, sandboxed=True):
    """Every Chromium-family browser found, best first and without repeats. With
    sandboxed=False, Flatpak browsers are left out."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    first = default_browser(platform)
    order = ([first] if first else []) + [b for b in BROWSERS if b is not first]
    found = []
    if (p := env.get("LENS_CHROMIUM")) and Path(p).is_file():
        found.append(p)
    for b in order:
        for p in _paths(b, platform, env):
            if p not in found and (sandboxed or not is_sandboxed(p)):
                found.append(p)
    return found


def find(sandboxed=True):
    """The best Chromium-family browser, or None."""
    return next(iter(candidates(sandboxed=sandboxed)), None)
