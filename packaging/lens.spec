# PyInstaller spec: build with `pyinstaller packaging/lens.spec` from anywhere.
# Lite by default (`dist/lens`). LENS_FULL=1 bundles CoolProp for props(...) and builds `dist/lens-full`.
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

FULL = os.environ.get("LENS_FULL") == "1"
hidden = collect_submodules("laconic") + collect_submodules("uvicorn")
ROOT = os.path.dirname(SPECPATH)  # SPECPATH is the directory holding this file
datas = [(os.path.join(ROOT, "laconic", "static"), "laconic/static")] + collect_data_files("pint")
if FULL:
    hidden += ["CoolProp.CoolProp"]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest"] + ([] if FULL else ["CoolProp"]),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="lens-full" if FULL else "lens",
    console=sys.platform != "win32",  # no console window on Windows
    upx=False,
)
