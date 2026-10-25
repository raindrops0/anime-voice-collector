"""Picking the port for `avoc app`: a free one, or the page of the same workspace already open. The
open app is a small HTTP server that answers like avoc, so no real app starts during tests."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from avoc.app import ports
from avoc.app.ports import WORKSPACE_PATH, choose_port
from avoc.app.server import AppState, create_app


def serve(answer: dict[str, Any]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(answer).encode() if self.path == WORKSPACE_PATH else b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def open_app(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    """An app that shows `tmp_path / "ws"`, and the port it holds."""
    workspace = tmp_path / "ws"
    server = serve({"app": "avoc", "workspace": str(workspace), "pid": 4321, "server_pid": 4321})
    yield server.server_address[1], workspace
    server.shutdown()
    server.server_close()


def test_the_same_workspace_is_found_open(open_app: tuple[int, Path]) -> None:
    port, workspace = open_app
    choice = choose_port(workspace, port, fixed=False)
    assert choice is not None and choice.running and choice.port == port
    assert choice.server is not None and choice.server["pid"] == 4321
    # Given another way, such as with a relative part, it is still the same folder.
    assert choose_port(workspace / ".." / "ws", port, fixed=True) == choice


def test_another_workspace_moves_to_a_free_port(open_app: tuple[int, Path], tmp_path: Path) -> None:
    port, _ = open_app
    choice = choose_port(tmp_path / "other", port, fixed=False)
    assert choice is not None and not choice.running and choice.port != port
    assert ports.is_free(choice.port)
    # A port given on the command line is not changed behind the user's back.
    assert choose_port(tmp_path / "other", port, fixed=True) is None


def test_a_program_that_is_not_avoc_is_not_taken_for_it(tmp_path: Path) -> None:
    server = serve({"hello": "world"})
    port = server.server_address[1]
    try:
        choice = choose_port(tmp_path / "ws", port, fixed=False)
        assert choice is not None and not choice.running and choice.port != port
    finally:
        server.shutdown()
        server.server_close()


def test_the_app_says_who_started_it(tmp_path: Path, monkeypatch: Any) -> None:
    # Set first, so the variable note_start writes is removed again after the test.
    monkeypatch.setenv(ports.STARTED_BY, "{}")
    monkeypatch.delenv(ports.STARTED_BY)
    monkeypatch.setattr("sys.argv", ["avoc", "app", "ws"])
    ports.note_start()
    root = tmp_path / "ws"
    (root / "episodes").mkdir(parents=True)
    client = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    answer = client.get(WORKSPACE_PATH).json()
    assert answer["app"] == "avoc" and Path(answer["workspace"]) == root.resolve()
    assert answer["command"] == "avoc app ws" and answer["pid"] == answer["server_pid"]
    assert answer["started"] and answer["folder"]
