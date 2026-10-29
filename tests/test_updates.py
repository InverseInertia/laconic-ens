"""The update check and the Update action (laconic/updates.py), with the network, the download,
starting a program and exiting all faked."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from laconic import server, settings, updates
from laconic.updates import Place, Updater, is_newer, latest, parse

ROOT = Path(__file__).resolve().parent.parent


def rel(tag, draft=False, prerelease=False, body="### New\n- **A thing**: it works. (#134)\n", assets=()):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "body": body,
            "html_url": f"https://github.com/InverseInertia/laconic-ens/releases/tag/{tag}",
            "assets": [{"name": n, "browser_download_url": f"https://example.invalid/{n}"} for n in assets]}


RELEASES = [rel("v0.6.0-rc1", prerelease=True), rel("v0.7.0", draft=True), rel("installer-v2.2.0"),
            rel("v0.5.0", assets=["lens-0.5.0-windows-x64-install-wizard.exe", "lens-0.5.0-linux-x64.tar.gz"]),
            rel("v0.4.5")]


class Fake:
    """Records what the updater asked for, in place of the network and the operating system."""

    def __init__(self, releases=RELEASES):
        self.releases, self.calls = releases, []

    def fetch(self, url, timeout):
        self.calls.append(("fetch", url))
        if isinstance(self.releases, Exception):
            raise self.releases
        return self.releases

    def download(self, url, to):
        self.calls.append(("download", url))
        Path(to).write_bytes(b"MZ")

    def spawn(self, cmd):
        self.calls.append(("spawn", cmd))

    def exit(self):
        self.calls.append(("exit",))

    def updater(self, where=Place("manual"), current="0.4.5"):
        return Updater(fetch=self.fetch, download=self.download, spawn=self.spawn, exit=self.exit,
                       where=where, current=current)


def test_versions_compare_as_numbers():
    assert parse("v0.4.10") == (0, 4, 10) and parse("0.4.5") == (0, 4, 5)
    assert parse("0+dev") is None and parse("v0.5.0-rc1") is None and parse("installer-v2.2.0") is None
    assert is_newer("v0.4.10", "0.4.9") and not is_newer("v0.4.9", "0.4.10")
    assert not is_newer("v0.5", "0.5.0") and not is_newer("v0.4.5", "0.4.5")
    assert not is_newer("v9.9.9", "0+dev")   # a source checkout is never told to update


def test_the_latest_release_skips_drafts_prereleases_and_installer_tags():
    assert latest(RELEASES)["tag_name"] == "v0.5.0"
    assert latest([rel("installer-v2.2.0"), rel("v0.6.0", prerelease=True)]) is None
    assert latest({"message": "API rate limit exceeded"}) is None


def test_a_newer_release_is_offered_with_its_notes():
    fake = Fake()
    u = fake.updater().result(wait=5)
    assert u["checking"] is False
    found = u["update"]
    assert found["version"] == "0.5.0" and found["label"] == "v0.5.0" and found["current"] == "v0.4.5"
    assert found["url"].endswith("/releases/tag/v0.5.0")
    assert "<h5>New</h5>" in found["notes"] and "<strong>A thing</strong>" in found["notes"]
    assert found["action"] == "manual" and "release page" in found["how"]


def test_the_check_runs_once_and_is_kept():
    fake = Fake()
    up = fake.updater()
    up.result(wait=5)
    up.result(wait=5)
    up.check()
    assert [c for c in fake.calls if c[0] == "fetch"] == [("fetch", updates.API)]


def test_nothing_is_offered_when_up_to_date_offline_or_a_dev_build():
    assert Fake().updater(current="0.5.0").result(wait=5)["update"] is None
    assert Fake(OSError("offline")).updater().result(wait=5) == {"checking": False, "update": None}
    assert Fake(ValueError("not JSON")).updater().result(wait=5)["update"] is None
    dev = Fake()
    assert dev.updater(current="0+dev").result(wait=5)["update"] is None
    assert dev.calls == []   # not even asked


def test_release_notes_are_escaped():
    found = Fake([rel("v0.5.0", body="- <script>alert(1)</script>")]).updater().result(wait=5)["update"]
    assert "<script>" not in found["notes"] and "&lt;script&gt;" in found["notes"]


def test_where_lens_was_installed_decides_what_update_does(tmp_path):
    assert updates.place(frozen=False).kind == "manual"
    exe = tmp_path / "lens.exe"
    assert updates.place(frozen=True, platform="win32", exe=exe).kind == "manual"
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert updates.place(frozen=True, platform="win32", exe=exe) == Place("wizard", tmp_path, exe)
    lin = tmp_path / "linux"
    lin.mkdir()
    assert updates.place(frozen=True, platform="linux", exe=lin / "lens") == Place("manual", lin, lin / "lens")
    (lin / "version").write_text("0.4.5\n")   # installed by an installer that kept no copy of itself
    older = updates.place(frozen=True, platform="linux", exe=lin / "lens")
    assert older.kind == "manual" and older.note == updates.LINUX_AGAIN
    found = Fake().updater(older).result(wait=5)["update"]
    assert found["action"] == "manual" and "lens-install-linux-v2.sh" in found["how"]
    (lin / "install-linux.sh").write_text("#!/bin/sh\n")
    assert updates.place(frozen=True, platform="linux", exe=lin / "lens").kind == "script"


def test_windows_downloads_and_starts_the_wizard_then_exits(tmp_path):
    fake = Fake()
    up = fake.updater(Place("wizard", tmp_path, tmp_path / "lens.exe"))
    assert up.result(wait=5)["update"]["action"] == "wizard"
    assert up.update() == {"ok": True, "action": "wizard"}
    kinds = [c[0] for c in fake.calls]
    assert kinds == ["fetch", "download", "spawn", "exit"]
    assert fake.calls[1][1] == "https://example.invalid/lens-0.5.0-windows-x64-install-wizard.exe"
    started = Path(fake.calls[2][1][0])
    assert started.name == "lens-0.5.0-windows-x64-install-wizard.exe" and started.read_bytes() == b"MZ"
    shutil.rmtree(started.parent)


def test_a_release_without_a_wizard_is_offered_as_a_download(tmp_path):
    fake = Fake([rel("v0.5.0")])
    up = fake.updater(Place("wizard", tmp_path, tmp_path / "lens.exe"))
    assert up.result(wait=5)["update"]["action"] == "manual"
    assert up.update()["ok"] is False
    assert [c[0] for c in fake.calls] == ["fetch"]


def test_linux_runs_the_kept_installer_for_that_release_then_exits(tmp_path):
    (tmp_path / "install-linux.sh").write_text("#!/bin/sh\necho installer\n")
    fake = Fake()
    up = fake.updater(Place("script", tmp_path, tmp_path / "lens"))
    assert up.result(wait=5)["update"]["action"] == "script"
    assert up.update() == {"ok": True, "action": "script"}
    (_, cmd), exit_ = fake.calls[1:]
    assert exit_ == ("exit",)
    assert cmd[:3] == ["sh", "-c", updates.RELAUNCH]
    pid, script, version, log, exe = cmd[4:]
    assert pid == str(os.getpid()) and version == "0.5.0" and exe == str(tmp_path / "lens")
    # run from a copy, since the installer replaces the folder it was kept in
    assert Path(script).parent != tmp_path and Path(script).read_text() == "#!/bin/sh\necho installer\n"
    shutil.rmtree(Path(script).parent)


@pytest.mark.skipif(shutil.which("sh") is None or os.name != "posix", reason="needs a POSIX shell")
def test_the_relaunch_runs_the_installer_then_starts_lens_again(tmp_path):
    script = tmp_path / "install.sh"
    script.write_text('echo "installing $1 $2"\n')
    lens = tmp_path / "lens"
    lens.write_text(f'#!/bin/sh\necho "started $*" > "{tmp_path}/started"\n')
    lens.chmod(0o755)
    log = tmp_path / "update.log"
    gone = subprocess.Popen(["true"])
    gone.wait()   # a LENS that has already exited
    subprocess.run(["sh", "-c", updates.RELAUNCH, "x", str(gone.pid), str(script), "0.5.0", str(log), str(lens)],
                   check=True, timeout=30)
    assert log.read_text() == "installing --release 0.5.0\n"
    assert (tmp_path / "started").read_text() == "started --window\n"


def test_a_manual_install_cannot_update_itself():
    fake = Fake()
    up = fake.updater()
    up.result(wait=5)
    assert up.update()["ok"] is False
    assert [c[0] for c in fake.calls] == ["fetch"]


def test_a_failed_download_changes_nothing(tmp_path):
    fake = Fake()

    def broken(url, to):
        raise OSError("connection reset")
    fake.download = broken
    up = fake.updater(Place("wizard", tmp_path, tmp_path / "lens.exe"))
    up.result(wait=5)
    r = up.update()
    assert r["ok"] is False and "connection reset" in r["error"]
    assert [c[0] for c in fake.calls] == ["fetch"]


# ---- the endpoints ------------------------------------------------------------------------
@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_the_endpoint_offers_the_update_and_installs_only_the_one_offered(config, monkeypatch, tmp_path):
    fake = Fake()
    monkeypatch.setattr(updates, "updater", fake.updater(Place("wizard", tmp_path, tmp_path / "lens.exe")))
    assert server.get_update(wait=5)["update"]["version"] == "0.5.0"
    assert server.post_update(server.UpdateBody(version="0.4.0"))["ok"] is False
    assert [c[0] for c in fake.calls] == ["fetch"]
    assert server.post_update(server.UpdateBody(version="0.5.0"))["ok"] is True
    assert fake.calls[-1] == ("exit",)


def test_the_page_starts_the_check_and_the_setting_turns_it_off(config, monkeypatch):
    fake = Fake()
    monkeypatch.setattr(updates, "updater", fake.updater())
    settings.save_prefs({"checkUpdates": False})
    server.index()
    assert server.get_update(wait=5) == {"checking": False, "update": None, "off": True}
    assert fake.calls == []
    settings.save_prefs({"checkUpdates": None})
    server.index()
    assert server.get_update(wait=5)["update"]["version"] == "0.5.0"
