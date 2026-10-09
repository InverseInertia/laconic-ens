import argparse
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import document, run

_CHROMIUM = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             "microsoft-edge", "brave-browser")


def _launch(url, app):
    """--app opens a Chromium-family window with no tabs or address bar, which
    gives the page more of the keyboard (Ctrl+T is a new tab in a normal tab)."""
    if app:
        for exe in _CHROMIUM:
            path = shutil.which(exe)
            if path:
                subprocess.Popen([path, f"--app={url}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        print("No Chromium-based browser found, opening the default browser instead")
    if sys.platform.startswith("linux") and shutil.which("xdg-open"):
        # GTK browsers print harmless messages to the terminal; keep them out of it.
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser(prog="lens", description="Laconic Engineering Notebook System")
    ap.add_argument("file", nargs="?", help="worksheet file (.lens); omit with --serve")
    ap.add_argument("--tex", metavar="OUT", help="write a LaTeX document to OUT")
    ap.add_argument("--serve", action="store_true", help="start the web UI")
    ap.add_argument("--open", action="store_true", help="with --serve, open the default browser")
    ap.add_argument("--app", action="store_true", help="with --serve, open a Chromium app window")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    if a.serve:
        import uvicorn
        url = f"http://127.0.0.1:{a.port}"
        print(f"laconic running at {url}")
        if a.open or a.app:
            threading.Timer(1.0, _launch, args=(url, a.app)).start()
        uvicorn.run("laconic.server:app", host="127.0.0.1", port=a.port, log_level="warning")
        return
    if not a.file:
        ap.error("give a worksheet file or use --serve")

    text = Path(a.file).read_text(encoding="utf-8")
    if a.tex:
        Path(a.tex).write_text(document(run(text, siunitx=True), title=Path(a.file).stem), encoding="utf-8")
        print(f"wrote {a.tex}")
    for r in run(text):
        if r.kind == "error":
            print(f"{r.n:>3}  ERROR  {r.error}", file=sys.stderr)
        elif r.text and r.kind in ("assign", "expr"):
            print(f"{r.n:>3}  {r.text}")


if __name__ == "__main__":
    main()
