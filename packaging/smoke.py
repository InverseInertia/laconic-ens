"""Run the frozen binary, check it serves the UI and the vendored assets.

Usage: smoke.py EXE [VERSION]; with VERSION ("v0.2.0" or "dev"), the page must show it."""
import glob
import json
import subprocess
import sys
import time
import urllib.request

exe = glob.glob(sys.argv[1])[0]
port = 8799
p = subprocess.Popen([exe, "--serve", "--port", str(port)])
try:
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            page = urllib.request.urlopen(base + "/", timeout=2).read().decode()
            break
        except OSError:
            time.sleep(0.5)
    else:
        sys.exit("server did not start")
    assert "{{version}}" not in page, "version marker left in the page"
    # Help ends with the changelog, which the build copies into the program (laconic/changelog.py).
    assert "<h4>" in page.split('id="changelog"')[1] and "not included in this copy" not in page, \
        "Help has no changelog"
    if len(sys.argv) > 2:
        assert f'id="version">{sys.argv[2]}<' in page, f"page does not show version {sys.argv[2]}"
    for path in ("/static/vendor/katex/katex.min.js", "/static/vendor/d3/d3.min.js", "/static/plotview.js",
                 "/static/fonts/fonts.css", "/static/example.lens", "/api/examples/beam"):
        urllib.request.urlopen(base + path, timeout=5).read()
    req = urllib.request.Request(base + "/api/eval", data=json.dumps({"text": "a = 2'm\na * 3"}).encode(),
                                 headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=10).read().decode()
    assert "6" in out, out
    # A plot draws, and its standalone SVG finds the font file it embeds.
    body = {"text": "!plot sin(x), x = 0 .. 6", "line": 1}
    req = urllib.request.Request(base + "/api/plotimage", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    svg = urllib.request.urlopen(req, timeout=10).read().decode()
    assert "<svg" in svg and "font/woff2" in svg, svg[:200]
    # A solver block runs in a spawned worker (scipy and multiprocessing must survive freezing).
    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    job = call("/api/solve/start", {"text": "x = 1\n!root x\n  equation: x^2 = 4\n", "line": 2})["job"]
    for _ in range(120):
        view = call(f"/api/solve/{job}")
        if view["state"] != "running":
            break
        time.sleep(0.5)
    assert view["state"] == "done" and abs(view["outcome"]["record"]["values"][0]["mag"] - 2) < 1e-6, view
    print("smoke test ok")
finally:
    p.terminate()
