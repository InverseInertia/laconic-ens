"""One LENS at a time, on the same port each time.

The page keeps its presets in the browser's storage, which belongs to the page's origin and so to
its port: a LENS that started on a port of its own opened with none of them. So the packaged app
looks for a LENS already running on one of PORTS and, finding one, asks it to open the window
(with the sheet, if one was given) and quits. Otherwise it takes the first free port of PORTS.

A port is checked for being free the way the server binds it, with SO_REUSEADDR, so that the
connections a stopped LENS leaves behind (TIME_WAIT, for a minute or two after it exits) do not
make the port look taken."""
import http.client
import json
import os
import socket
from pathlib import Path

PORTS = range(8765, 8775)
APP = "lens"   # what /api/hello answers, so another program on the port is not taken for LENS


def _ask(port, method, path, body=None, timeout=2.0):
    """The JSON a LENS on `port` answers, or None. http.client, not urllib: urllib would send
    a request for 127.0.0.1 through a proxy set in the environment."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
        r = conn.getresponse()
        return json.loads(r.read()) if r.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def port_free(port):
    with socket.socket() as s:
        if os.name != "nt":   # on Windows SO_REUSEADDR would let us bind over a live server
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def is_lens(port):
    r = _ask(port, "GET", "/api/hello")
    return isinstance(r, dict) and r.get("app") == APP


def hand_off(port, sheet=None):
    """Ask the LENS on `port` to open a window on `sheet` (or an empty one). True if it did."""
    path = str(Path(sheet).resolve()) if sheet else None
    r = _ask(port, "POST", "/api/window", {"path": path}, timeout=10.0)
    return isinstance(r, dict) and r.get("ok") is True


def claim(sheet=None, ports=PORTS):
    """None when a running LENS has taken over (the caller should exit), else the port to serve
    on: the first free one of `ports`, or any free port if all of them are in use."""
    for port in ports:
        if not port_free(port) and is_lens(port) and hand_off(port, sheet):
            return None
    for port in ports:
        if port_free(port):
            return port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
