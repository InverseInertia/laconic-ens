# PyInstaller spec: build with `pyinstaller packaging/lens.spec` from anywhere.
import os
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
if sys.platform == "win32":
    # A folder (dist/lens: lens.exe beside _internal), which packaging/lens.iss turns into the
    # installer. A one-file build unpacks itself to a temporary folder on every launch (and
    # antivirus scans what it unpacks) before LENS can start.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lens",
              console=False,  # no console window
              upx=False, icon=icon)
    coll = COLLECT(exe, a.binaries, a.datas, name="lens", upx=False)
else:
    # One file (dist/lens), which is what install-linux.sh installs.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name="lens",
        console=True,
        upx=False,
        icon=icon,
    )
