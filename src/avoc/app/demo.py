"""The online demo: one small workspace that every visitor gets a fresh copy of.

Two steps:

- `pack` turns a finished workspace into a template: the files each episode was made from (video,
  subtitles) are copied into its folder, and the paths in `episode.json` are written relative to
  that folder, so the template can be moved to another machine.
- `serve` answers every visitor from their own copy of the template, found by a cookie. Copies
  left alone for a while are deleted, and one fresh copy is kept ready. Adding episodes and
  exporting are turned off (see `server.DEMO_OFF`).

Run from the repository root:

    uv run python -m avoc.app.demo pack WORKSPACE TEMPLATE
    uv run python -m avoc.app.demo serve TEMPLATE --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PATH_KEYS = ("source", "video", "vocals", "analysis", "subtitles", "display_subtitles")
"""The keys in `episode.json` that name a file."""
INPUT_FOLDER = "input"
"""Where `pack` puts the files an episode was made from that lay outside its folder."""
COOKIE = "avoc_demo"
LINK_SIZE = 256 * 1024
"""Files at least this big are linked into each visitor's copy instead of copied. They are only
read: media and caches. Everything under `labels/` is always copied."""
STARTER = "quality-starter.npz"
"""The low-quality hint's starter weights, when put in the template (scripts/demo/make_deploy.py
does), so the server needs no network to start. Otherwise they are downloaded."""


def pack(workspace: Path, template: Path) -> None:
    """Copy `workspace` to `template`, ready for `serve`. Cuts made for the page while labeling
    are kept (they save the first visitors the wait), the labels are left out unless the
    workspace has a `labels/` the demo should start from: `cast.json` and `purpose.json` are kept,
    so visitors can start labeling at once; the label database is not."""
    if template.exists():
        raise SystemExit(f"{template} exists already; remove it first")
    _cut_all(workspace)
    shutil.copytree(workspace / "episodes", template / "episodes")
    labels = template / "labels"
    labels.mkdir(parents=True)
    for name in ("cast.json", "purpose.json"):
        if (workspace / "labels" / name).is_file():
            shutil.copy2(workspace / "labels" / name, labels / name)
    for folder in sorted((template / "episodes").iterdir()):
        meta_path = folder / "episode.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        old_root = (workspace / "episodes" / folder.name).resolve()
        for key in PATH_KEYS:
            if not meta.get(key):
                continue
            path = Path(meta[key]).resolve()
            if path.is_relative_to(old_root):
                meta[key] = path.relative_to(old_root).as_posix()
                continue
            inputs = folder / INPUT_FOLDER
            inputs.mkdir(exist_ok=True)
            shutil.copy2(path, inputs / path.name)
            meta[key] = f"{INPUT_FOLDER}/{path.name}"
        copy = folder / "app_media" / "episode" / "copy.json"
        meta["demo_copy_ready"] = copy.is_file()
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Template written to {template}")


def _cut_all(workspace: Path) -> None:
    """Cut every line's vocals now, so the demo server, on a small share of one CPU, does not run
    FFmpeg while someone waits. The pictures come from the whole-episode copy, which the page
    plays when it is ready."""
    from avoc.service import WorkspaceService

    state = WorkspaceService(workspace)
    try:
        for clip in state.workspace.clips:
            state.media("audio", clip.id)
    finally:
        state.close()


def _place(source: str, target: str) -> None:
    """Link a big read-only file, or copy it when links are not allowed (Windows without
    developer mode). Called by `shutil.copytree` with plain strings."""
    path = Path(source)
    if path.stat().st_size >= LINK_SIZE and path.parent.name != "labels":
        with contextlib.suppress(OSError):
            Path(target).symlink_to(path.resolve())
            return
    shutil.copy2(source, target)


def make_copy(template: Path, root: Path) -> None:
    """A visitor's own workspace at `root`, made from `template`, with absolute paths again."""
    from avoc.video import copy_signature

    shutil.copytree(template, root, copy_function=_place, ignore=shutil.ignore_patterns(STARTER))
    for folder in sorted((root / "episodes").iterdir()):
        meta_path = folder / "episode.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for key in PATH_KEYS:
            if meta.get(key):
                meta[key] = str(folder.resolve() / meta[key])
        if meta.pop("demo_copy_ready", False):
            # The copy is the same; only the paths it is checked against changed.
            record = folder / "app_media" / "episode" / "copy.json"
            record.write_text(json.dumps(copy_signature(meta)), encoding="utf-8")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class Visit:
    root: Path
    app: Any
    state: Any
    used: float = field(default_factory=time.monotonic)


class DemoHub:
    """An ASGI app that hands each request to the visitor's own avoc app."""

    def __init__(
        self,
        template: Path,
        *,
        limit: int = 30,
        idle: float = 3600.0,
        models: tuple[str, ...] | None = None,
        prepare: bool = True,
    ) -> None:
        """`models` are the voiceprint models to read, the first one for grouping (all of
        avoc's by default); `prepare` gets ready in the background (see `_prepare`). Both are
        changed only in tests."""
        self.template = template.resolve()
        self.models = models
        self.limit, self.idle = limit, idle
        self.folder = Path(tempfile.mkdtemp(prefix="avoc-demo-"))
        self.visits: dict[str, Visit] = {}
        self.lock = threading.Lock()
        self.starter: Any = None
        self.spare: tuple[str, Visit] | None = None
        """A copy made before anyone asked, so the next visitor does not wait for one."""
        self.making_spare = False
        from fastapi import FastAPI
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        from avoc.app.server import STATIC

        self.files = FastAPI(docs_url=None, redoc_url=None)
        self.files.mount("/static", StaticFiles(directory=STATIC), name="static")
        self.files.get("/favicon.ico")(
            lambda: FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")
        )
        if prepare:
            threading.Thread(target=self._prepare, daemon=True).start()

    def _prepare(self) -> None:
        """Right after the server starts, so the first visitor does not wait for it: read the
        low-quality hint's starter weights, label a throwaway copy once (the first training
        loads its libraries and is several times slower than the next ones), and make a spare
        copy."""
        from avoc import quality

        with contextlib.suppress(Exception):
            bundled = self.template / STARTER
            path = bundled if bundled.is_file() else quality.starter_path()
            self.starter = quality.read_starter(path)
            for visit in list(self.visits.values()):
                self._give_starter(visit.state)
        with contextlib.suppress(Exception):
            _, visit = self._open()
            try:
                _warm_up(visit.state)
            finally:
                self._close(visit)
        self._make_spare()

    def _make_spare(self) -> None:
        with self.lock:
            if self.spare is not None or self.making_spare:
                return
            self.making_spare = True
        try:
            spare = self._open()
            with self.lock:
                self.spare = spare
        finally:
            self.making_spare = False

    def _take(self) -> tuple[str, Visit]:
        """A new visitor's copy: the spare if there is one, then another spare in the
        background."""
        with self.lock:
            spare, self.spare = self.spare, None
        if spare is not None:
            threading.Thread(target=self._make_spare, daemon=True).start()
            return spare
        return self._open()

    def _give_starter(self, state: Any) -> None:
        if self.starter is None:
            return
        with state.lock:
            state._starter = self.starter
            state._train_quality()

    def _open(self) -> tuple[str, Visit]:
        from avoc.app.server import AppState, create_app

        key = secrets.token_urlsafe(18)
        root = self.folder / key
        make_copy(self.template, root)
        state = (
            AppState(root, self.models, grouping=self.models[0]) if self.models else AppState(root)
        )
        state.demo = True
        self._give_starter(state)
        return key, Visit(root, create_app(state), state)

    def _close(self, visit: Visit) -> None:
        with contextlib.suppress(Exception):
            visit.state.close()
        shutil.rmtree(visit.root, ignore_errors=True)

    def _tidy(self) -> None:
        """Before a new copy: drop copies left alone too long, then the least recently used ones
        until there is room."""
        now = time.monotonic()
        with self.lock:
            oldest_first = sorted(self.visits, key=lambda k: self.visits[k].used)
            kept = [k for k in oldest_first if now - self.visits[k].used <= self.idle]
            gone = [k for k in oldest_first if k not in kept]
            gone += kept[: max(0, len(kept) - self.limit + 1)]
            dropped = [self.visits.pop(k) for k in gone]
        for visit in dropped:
            self._close(visit)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    spare = [self.spare[1]] if self.spare else []
                    for visit in [*self.visits.values(), *spare]:
                        self._close(visit)
                    shutil.rmtree(self.folder, ignore_errors=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        key = _cookie(scope)
        with self.lock:
            visit = self.visits.get(key or "")
        fresh = None
        if visit is None and scope["path"].startswith(("/static/", "/favicon")):
            # The page's own files are the same for everyone.
            await self.files(scope, receive, send)
            return
        if visit is None:
            if scope["path"] != "/":
                # Not a page load: a stale tab after its copy was dropped. Say so instead of
                # quietly answering from a new, empty copy.
                await _answer(send, 410, "This demo copy was closed. Reload the page.")
                return
            import anyio.to_thread

            self._tidy()
            key, visit = await anyio.to_thread.run_sync(self._take)
            with self.lock:
                self.visits[key] = visit
            fresh = key
        visit.used = time.monotonic()
        if fresh is None:
            await visit.app(scope, receive, send)
            return
        secure = _https(scope)
        cookie = f"{COOKIE}={fresh}; Path=/; HttpOnly; Max-Age={int(self.idle)}; " + (
            "SameSite=None; Secure" if secure else "SameSite=Lax"
        )

        async def send_with_cookie(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"set-cookie", cookie.encode())],
                }
            await send(message)

        await visit.app(scope, receive, send_with_cookie)


def _warm_up(state: Any) -> None:
    """Label a throwaway copy as a visitor would: enough lines of one character for guessing to
    start, a few others, and one marked low quality."""
    from avoc.labels import OTHER
    from avoc.model import MIN_GUESS_LABELS

    ids = [clip.id for clip in state.workspace.clips]
    n = MIN_GUESS_LABELS
    run = state.operations.execute
    role = run("label", {"clips": ids[:n], "new_role": True})["role"]
    run("label", {"clips": ids[n : n + 3], "label": OTHER})
    run("label", {"clips": ids[n + 3 : n + 4], "label": role, "unusable": True})


def _cookie(scope: dict[str, Any]) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in value.decode("latin-1").split(";"):
                key, _, found = part.strip().partition("=")
                if key == COOKIE:
                    return found
    return None


def _https(scope: dict[str, Any]) -> bool:
    """Behind a host's proxy the page is https while the app itself is plain http."""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-proto":
            return value == b"https"
    return scope.get("scheme") == "https"


async def _answer(send: Any, status: int, detail: str) -> None:
    body = json.dumps({"code": "demo_closed", "detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            # Browsers may keep a 410 and answer from it later, even after a new copy is made.
            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m avoc.app.demo", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    making = commands.add_parser("pack", help="turn a workspace into the demo's template")
    making.add_argument("workspace", type=Path)
    making.add_argument("template", type=Path)
    serving = commands.add_parser("serve", help="serve the demo")
    serving.add_argument("template", type=Path)
    serving.add_argument("--host", default="127.0.0.1")
    serving.add_argument("--port", type=int, default=int(os.environ.get("PORT", "7860")))
    serving.add_argument("--limit", type=int, default=30, help="most copies open at once")
    args = parser.parse_args()
    if args.command == "pack":
        pack(args.workspace, args.template)
        return
    import uvicorn

    hub = DemoHub(args.template, limit=args.limit)
    uvicorn.run(hub, host=args.host, port=args.port, log_level="warning", proxy_headers=True)


if __name__ == "__main__":
    main()
