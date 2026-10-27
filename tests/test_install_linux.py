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


def run(tmp_path, *args, check=True):
    home = tmp_path / "home"
    path = os.environ["PATH"]
    if (tmp_path / "bin").is_dir():   # the stand-in curl, ahead of any real one
        path = f"{tmp_path / 'bin'}:{path}"
    env = {"PATH": path, "HOME": str(home), "FAKE_GITHUB": str(tmp_path / "github")}
    return subprocess.run(["sh", str(tmp_path / "dl" / "install-linux.sh"), *args], env=env,
                          capture_output=True, text=True, check=check), home


# Serves $FAKE_GITHUB/latest.json for the latest-release lookup and $FAKE_GITHUB/v<version>/<file>
# for a release download, logging each URL; fails as curl does offline if latest.json is missing.
FAKE_CURL = """#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift ;; http*) url="$1" ;; esac
    shift
done
echo "$url" >> "$FAKE_GITHUB/log"
case "$url" in
    */releases/latest) src="$FAKE_GITHUB/latest.json" ;;
    */releases/download/*) rest="${url#*/releases/download/}"; src="$FAKE_GITHUB/$rest" ;;
esac
[ -f "$FAKE_GITHUB/latest.json" ] || exit 6
[ -f "$src" ] || exit 22
cp "$src" "$out"
"""


def program(version):
    return f'#!/bin/sh\n# LENS {version}\n[ "$1" = --export-examples ] && mkdir -p "$2"\n'


def release(github, version):
    """Put a release's files on the stand-in GitHub."""
    d = github / f"v{version}"
    d.mkdir(parents=True)
    (d / f"lens-{version}-linux-x64").write_text(program(version))
    (d / f"lens-{version}-icon.png").write_bytes(PNG)
    (d / f"lens-{version}-file-icon.png").write_bytes(PNG)


def latest(github, version):
    (github / "latest.json").write_text(
        '{\n  "url": "https://api.github.com/repos/x/y/releases/1",\n'
        f'  "tag_name": "v{version}",\n  "name": "v{version}",\n  "assets": [{{"name": "a"}}]\n}}\n')


@pytest.fixture
def github(tmp_path):
    """A stand-in GitHub (offline until latest() is called) and an empty downloads folder."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "curl").write_text(FAKE_CURL)
    (tmp_path / "bin" / "curl").chmod(0o755)
    (tmp_path / "github").mkdir()
    (tmp_path / "dl").mkdir()
    shutil.copy(ROOT / "packaging" / "install-linux.sh", tmp_path / "dl")
    return tmp_path / "github"


def installed(home):
    app = home / ".local" / "share" / "laconic-lens"
    return (app / "lens").read_text(), (app / "version").read_text().strip()


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
    profile = home / ".cache" / "laconic-lens" / "browser-google-chrome"   # what a LENS window creates (see _app_args)
    profile.mkdir(parents=True)
    ours = [p for p in data.rglob("*") if p.is_file() and "laconic-lens" in str(p)]
    assert len(ours) >= 5   # program, icon, file icon, launcher, file type
    run(tmp_path, "--uninstall")
    assert not any(p.exists() for p in ours)
    assert not (data / "laconic-lens").exists() and not (home / ".cache" / "laconic-lens").exists()


def test_installs_the_latest_release_and_updates_to_a_newer_one(tmp_path, github):
    release(github, "0.3.5")
    latest(github, "0.3.5")
    r, home = run(tmp_path)
    assert "Installing LENS 0.3.5" in r.stdout
    assert installed(home) == (program("0.3.5"), "0.3.5")
    release(github, "0.4.0")
    latest(github, "0.4.0")
    r, home = run(tmp_path)
    assert "Updating LENS 0.3.5 -> 0.4.0" in r.stdout
    assert installed(home) == (program("0.4.0"), "0.4.0")


def test_uses_files_of_the_latest_release_already_beside_it(tmp_path, github):
    latest(github, "0.3.5")   # the release is not on the stand-in GitHub, so a download would fail
    release(tmp_path / "dl" / "x", "0.3.5")
    for f in (tmp_path / "dl" / "x" / "v0.3.5").iterdir():
        f.rename(tmp_path / "dl" / f.name)
    _, home = run(tmp_path)
    assert installed(home) == (program("0.3.5"), "0.3.5")


def test_offline_installs_the_newest_release_beside_it(tmp_path, github):
    for v in ("0.3.9", "0.3.10"):
        release(tmp_path / "dl" / "x", v)
        for f in (tmp_path / "dl" / "x" / f"v{v}").iterdir():
            f.rename(tmp_path / "dl" / f.name)
    r, home = run(tmp_path)
    assert "installing 0.3.10 from the files beside this script" in r.stdout
    assert installed(home) == (program("0.3.10"), "0.3.10")


def test_offline_with_nothing_beside_it_says_so_and_changes_nothing(tmp_path, github):
    release(github, "0.3.5")
    latest(github, "0.3.5")
    _, home = run(tmp_path)
    (github / "latest.json").unlink()
    r, home = run(tmp_path, check=False)
    assert r.returncode == 1 and "Could not look up the latest release" in r.stderr
    assert installed(home) == (program("0.3.5"), "0.3.5")


def test_a_missing_release_file_changes_nothing(tmp_path, github):
    release(github, "0.3.5")
    latest(github, "0.3.5")
    _, home = run(tmp_path)
    latest(github, "0.4.0")   # announced, but its files are not there
    r, home = run(tmp_path, check=False)
    assert r.returncode == 1 and "Could not download" in r.stderr
    assert installed(home) == (program("0.3.5"), "0.3.5")


def test_release_option_installs_that_release_without_a_lookup(tmp_path, github):
    release(github, "0.3.4")
    latest(github, "0.3.5")
    _, home = run(tmp_path, "--release", "v0.3.4")
    assert installed(home) == (program("0.3.4"), "0.3.4")
    assert not any(u.endswith("/releases/latest") for u in (github / "log").read_text().split())


def test_the_installer_has_a_version_of_its_own(tmp_path, github):
    script = (ROOT / "packaging" / "install-linux.sh").read_text()
    version = re.search(r'^INSTALLER_VERSION="(\d+\.\d+\.\d+)"$', script, re.M).group(1)
    r, _ = run(tmp_path, "--version")
    assert r.stdout.strip() == f"LENS installer {version}"
