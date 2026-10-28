"""packaging/install-linux.sh, run against a stand-in program in a throwaway home folder."""
import io
import os
import re
import shutil
import subprocess
import tarfile
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


def archive(path, version):
    """A program archive as the build makes it: the folder lens/, with lens/lens beside lens/_internal."""
    with tarfile.open(path, "w:gz") as tar:
        for name, text, mode in (("lens/lens", program(version), 0o755),
                                 (f"lens/_internal/lib-{version}.so", version, 0o644)):
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))


def release(github, version):
    """Put a release's files on the stand-in GitHub."""
    d = github / f"v{version}"
    d.mkdir(parents=True)
    archive(d / f"lens-{version}-linux-x64.tar.gz", version)
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
    assert os.access(app / "lens", os.X_OK)
    return (app / "lens").read_text(), (app / "version").read_text().strip()


@pytest.fixture
def downloads(tmp_path):
    dl = tmp_path / "dl"
    dl.mkdir()
    shutil.copy(ROOT / "packaging" / "install-linux.sh", dl)
    archive(dl / "lens-linux-x64.tar.gz", "own")
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
    # the libraries of the release it replaced are gone, not left beside the new ones
    assert [p.name for p in (home / ".local/share/laconic-lens/_internal").iterdir()] == ["lib-0.4.0.so"]


def test_a_download_that_is_not_a_program_archive_changes_nothing(tmp_path, github):
    release(github, "0.3.5")
    latest(github, "0.3.5")
    _, home = run(tmp_path)
    release(github, "0.4.0")
    (github / "v0.4.0" / "lens-0.4.0-linux-x64.tar.gz").write_text("<html>captive portal</html>")
    latest(github, "0.4.0")
    r, home = run(tmp_path, check=False)
    assert r.returncode == 1 and "is not a LENS program archive" in r.stderr
    assert installed(home) == (program("0.3.5"), "0.3.5")


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


def bridged_release(github, version):
    """A release as the release job attaches it: its files, installer 2, and the stamped bridge
    that copies of installer 1.x download as the program."""
    release(github, version)
    d = github / f"v{version}"
    shutil.copy(ROOT / "packaging" / "install-linux.sh", d / "lens-install-linux-v2.sh")
    bridge = (ROOT / "packaging" / "v1-bridge.sh").read_text()
    assert 'VERSION="@VERSION@"\n' in bridge   # what the release job's sed replaces
    (d / f"lens-{version}-linux-x64").write_text(bridge.replace("@VERSION@", version))


def test_installer_1_updates_through_the_bridge(tmp_path, github):
    """Installer 1.0.0, as v0.3.6 shipped it, looks for a single-file program the releases no
    longer have (#101); the bridge attached under that name installs the release with installer 2."""
    shutil.copy(ROOT / "tests" / "install-linux-1.0.0.sh", tmp_path / "dl" / "install-linux.sh")
    d = github / "v0.3.6"
    d.mkdir()
    (d / "lens-0.3.6-linux-x64").write_text(program("0.3.6"))
    (d / "lens-0.3.6-icon.png").write_bytes(PNG)
    (d / "lens-0.3.6-file-icon.png").write_bytes(PNG)
    latest(github, "0.3.6")
    _, home = run(tmp_path)
    assert installed(home) == (program("0.3.6"), "0.3.6")
    bridged_release(github, "0.4.1")
    latest(github, "0.4.1")
    r, home = run(tmp_path)
    assert "needs installer 2" in r.stderr
    assert installed(home) == (program("0.4.1"), "0.4.1")
    app = home / ".local/share/laconic-lens"
    assert [p.name for p in (app / "_internal").iterdir()] == ["lib-0.4.1.so"]
    assert (app / "examples").is_dir()
    desktop = (home / ".local/share/applications/laconic-lens.desktop").read_text()
    assert f'Exec="{app / "lens"}" --window %f' in desktop


@pytest.mark.skipif(not Path("/proc/self/exe").exists() or shutil.which("sleep") is None, reason="needs /proc")
@pytest.mark.parametrize("deleted", [False, True])
def test_stops_a_lens_still_running_from_the_install_folder(tmp_path, downloads, deleted):
    """A running LENS takes every new launch over, so the old release would keep showing; it is
    stopped even when its files were already deleted by hand (#101)."""
    app = tmp_path / "home" / ".local/share/laconic-lens"
    app.mkdir(parents=True)
    shutil.copy(shutil.which("sleep"), app / "lens")
    old = subprocess.Popen([str(app / "lens"), "300"])
    elsewhere = subprocess.Popen([shutil.which("sleep"), "300"])
    try:
        if deleted:
            shutil.rmtree(app)
        r, home = run(tmp_path)
        assert "Stopped the LENS that was running" in r.stdout
        assert old.wait(timeout=10) != 0
        assert elsewhere.poll() is None
        assert (home / ".local/share/laconic-lens/lens").read_text() == program("own")
    finally:
        for p in (old, elsewhere):
            p.kill()
            p.wait()
