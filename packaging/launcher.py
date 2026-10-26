"""Entry point for the frozen (PyInstaller) build.

Double-clicking the executable opens the UI. If LENS is already running, that
LENS opens the window and this one quits; otherwise this one starts the server,
on the same port as last time where it can (see laconic/instance.py).
`lens --window sheet.lens` does the same with that sheet open, saving back to
it: that is what a double-clicked .lens file runs (see install-linux.sh and
laconic/fileassoc.py). Any other arguments are passed straight to the normal CLI,
so the same binary also does `lens sheet.lens --tex out.tex`."""
import os
import sys
import threading
import time


def _quit_when_closed():
    """Exit once the UI window is gone. Gives up waiting for a first page after
    a minute, in case the window never opened."""
    from laconic.lifecycle import lifecycle

    start = time.monotonic()
    while not lifecycle.should_exit():
        if not lifecycle.ever_seen and time.monotonic() - start > 60:
            break
        time.sleep(1)
    os._exit(0)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # the solver worker is a spawned copy of this executable
    if sys.stdout is None or sys.stderr is None:  # windowed build has no console
        sys.stdout = sys.stderr = open(os.devnull, "w")
    from laconic.__main__ import main

    if sys.argv[1:2] in ([], ["--window"]):
        from laconic.instance import claim

        sheet = sys.argv[2:3]   # the sheet to open, if one was given
        port = claim(sheet[0] if sheet else None)
        if port is None:   # a running LENS opened the window
            sys.exit(0)
        sys.argv[1:] = ["--serve", "--app", "--port", str(port)] + sheet
        threading.Thread(target=_quit_when_closed, daemon=True).start()
    main()
