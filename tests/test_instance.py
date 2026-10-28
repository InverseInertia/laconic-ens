"""The packaged app reuses a running LENS, or the port the last one had (instance.py)."""
import socket

import pytest

from laconic import instance
from laconic.opened import sheets


@pytest.fixture(autouse=True)
def fresh_sheets():
    yield
    sheets.clear()


def _port(url):
    return int(url.rsplit(":", 1)[1])


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_takes_the_first_port_when_nothing_runs():
    port = _free_port()
    assert instance.claim(ports=[port, port + 1]) == port


def test_a_port_left_in_time_wait_by_a_stopped_lens_is_reclaimed():
    """A stopped server's connections linger in TIME_WAIT; the port must still count as free."""
    with socket.socket() as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen()
        client = socket.create_connection(("127.0.0.1", port))
        conn, _ = srv.accept()
        conn.close()            # the server side closes first, so its end goes to TIME_WAIT
        client.recv(1)
        client.close()
    assert instance.port_free(port)


def test_skips_a_port_another_program_holds():
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        taken = other.getsockname()[1]
        free = _free_port()
        assert not instance.is_lens(taken)
        assert instance.claim(ports=[taken, free]) == free


def test_hands_the_sheet_to_a_running_lens(server, tmp_path):
    sheet = tmp_path / "beam.lens"
    sheet.write_text("x = 1\n", encoding="utf-8")
    opened = []
    sheets.serve(opened.append)
    free = _free_port()
    assert instance.claim(str(sheet), ports=[free, _port(server)]) is None
    token = opened[0].removeprefix("/?sheet=")
    assert sheets.get(token) == sheet.resolve()


def test_a_lens_that_will_not_open_a_window_is_passed_over(server):
    free = _free_port()
    assert instance.claim(ports=[_port(server), free]) == free
