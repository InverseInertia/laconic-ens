"""Finding a Chromium-family browser (laconic/browsers.py), with the file system, registry and
default-browser lookups faked. #72: Brave and the rest were never found, nor anything on
Windows or macOS, so the app window fell back to a browser tab."""
import json
from pathlib import Path

import pytest

from laconic import browsers
from laconic import __main__ as cli


@pytest.fixture
def system(monkeypatch, tmp_path):
    """A fake system: install(path) makes a browser exist; registry and default are dicts."""
    reg, default = {}, {}
    monkeypatch.delenv("LENS_CHROMIUM", raising=False)
    monkeypatch.setattr(browsers.shutil, "which", lambda exe: None)
    monkeypatch.setattr(browsers, "_registry", lambda root, key, name="": reg.get((root, key)))
    monkeypatch.setattr(browsers, "_default_id", lambda platform: default.get("id"))
    real_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: real_is_file(tmp_path / str(p).lstrip("/\\").replace(":", "")))

    class System:
        root = tmp_path
        registry = reg

        @staticmethod
        def install(path):
            f = tmp_path / str(path).lstrip("/\\").replace(":", "")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("")
            return str(path)

        @staticmethod
        def set_default(ident):
            default["id"] = ident
    return System


WIN_ENV = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
           "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}


def win(*parts):
    return str(Path(*parts))


def test_windows_finds_brave_in_program_files(system):
    brave = system.install(win(WIN_ENV["PROGRAMFILES"], r"BraveSoftware\Brave-Browser\Application\brave.exe"))
    assert browsers.candidates("win32", WIN_ENV) == [brave]


def test_windows_finds_per_user_installs_and_app_paths(system):
    opera = system.install(win(WIN_ENV["LOCALAPPDATA"], r"Programs\Opera\opera.exe"))
    vivaldi = system.install(r"D:\Apps\Vivaldi\vivaldi.exe")
    system.registry[("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths\vivaldi.exe")] = f'"{vivaldi}"'
    assert browsers.candidates("win32", WIN_ENV) == [vivaldi, opera]


def test_windows_default_browser_comes_before_preinstalled_edge(system):
    edge = system.install(win(WIN_ENV["PROGRAMFILES(X86)"], r"Microsoft\Edge\Application\msedge.exe"))
    brave = system.install(win(WIN_ENV["LOCALAPPDATA"], r"BraveSoftware\Brave-Browser\Application\brave.exe"))
    assert browsers.candidates("win32", WIN_ENV) == [edge, brave]   # the fixed order: Edge first
    system.set_default("BraveHTML")
    assert browsers.candidates("win32", WIN_ENV) == [brave, edge]
    system.set_default("FirefoxURL-308046B0AF4A39CB")              # not Chromium: the fixed order
    assert browsers.candidates("win32", WIN_ENV) == [edge, brave]


def test_macos_finds_app_bundles(system, monkeypatch):
    monkeypatch.setattr(browsers.Path, "home", lambda: Path("/Users/u"))
    brave = system.install("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
    chrome = system.install("/Users/u/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    assert browsers.candidates("darwin", {}) == [chrome, brave]
    system.set_default("com.brave.browser")
    assert browsers.candidates("darwin", {}) == [brave, chrome]


def test_linux_keeps_the_old_order_and_adds_the_new_names(system, monkeypatch):
    on_path = {"brave-browser": "/usr/bin/brave-browser", "chromium": "/usr/bin/chromium",
               "vivaldi-stable": "/usr/bin/vivaldi-stable"}
    for p in on_path.values():
        system.install(p)
    monkeypatch.setattr(browsers.shutil, "which", on_path.get)
    assert browsers.candidates("linux", {}) == ["/usr/bin/chromium", "/usr/bin/brave-browser", "/usr/bin/vivaldi-stable"]
    system.set_default("brave-browser.desktop")
    assert browsers.candidates("linux", {})[0] == "/usr/bin/brave-browser"


def test_linux_finds_snap_and_flatpak(system, monkeypatch):
    monkeypatch.setenv("HOME", "/home/u")
    snap = system.install("/snap/bin/chromium")
    flat = system.install("/home/u/.local/share/flatpak/exports/bin/com.brave.Browser")
    assert browsers.candidates("linux", {}) == [snap, flat]
    assert browsers.is_sandboxed(flat) and not browsers.is_sandboxed(snap)
    assert browsers.candidates("linux", {}, sandboxed=False) == [snap]   # PDF printing skips Flatpak
    system.set_default("com.brave.Browser.desktop")
    assert browsers.candidates("linux", {})[0] == flat


@pytest.mark.parametrize("ident, name", [("google-chrome.desktop", "Chrome"), ("chromium_chromium.desktop", "Chromium"),
                                         ("microsoft-edge.desktop", "Edge"), ("vivaldi-stable.desktop", "Vivaldi"),
                                         ("opera.desktop", "Opera"), ("firefox.desktop", None)])
def test_linux_default_browser_names(system, ident, name):
    system.set_default(ident)
    b = browsers.default_browser("linux")
    assert (b and b.name) == name


def test_lens_chromium_comes_first(system):
    mine = system.install("/opt/mine/browser")
    edge = system.install(win(WIN_ENV["PROGRAMFILES"], r"Microsoft\Edge\Application\msedge.exe"))
    assert browsers.candidates("win32", {**WIN_ENV, "LENS_CHROMIUM": mine}) == [mine, edge]


def test_app_launch_tries_each_browser_and_keeps_a_flatpak_one_out_of_the_lens_profile(monkeypatch, tmp_path):
    import sys
    calls = []
    flat = "/var/lib/flatpak/exports/bin/com.brave.Browser"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(browsers, "candidates", lambda: ["/usr/bin/broken", flat])
    monkeypatch.setattr(cli, "_spawn", lambda cmd: calls.append(cmd) or cmd[0] != "/usr/bin/broken")
    cli._launch("http://127.0.0.1:1", app=True)
    assert [c[0] for c in calls] == ["/usr/bin/broken", flat]
    assert "--user-data-dir" in " ".join(calls[0]) and calls[1][1:] == ["--app=http://127.0.0.1:1"]


def test_page_carries_png_icons_for_the_app_window():
    static = Path(cli.__file__).parent / "static"
    page = (static / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((static / "manifest.json").read_text(encoding="utf-8"))
    assert '<link rel="manifest" href="/static/manifest.json">' in page
    for icon in manifest["icons"]:
        assert (static / Path(icon["src"]).name).is_file()
        if icon["type"] == "image/png":
            assert f'href="{icon["src"]}"' in page
