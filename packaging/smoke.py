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
    for path in ("/static/vendor/katex/katex.min.js", "/static/fonts/fonts.css", "/static/example.lens"):
        urllib.request.urlopen(base + path, timeout=5).read()
    req = urllib.request.Request(base + "/api/eval", data=json.dumps({"text": "a = 2'm\na * 3"}).encode(),
                                 headers={"Content-Type": "application/json"})
    out = urllib.request.urlopen(req, timeout=10).read().decode()
    assert "6" in out, out
    print("smoke test ok")
finally:
    p.terminate()
