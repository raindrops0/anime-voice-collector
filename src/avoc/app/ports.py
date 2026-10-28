"""Pick the port for `avoc app`. Each running app answers WORKSPACE_PATH with the workspace it
shows, so a second start can tell "this workspace is already open" from "another workspace has the
port"."""

from __future__ import annotations

import json
import os
import shlex
import socket
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKSPACE_PATH = "/api/workspace"
DEFAULT_PORT = 8765
TRIED_PORTS = 20
"""How many ports from the first one are tried, both to find the workspace already open and to find
a free port."""


STARTED_BY = "AVOC_STARTED_BY"
"""Set by `note_start` to who started `avoc app`. It is in the environment so that the server
process of `--reload`, started again after each change, reports the process that was started by
hand, not itself."""


@dataclass(frozen=True)
class Choice:
    port: int
    running: bool
    """True when the workspace is already open on `port`, so nothing new is started."""
    server: dict[str, Any] | None = None
    """What the running server says about itself (see `server_info`), when `running`."""


def note_start() -> None:
    """Record this process as the one that started `avoc app`. Called once, before serving."""
    import subprocess
    import sys
    import time

    if STARTED_BY in os.environ:
        return
    command = subprocess.list2cmdline(sys.argv) if os.name == "nt" else shlex.join(sys.argv)
    os.environ[STARTED_BY] = json.dumps(
        {
            "pid": os.getpid(),
            "command": command,
            "folder": str(Path.cwd()),
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def server_info(workspace: Path) -> dict[str, Any]:
    """What WORKSPACE_PATH answers. `pid` is the process started by hand; `server_pid` is the one
    serving, which differs with `--reload`."""
    started = json.loads(os.environ.get(STARTED_BY, "{}"))
    return {
        "app": "avoc",
        "workspace": str(workspace.resolve()),
        "pid": os.getpid(),
        **started,
        "server_pid": os.getpid(),
    }


def _same(a: Path | str, b: Path | str) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def server_on(port: int, timeout: float = 1.0) -> dict[str, Any] | None:
    """What an avoc app on `port` says about itself, or None if the port has no avoc app."""
    url = f"http://127.0.0.1:{port}{WORKSPACE_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            answer = json.loads(response.read())
    except (OSError, ValueError):
        return None
    if isinstance(answer, dict) and answer.get("app") == "avoc" and "workspace" in answer:
        return answer
    return None


def wait_until_ready(port: int, timeout: float = 300.0, every: float = 0.2) -> bool:
    """Wait until the avoc app on `port` answers, so the browser is not opened on a page that
    cannot connect while the server still loads the workspace. False if it has not answered after
    `timeout` seconds."""
    import time

    end = time.monotonic() + timeout
    while server_on(port, timeout=every) is None:
        if time.monotonic() >= end:
            return False
        time.sleep(every)
    return True


def open_when_ready(port: int, timeout: float = 300.0) -> None:
    """Open the app's page in the browser once the server on `port` answers, without holding up
    the caller, which goes on to start the server."""
    import threading
    import webbrowser

    def open_page() -> None:
        if wait_until_ready(port, timeout):
            webbrowser.open(f"http://127.0.0.1:{port}/")

    threading.Thread(target=open_page, daemon=True).start()


def choose_port(workspace: Path, first: int, fixed: bool) -> Choice | None:
    """Where to serve `workspace`. If it is already open on one of the tried ports, that port with
    running=True. Otherwise the first free port from `first`. With `fixed` (the port was given on
    the command line) only `first` is tried. None when no tried port is free."""
    ports = [first] if fixed else range(first, first + TRIED_PORTS)
    taken = [port for port in ports if not is_free(port)]
    for port in taken:
        server = server_on(port)
        if server is not None and _same(server["workspace"], workspace):
            return Choice(port, running=True, server=server)
    for port in ports:
        if port not in taken:
            return Choice(port, running=False)
    return None
