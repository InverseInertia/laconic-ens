"""Entry point for the frozen (PyInstaller) build.

Double-clicking the executable starts the server on a free port and opens the
UI. `lens --window sheet.lens` does the same with that sheet open, saving back to
it: that is what a double-clicked .lens file runs (see install-linux.sh and
laconic/fileassoc.py). Any other arguments are passed straight to the normal CLI,
so the same binary also does `lens sheet.lens --tex out.tex`."""
import os
import socket
import sys
import threading
import time


def _free_port(preferred=8765):
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]


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
        sheet = sys.argv[2:3]   # the sheet to open, if one was given
        sys.argv[1:] = ["--serve", "--app", "--port", str(_free_port())] + sheet
        threading.Thread(target=_quit_when_closed, daemon=True).start()
    main()
