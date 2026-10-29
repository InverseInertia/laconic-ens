"""The Update button and dialog on the real page in Chromium (#134), with the release lookup and
the installer faked (see test_updates.py). Skipped when Playwright or a browser is not available."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from test_updates import Fake  # noqa: E402

from laconic import updates  # noqa: E402
from laconic.updates import Place  # noqa: E402


def load(page, monkeypatch, where=Place("manual")):
    fake = Fake()
    monkeypatch.setattr(updates, "updater", fake.updater(where))
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    return fake


def test_no_button_without_a_newer_release(page):
    page.wait_for_timeout(300)   # the offline check has answered
    assert page.is_hidden("#updateBtn")


def test_the_button_opens_the_release_and_update_starts_the_installer(page, monkeypatch, tmp_path):
    fake = load(page, monkeypatch, Place("wizard", tmp_path, tmp_path / "lens.exe"))
    page.wait_for_selector("#updateBtn:not([hidden])")
    assert page.inner_text("#updateBtn").strip().endswith("v0.5.0")
    page.click("#updateBtn")
    assert page.is_visible("#updateDlg")
    assert "v0.5.0" in page.inner_text("#updateMsg") and "v0.4.5" in page.inner_text("#updateMsg")
    assert page.inner_text("#updateNotes h5") == "New"
    assert page.get_attribute("#updateLink", "href").endswith("/releases/tag/v0.5.0")
    page.click("#updateGo")
    page.wait_for_function("document.querySelector('#updateGo').hidden")
    assert "closing" in page.inner_text("#updateMsg")
    assert [c[0] for c in fake.calls] == ["fetch", "download", "spawn", "exit"]
    shutil.rmtree(Path(fake.calls[2][1][0]).parent)   # the wizard's download folder


def test_a_copy_that_cannot_update_itself_says_how(page, monkeypatch):
    load(page, monkeypatch)
    page.click("#updateBtn")
    assert page.is_hidden("#updateGo")
    assert "release page" in page.inner_text("#updateHow")


def test_the_setting_turns_the_check_off(page, monkeypatch):
    fake = load(page, monkeypatch)
    page.wait_for_selector("#updateBtn:not([hidden])")
    page.click("#settingsBtn")
    page.uncheck("#checkUpdates")
    assert page.is_hidden("#updateBtn")
    page.wait_for_timeout(300)   # the setting reaches the server
    fake = load(page, monkeypatch)
    page.wait_for_timeout(500)
    assert page.is_hidden("#updateBtn") and fake.calls == []
    assert not page.is_checked("#checkUpdates")
