# PyInstaller spec: build with `pyinstaller packaging/lens.spec` from anywhere.
import os
import shutil
import subprocess
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = (collect_submodules("laconic") + collect_submodules("uvicorn") + ["CoolProp.CoolProp"]
          + collect_submodules("scipy.optimize"))
ROOT = os.path.dirname(SPECPATH)  # SPECPATH is the directory holding this file
ICON = os.path.join(SPECPATH, "icon.png")  # rendered from laconic/static/logo.svg; PyInstaller converts it (needs Pillow)
datas = [(os.path.join(ROOT, "laconic", "static"), "laconic/static"),
         (os.path.join(ROOT, "laconic", "examples"), "laconic/examples"),
         (os.path.join(SPECPATH, "file-icon.ico"), ".")] + collect_data_files("pint")  # see laconic/fileassoc.py

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
icon = ICON if os.path.exists(ICON) and sys.platform in ("win32", "darwin") else None
# A folder, dist/lens: the program lens (lens.exe) beside _internal, which the installers install
# (packaging/lens.iss on Windows; on Linux the build workflow packs it as a .tar.gz for
# install-linux.sh). A one-file build unpacks itself to a temporary folder on every launch (and
# antivirus scans what it unpacks) before LENS can start.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lens",
          console=sys.platform != "win32",  # no console window on Windows
          upx=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="lens", upx=False)
# Beside the program: LENS's own license, and the licenses of everything bundled with it
# (packaging/notices.py), which the installers install with it.
shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(DISTPATH, "lens", "LICENSE.txt"))
subprocess.run([sys.executable, os.path.join(SPECPATH, "notices.py"),
                os.path.join(DISTPATH, "lens", "THIRD-PARTY-NOTICES.txt")], check=True)
