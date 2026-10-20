"""Run the frozen binary, check it serves the UI and the vendored assets."""
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
            urllib.request.urlopen(base + "/", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    else:
        sys.exit("server did not start")
    for path in ("/static/vendor/katex/katex.min.js", "/static/vendor/d3/d3.min.js", "/static/plotview.js",
                 "/static/fonts/fonts.css", "/static/example.lens"):
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
    print("smoke test ok")
finally:
    p.terminate()
