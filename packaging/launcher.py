"""Entry point for the frozen (PyInstaller) build.

Double-clicking the executable starts the server on a free port and opens the
UI. Any command-line arguments are passed straight to the normal CLI, so the
same binary also does `lens sheet.lens --tex out.tex`."""
import os
import socket
import sys


def _free_port(preferred=8765):
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # windowed build has no console
        sys.stdout = sys.stderr = open(os.devnull, "w")
    from laconic.__main__ import main

    if len(sys.argv) == 1:
        sys.argv += ["--serve", "--app", "--port", str(_free_port())]
    main()
