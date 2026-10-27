import argparse
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import browser, document, evaluate, markdown, settings
from .sheet import solve_block, solver_blocks
from .blockedit import apply
from .solver import write_result

EXAMPLES = Path(__file__).parent / "examples"

def _browser_env():
    """The environment for a browser we start. A PyInstaller build on Linux puts its own
    libraries first on LD_LIBRARY_PATH; a browser that inherits that loads the bundle's copies
    of libstdc++, libssl and friends instead of the system ones, and Firefox in particular
    fails to start. The bootloader keeps the user's value in LD_LIBRARY_PATH_ORIG."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = orig
    return env


def _spawn(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=_browser_env(), start_new_session=True)
        return True
    except OSError:
        return False


WM_CLASS = "lens"   # the StartupWMClass of the launcher install-linux.sh writes


def _app_args(url, exe):
    """The browser arguments for an app window. On Linux the desktop matches a window to its
    launcher, and so to the launcher's icon, by the window's WM_CLASS; a Chromium app window's is
    ("127.0.0.1", "Google-chrome") or the like, which no LENS launcher names, so the panel showed the
    browser's icon or none (#66). --class sets it, but only in a browser process of its own:
    a window opened through an already running browser takes that browser's class. Hence a
    profile of LENS's own, kept in the cache folder (or the sandbox's, see browser.profile_dir)."""
    args = [f"--app={url}"]
    if sys.platform.startswith("linux"):
        args = [f"--class={WM_CLASS}", f"--user-data-dir={browser.profile_dir(exe)}",
                "--no-first-run", "--no-default-browser-check"] + args
    return args


def _launch(url, app):
    """--app opens a Chromium-family window with no tabs or address bar, which
    gives the page more of the keyboard (Ctrl+T is a new tab in a normal tab)."""
    if app:
        exe = browser.find()
        if exe and _spawn([exe] + _app_args(url, exe)):
            return
        print("No Chromium-based browser found, opening the default browser instead")
    # GTK browsers print harmless messages to the terminal; _spawn keeps them out of it.
    if sys.platform.startswith("linux") and shutil.which("xdg-open") and _spawn(["xdg-open", url]):
        return
    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass
    print(f"Could not open a browser; open {url} by hand")


_STATUS = {"valid": "solved", "stale": "OUT OF DATE: run with --solve", "none": "NOT SOLVED: run with --solve"}


def _solve_all(path, text, units):
    """Solve the blocks that are not up to date, top to bottom (a later block may read an earlier
    one's answer), and write each result into the file as it arrives."""
    done = set()
    while True:
        todo = [r for r in solver_blocks(text, units) if r.solver.status != "valid" and r.solver.hash not in done]
        if not todo:
            return text
        r = todo[0]
        done.add(r.solver.hash)
        print(f"{r.n:>3}  solving {r.source.strip()}", file=sys.stderr)
        out = solve_block(text, r.n, units, log=lambda m: print("       " + m, file=sys.stderr))
        if not out["ok"]:
            print(f"{r.n:>3}  FAILED  {out['message']}", file=sys.stderr)
            continue
        text = apply(text, write_result(text, r.n, out["record"]))
        path.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(prog="lens", description="Laconic Engineering Notebook System")
    ap.add_argument("file", nargs="?", help="worksheet file (.lens); with --serve, the sheet the page opens")
    ap.add_argument("--tex", metavar="OUT", help="write a LaTeX document to OUT")
    ap.add_argument("--md", metavar="OUT", help="write a Markdown note (Obsidian style) to OUT")
    ap.add_argument("--pdf", metavar="OUT", help="write a PDF to OUT (needs a Chromium-based browser: Chrome, Edge, Brave...)")
    ap.add_argument("--plots", metavar="DIR", help="write each plot as an SVG file in DIR")
    ap.add_argument("--solve", action="store_true",
                    help="run every !root/!minimize/!maximize block that is not up to date and store the results in the file")
    ap.add_argument("--serve", action="store_true", help="start the web UI")
    ap.add_argument("--open", action="store_true", help="with --serve, open the default browser")
    ap.add_argument("--app", action="store_true", help="with --serve, open a Chromium app window")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--register-files", action="store_true",
                    help="Windows build: open double-clicked .lens files in LENS, with their own icon")
    ap.add_argument("--unregister-files", action="store_true", help="undo --register-files")
    ap.add_argument("--export-examples", metavar="DIR", help="copy the example worksheets into DIR and exit")
    a = ap.parse_args()

    if a.register_files or a.unregister_files:
        from .fileassoc import main as files
        sys.exit(files(undo=a.unregister_files))

    if a.export_examples:
        out = Path(a.export_examples)
        out.mkdir(parents=True, exist_ok=True)
        for p in sorted(EXAMPLES.glob("*.lens")):
            shutil.copyfile(p, out / p.name)
            print(f"wrote {out / p.name}")
        return

    if a.serve:
        import uvicorn
        from . import server
        if a.file:
            server.OPENED = Path(a.file).resolve()
        url = f"http://127.0.0.1:{a.port}"
        # Another launch of the packaged app hands its window to this server (instance.py).
        server.OPEN_WINDOW = lambda path: threading.Thread(target=_launch, args=(url + path, a.app)).start()
        # Always printed: the browser may fail to start, or start without showing a window.
        print(f"laconic running at {url} (open it in a browser if no window appears)")
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
    # The Markdown and PDF math is the live view's flavour, not siunitx, so it needs a run of its own.
    live = evaluate(text, global_units=units).results if a.tex and (a.md or a.pdf) else results
    if a.md:
        Path(a.md).write_text(markdown(live, title=Path(a.file).stem), encoding="utf-8")
        print(f"wrote {a.md}")
    if a.pdf:
        from . import pdfdoc
        try:
            Path(a.pdf).write_bytes(pdfdoc.pdf(pdfdoc.page(live, title=Path(a.file).stem)))
        except (RuntimeError, subprocess.TimeoutExpired) as e:   # NoBrowser is a RuntimeError
            sys.exit(f"PDF export failed: {e}")
        print(f"wrote {a.pdf}")
    if a.plots:
        out = Path(a.plots)
        out.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r.plot:
                path = out / f"{Path(a.file).stem}-line{r.n}.svg"
                path.write_text(r.plot.image(uid=r.n), encoding="utf-8")
                print(f"wrote {path}")
    for r in results:
        if r.kind == "error":
            print(f"{r.n:>3}  ERROR  {r.error}", file=sys.stderr)
        elif r.text and r.kind in ("assign", "expr"):
            print(f"{r.n:>3}  {r.text}" + ("   (out of date)" if r.stale else ""))
        elif r.solver:
            print(f"{r.n:>3}  {r.text}   ({_STATUS[r.solver.status]})")


if __name__ == "__main__":
    main()
