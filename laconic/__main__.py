import argparse
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import document, evaluate, settings
from .sheet import solve_block
from .solver import write_result
from .plotsvg import render_svg

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


_STATUS = {"valid": "solved", "stale": "OUT OF DATE: run with --solve", "none": "NOT SOLVED: run with --solve"}


def _solve_all(path, text, units):
    """Solve the blocks that are not up to date, top to bottom (a later block may read an earlier
    one's answer), and write each result into the file as it arrives."""
    done = set()
    while True:
        todo = [r for r in evaluate(text, global_units=units).results
                if r.kind == "solver" and r.solver["status"] != "valid" and r.solver["hash"] not in done]
        if not todo:
            return text
        r = todo[0]
        done.add(r.solver["hash"])
        print(f"{r.n:>3}  solving {r.source.strip()}", file=sys.stderr)
        out = solve_block(text, r.n, units, log=lambda m: print("       " + m, file=sys.stderr))
        if not out["ok"]:
            print(f"{r.n:>3}  FAILED  {out['message']}", file=sys.stderr)
            continue
        text = write_result(text, r.n, out["record"])
        path.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(prog="lens", description="Laconic Engineering Notebook System")
    ap.add_argument("file", nargs="?", help="worksheet file (.lens); omit with --serve")
    ap.add_argument("--tex", metavar="OUT", help="write a LaTeX document to OUT")
    ap.add_argument("--plots", metavar="DIR", help="write each plot as an SVG file in DIR")
    ap.add_argument("--solve", action="store_true",
                    help="run every !root/!minimize/!maximize block that is not up to date and store the results in the file")
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
    units = settings.global_units()
    if a.solve:
        text = _solve_all(Path(a.file), text, units)
    ws = evaluate(text, siunitx=bool(a.tex), global_units=units)
    results = ws.results
    if a.tex:
        Path(a.tex).write_text(document(results, title=Path(a.file).stem, declarations=ws.declarations),
                               encoding="utf-8")
        print(f"wrote {a.tex}")
    if a.plots:
        out = Path(a.plots)
        out.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r.kind == "plot":
                path = out / f"{Path(a.file).stem}-line{r.n}.svg"
                path.write_text(render_svg(r.plot, uid=r.n, standalone=True), encoding="utf-8")
                print(f"wrote {path}")
    for r in results:
        if r.kind == "error":
            print(f"{r.n:>3}  ERROR  {r.error}", file=sys.stderr)
        elif r.text and r.kind in ("assign", "expr"):
            print(f"{r.n:>3}  {r.text}" + ("   (out of date)" if r.stale else ""))
        elif r.kind == "solver":
            print(f"{r.n:>3}  {r.text}   ({_STATUS[r.solver['status']]})")


if __name__ == "__main__":
    main()
