# PyInstaller spec: build with `pyinstaller packaging/lens.spec` from anywhere.
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = collect_submodules("laconic") + collect_submodules("uvicorn")
ROOT = os.path.dirname(SPECPATH)  # SPECPATH is the directory holding this file
datas = [(os.path.join(ROOT, "laconic", "static"), "laconic/static")] + collect_data_files("pint")

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="lens",
    console=sys.platform != "win32",  # no console window on Windows
    upx=False,
)
