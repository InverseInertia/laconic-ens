"""Fixtures for the browser tests: a live server and a Chromium page on it (test_ui.py,
test_plots_ui.py, test_solver_ui.py). Each skips when its dependency is not installed."""
import os
import socket
import threading
import time

import pytest


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    uvicorn = pytest.importorskip("uvicorn")
    os.environ["LENS_CONFIG_DIR"] = str(tmp_path_factory.mktemp("cfg"))
    from laconic.server import app
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


@pytest.fixture()
def page(server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:  # no browser installed
            pytest.skip(f"no Chromium: {e}")
        pg = browser.new_page(viewport={"width": 1200, "height": 800})
        pg.goto(server)
        pg.wait_for_function("document.querySelector('#src').value.length > 0")
        pg.evaluate("localStorage.clear()")
        yield pg
        browser.close()
