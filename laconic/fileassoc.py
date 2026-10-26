"""Opening .lens files from the Windows file manager: `lens --register-files` makes the
Windows build the program that opens a double-clicked .lens file, with a file icon of its own;
`lens --unregister-files` takes that back. Both write under HKEY_CURRENT_USER only, so they need
no administrator. On Linux, install-linux.sh does the same job with a MIME type.

The registration names the executable by its path: after moving it, register again."""
import os
import shutil
import sys
from pathlib import Path

PROG_ID = "LaconicLens.Worksheet"
EXT = ".lens"
ICON = "file-icon.ico"   # bundled next to the program's files by packaging/lens.spec
CLASSES = r"Software\Classes"


def _icon_home():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "laconic-lens"


def _set(winreg, path, value, name=""):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_tree(winreg, path):
    """Removes a key and everything under it; a missing key is fine."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(winreg, path + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def _notify():
    """Tells Explorer the associations changed, so icons update without a restart."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except (ImportError, AttributeError, OSError):
        pass


def register(exe, bundle, winreg=None):
    """Makes `exe` open .lens files. `bundle` is the folder holding the bundled file icon; the
    icon is copied out of it, because a one-file build unpacks to a folder that goes away."""
    if winreg is None:
        import winreg
    icon = _icon_home() / ICON
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(bundle) / ICON, icon)
    base = f"{CLASSES}\\{PROG_ID}"
    _set(winreg, base, "LENS worksheet")
    _set(winreg, base + r"\DefaultIcon", f'"{icon}"')
    _set(winreg, base + r"\shell\open\command", f'"{exe}" --window "%1"')
    _set(winreg, f"{CLASSES}\\{EXT}", PROG_ID)
    _set(winreg, f"{CLASSES}\\{EXT}", "text/plain", "Content Type")
    _notify()


def unregister(winreg=None):
    if winreg is None:
        import winreg
    _delete_tree(winreg, f"{CLASSES}\\{PROG_ID}")
    try:   # the extension's key, only if it still points at us
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\{EXT}") as k:
            ours = winreg.QueryValueEx(k, "")[0] == PROG_ID
    except FileNotFoundError:
        ours = False
    if ours:
        _delete_tree(winreg, f"{CLASSES}\\{EXT}")
    shutil.rmtree(_icon_home(), ignore_errors=True)
    _notify()


def _tell(msg):
    """The Windows build has no console: show a message box as well as printing."""
    print(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "LENS", 0x40)   # MB_ICONINFORMATION
    except (ImportError, AttributeError, OSError):
        pass


def main(undo=False):
    """The --register-files / --unregister-files commands. Returns the process exit code."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        print("--register-files is for the Windows build of LENS. On Linux, lens-install-linux.sh "
              "sets up .lens files.", file=sys.stderr)
        return 2
    if undo:
        unregister()
        _tell("LENS no longer opens .lens files.")
    else:
        register(sys.executable, sys._MEIPASS)
        _tell(f"Double-clicking a .lens file now opens it in LENS ({sys.executable}).\n"
              "If you move the program, run it with --register-files again.")
    return 0
