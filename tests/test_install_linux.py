"""packaging/install-linux.sh, run against a stand-in binary in a throwaway home folder."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from laconic import __main__ as cli

ROOT = Path(__file__).resolve().parent.parent
PNG = (ROOT / "packaging" / "icon.png").read_bytes()

pytestmark = pytest.mark.skipif(shutil.which("sh") is None or os.name != "posix", reason="needs a POSIX shell")


def run(tmp_path, *args):
    home = tmp_path / "home"
    env = {"PATH": os.environ["PATH"], "HOME": str(home)}
    return subprocess.run(["sh", str(tmp_path / "dl" / "install-linux.sh"), *args], env=env,
                          capture_output=True, text=True, check=True), home


@pytest.fixture
def downloads(tmp_path):
    dl = tmp_path / "dl"
    dl.mkdir()
    shutil.copy(ROOT / "packaging" / "install-linux.sh", dl)
    (dl / "lens-linux-x64").write_text('#!/bin/sh\n[ "$1" = --export-examples ] && mkdir -p "$2"\n')
    (dl / "lens-icon.png").write_bytes(PNG)
    (dl / "lens-file-icon.png").write_bytes(PNG)
    return dl


def test_launcher_names_the_window_class_lens_opens_with(tmp_path, downloads):
    _, home = run(tmp_path)
    data = home / ".local" / "share"
    desktop = (data / "applications" / "laconic-lens.desktop").read_text()
    assert re.search(r"^StartupWMClass=(.*)$", desktop, re.M).group(1) == cli.WM_CLASS
    icon = Path(re.search(r"^Icon=(.*)$", desktop, re.M).group(1))
    assert icon.is_absolute() and icon.read_bytes() == PNG


def test_uninstall_removes_what_install_and_the_window_left(tmp_path, downloads):
    _, home = run(tmp_path)
    data = home / ".local" / "share"
    profile = home / ".cache" / "laconic-lens" / "browser"   # what a LENS window creates (see _app_args)
    profile.mkdir(parents=True)
    ours = [p for p in data.rglob("*") if p.is_file() and "laconic-lens" in str(p)]
    assert len(ours) >= 5   # program, icon, file icon, launcher, file type
    run(tmp_path, "--uninstall")
    assert not any(p.exists() for p in ours)
    assert not (data / "laconic-lens").exists() and not (home / ".cache" / "laconic-lens").exists()
