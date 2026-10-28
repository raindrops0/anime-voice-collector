"""Local server: gives the web page clips, predictions and media, takes in labels, and retrains
after each label.

Listens only on 127.0.0.1. State is kept in memory. Each change is written to the label records
first, then memory is updated. If the process crashes, restarting it picks up where it left off.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from pathlib import Path
from typing import Any

from avoc.adding import clean_path
from avoc.app.ports import WORKSPACE_PATH, server_info
from avoc.contracts import (
    AddBody,
    AvatarBody,
    ChangesBody,
    ChangeView,
    ClipView,
    CommandBody,
    ExportBody,
    ForgetBody,
    JobView,
    LabelBody,
    PairsBody,
    PickBody,
    PrefetchBody,
    PurposeBody,
    QueueBody,
    RevertBody,
    RoleBody,
    SnapshotView,
    SpokenBody,
    SubtitleStylesBody,
    SummaryView,
)
from avoc.contracts import (
    QueuedEpisode as QueuedEpisode,
)
from avoc.labels import ConflictError
from avoc.language import LANGUAGE, say
from avoc.playback import _cut_audio as _cut_audio
from avoc.project import free_export_folder as free_export_folder
from avoc.service import WorkspaceService as AppState
from avoc.stages.captions import marked_note
from avoc.video import COPY_FOLDER
from avoc.workspace import DEFAULT_MODELS

STATIC = Path(__file__).parent / "static"

RELOAD_WORKSPACE = "AVOC_RELOAD_WORKSPACE"
RELOAD_MODELS = "AVOC_RELOAD_MODELS"
RELOAD_DEVICE = "AVOC_RELOAD_DEVICE"


def reloaded_app() -> Any:
    """The app for `avoc app --reload`: uvicorn starts it afresh in a new process after each code
    change, with the workspace and models `avoc app` put in the environment."""
    models = tuple(m for m in os.environ.get(RELOAD_MODELS, "").split(",") if m)
    device = os.environ.get(RELOAD_DEVICE, "cpu")
    return create_app(
        AppState(
            Path(os.environ[RELOAD_WORKSPACE]),
            models or DEFAULT_MODELS,
            device=device,
            background=True,
        )
    )


DEMO_OFF = (
    "/api/add",
    "/api/pick",
    "/api/show-folder",
    "/api/install-ffmpeg",
    "/api/audio-tracks",
    "/api/subtitle-styles",
    "/api/export",
)
"""What the online demo turns off: everything that reads or writes files on the server's disk
outside the workspace, or starts long work on it. Commands that add or export are refused in
`Operations` too."""


def _demo_off(method: str, path: str) -> bool:
    if path == "/api/doctor":
        return True
    return method == "POST" and any(path == p or path.startswith(p + "/") for p in DEMO_OFF)


def _ignore_closed_connection(loop: Any, context: dict[str, Any]) -> None:
    """On Windows, asyncio prints a long ConnectionResetError traceback each time the browser
    drops a connection first (a refresh, a closed tab, a video seek). It is harmless, so it is not
    shown; every other error is printed as usual."""
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)


@contextlib.asynccontextmanager
async def _quiet_closed_connections(_app: Any) -> Any:
    import asyncio

    asyncio.get_running_loop().set_exception_handler(_ignore_closed_connection)
    yield


def create_app(state: AppState) -> Any:
    from fastapi import FastAPI, HTTPException
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import ValidationError

    @contextlib.asynccontextmanager
    async def lifespan(app: Any) -> Any:
        async with _quiet_closed_connections(app):
            try:
                yield
            finally:
                state.close()

    app = FastAPI(title="avoc", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_fields(_request: Any, exc: Any) -> Any:
        fields = [{k: v for k, v in item.items() if k != "ctx"} for item in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_request",
                "detail": say("请求中的字段不正确", "The request has invalid fields"),
                "fields": fields,
            },
        )

    @app.exception_handler(ValueError)
    async def invalid_request(_request: Any, exc: ValueError) -> Any:
        if isinstance(exc, ConflictError):
            return JSONResponse(
                status_code=409, content={"code": "revision_conflict", "detail": str(exc)}
            )
        if isinstance(exc, ValidationError):
            return JSONResponse(
                status_code=422,
                content={
                    "code": "invalid_request",
                    "detail": "The request has invalid fields",
                    "fields": exc.errors(include_context=False),
                },
            )
        return JSONResponse(
            status_code=400, content={"code": "invalid_request", "detail": str(exc)}
        )

    @app.middleware("http")
    async def always_check_page_files(request: Any, call_next: Any) -> Any:
        """Answer in the page's language (see avoc.language), and make the browser check the page,
        styles and script with the server every time (an unchanged file only gets a 304). Without
        that header the browser caches by modification time for a while, so a refresh after a UI
        change may still use the old styles or script. The same for cuts and episode copies: their
        address stays the same when PICTURE_PAD changes or a copy is made again."""
        LANGUAGE.set("en" if request.headers.get("x-language") == "en" else "zh")
        path = request.url.path
        if state.demo and _demo_off(request.method, path):
            return JSONResponse(
                status_code=403,
                content={
                    "code": "demo",
                    "detail": say("试用版不能做这一步", "The demo cannot do this"),
                },
            )
        response = await call_next(request)
        if path == "/" or path.startswith(("/static/", "/media/", "/episode-media/")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def clips_where(keep: Any) -> list[dict[str, Any]]:
        return [state.view(c) for c in state.workspace.clips if keep(c)]

    from avoc.agent import router

    app.include_router(router(state))

    @app.post("/api/commands")
    def post_command(body: CommandBody) -> dict[str, Any]:
        return state.operations.execute(
            body.operation,
            body.payload,
            request_id=body.request_id,
            expected_revision=body.expected_revision,
        )

    @app.get("/api/jobs/{job}", response_model=JobView)
    def read_job(job: str) -> dict[str, Any]:
        return state.jobs.get(job)

    @app.post("/api/jobs/{job}/cancel", response_model=JobView)
    def cancel_job(job: str) -> dict[str, Any]:
        return state.jobs.cancel(job)

    @app.post("/api/jobs/{job}/resume", response_model=JobView)
    def resume_job(job: str) -> dict[str, Any]:
        return state.jobs.resume(job)

    @app.get(WORKSPACE_PATH)
    def read_workspace() -> dict[str, Any]:
        """Which workspace this server shows and who started it, so a second `avoc app` can tell
        whether the same workspace is already open on a port. No lock: it must answer even while
        the app is busy."""
        return server_info(state.workspace.root)

    @app.get("/api/revision")
    def read_revision() -> dict[str, int]:
        from avoc.storage import connect

        db = connect(state.store.path)
        try:
            return {
                "revision": db.execute("SELECT revision FROM state WHERE singleton=1").fetchone()[0]
            }
        finally:
            db.close()

    @app.get("/api/snapshot", response_model=SnapshotView)
    def read_snapshot() -> dict[str, Any]:
        with state.lock:
            summary = state.summary()
            return {"state": summary, "clips": [state.view(c) for c in state.workspace.clips]}

    @app.get("/api/state", response_model=SummaryView)
    def read_state() -> dict[str, Any]:
        with state.lock:
            return state.summary()

    @app.get("/api/clips", response_model=list[ClipView], response_model_exclude_unset=True)
    def read_clips(
        episode: str | None = None, role: str | None = None, maybe: bool = False
    ) -> list[dict[str, Any]]:
        with state.lock:
            state.retrain_if_changed()
            if role is not None:
                return state.role_clips(role, only_maybe=maybe)
            return clips_where(lambda c: episode is None or c.episode == episode)

    @app.get("/api/groups")
    def read_groups(episode: str | None = None) -> list[dict[str, Any]]:
        with state.lock:
            return state.groups(episode)

    @app.get("/api/references")
    def read_references(name: str) -> list[dict[str, Any]]:
        with state.lock:
            return state.references(name)

    @app.post("/api/label", response_model=ChangeView, response_model_exclude_unset=True)
    def post_label(body: LabelBody) -> dict[str, Any]:
        return state.operations.execute("label", body.model_dump())

    @app.post("/api/changes", response_model=ChangeView, response_model_exclude_unset=True)
    def post_changes(body: ChangesBody) -> dict[str, Any]:
        return state.operations.execute("changes", body.model_dump())

    @app.post("/api/undo", response_model=ChangeView, response_model_exclude_unset=True)
    def post_undo() -> dict[str, Any]:
        return state.operations.execute("undo", {})

    @app.post("/api/revert", response_model=ChangeView, response_model_exclude_unset=True)
    def post_revert(body: RevertBody) -> dict[str, Any]:
        return state.operations.execute("revert", body.model_dump())

    @app.get("/api/history")
    def read_history(before: int | None = None, limit: int = 50) -> dict[str, Any]:
        """The newest steps first. Each names its first line's text, so it can be recognized."""
        with state.lock:
            entries = state.store.history(limit + 1, before)
            for entry in entries:
                clip = state.workspace.by_id.get(entry["first"] or "")
                entry["text"] = clip.text if clip else None
                entry["episode"] = clip.episode if clip else None
            return {"entries": entries[:limit], "more": len(entries) > limit}

    @app.post("/api/roles", response_model=ChangeView, response_model_exclude_unset=True)
    def post_role(body: RoleBody) -> dict[str, Any]:
        return state.operations.execute("role", body.model_dump())

    @app.post("/api/roles/avatar")
    def post_avatar(body: AvatarBody) -> dict[str, Any]:
        try:
            state.save_avatar(body.name, body.image)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        with state.lock:
            return state.summary()

    @app.post("/api/export")
    def post_export(body: ExportBody) -> dict[str, Any]:
        try:
            return state.export(body.roles, body.include_auto, body.form, Path(body.out))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/purpose")
    def post_purpose(body: PurposeBody) -> dict[str, Any]:
        try:
            with state.lock:
                state.set_purpose(body.purpose)
                return state.summary()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/spoken-language")
    def post_spoken_language(body: SpokenBody) -> dict[str, Any]:
        try:
            with state.lock:
                state.set_spoken(body.episode, body.language)
                return state.summary()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/audio-tracks")
    def post_audio_tracks(body: SubtitleStylesBody) -> dict[str, Any]:
        """The audio tracks of a video, and the one `avoc add` would take with no language given,
        so the add form can show them."""
        from dataclasses import asdict

        from avoc.audio import audio_tracks, can_read
        from avoc.pipeline import choose_track
        from avoc.stages.text_language import from_tag

        path = clean_path(body.path)
        if not path.is_file():
            raise HTTPException(400, say(f"找不到视频：{path}", f"cannot find the video: {path}"))
        tracks = audio_tracks(path)
        if not tracks and not can_read(path):
            raise HTTPException(
                400,
                say(
                    "FFmpeg 读不了这个文件，它是视频吗",
                    "FFmpeg cannot read this file. Is it a video?",
                ),
            )
        if not tracks:
            return {"tracks": [], "number": None, "language": None, "from": None}
        number, language, how = choose_track(tracks, None)
        return {
            "tracks": [{**asdict(t), "language": from_tag(t.tag)} for t in tracks],
            "number": number,
            "language": language,
            "from": how,
        }

    @app.get("/api/doctor")
    def read_doctor() -> list[dict[str, Any]]:
        from dataclasses import asdict

        from avoc.doctor import checks

        return [asdict(c) for c in checks(state.workspace.root.resolve())]

    installing = threading.Lock()

    @app.post("/api/install-ffmpeg")
    def post_install_ffmpeg() -> dict[str, Any]:
        """Install FFmpeg with Scoop, and Scoop first when missing; takes a few minutes."""
        from avoc.doctor import install_ffmpeg

        if not installing.acquire(blocking=False):
            raise HTTPException(409, say("已经在装了", "already installing"))
        try:
            ok, output = install_ffmpeg()
        finally:
            installing.release()
        return {"ok": ok, "output": output}

    @app.get("/api/add")
    def read_adding() -> dict[str, Any]:
        return state.adding.status()

    @app.post("/api/add")
    def post_add(body: AddBody) -> dict[str, Any]:
        try:
            if body.resume:
                return state.adding.carry_on(body.resume)
            if not body.video.strip() or not body.subtitles.strip():
                raise ValueError(
                    say("视频和字幕都要填", "both the video and the subtitles are needed")
                )
            shown = clean_path(body.display_subtitles) if body.display_subtitles.strip() else None
            name = body.name.strip() or None
            if name and name in state.workspace.episodes:
                raise ValueError(
                    say(
                        f"已经有一集叫 {name}，换个名字",
                        f"there is already an episode named {name}; choose another name",
                    )
                )
            return state.adding.start(
                clean_path(body.video),
                clean_path(body.subtitles),
                body.offset,
                name=name,
                styles=body.styles,
                spoken=body.spoken or None,
                display_subtitles=shown,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/add/queue")
    def post_add_queue(body: QueueBody) -> dict[str, Any]:
        try:
            if body.resume:
                return state.adding.carry_on_all(body.resume)
            taken = [e.name for e in body.episodes if e.name in state.workspace.episodes]
            if taken:
                raise ValueError(
                    say(
                        f"这些集名已经有了：{'、'.join(taken)}",
                        f"these names are taken already: {', '.join(taken)}",
                    )
                )
            return state.adding.enqueue(
                [
                    {
                        "name": e.name.strip(),
                        "video": clean_path(e.video),
                        "subtitles": clean_path(e.subtitles),
                        "display_subtitles": clean_path(e.display_subtitles)
                        if e.display_subtitles.strip()
                        else None,
                    }
                    for e in body.episodes
                ],
                body.offset,
                body.styles,
                body.spoken or None,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/add/pairs")
    def post_add_pairs(body: PairsBody) -> dict[str, Any]:
        """The videos and subtitles in two folders, paired by episode number."""
        from avoc.batch import pair

        try:
            return pair(body.videos, body.subtitles, body.display_subtitles)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/subtitle-styles")
    def post_subtitle_styles(body: SubtitleStylesBody) -> dict[str, Any]:
        """The styles in a subtitle file and the ones picked as dialogue, so the person can check
        and change them before adding the episode."""
        from avoc.stages.subtitle import describe_styles
        from avoc.stages.text_subtitle import style_languages, subtitle_languages

        path = clean_path(body.path)
        try:
            if not path.is_file():
                raise ValueError(
                    say(f"找不到字幕文件：{path}", f"cannot find the subtitles: {path}")
                )
            found = describe_styles(path)
            languages = subtitle_languages(path, found["picked"] or None)
            by_style = style_languages(path, [s["name"] for s in found["styles"]] or None)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            **found,
            "marked": marked_note(found["marked"]) if found["marked"] else None,
            "languages": list(languages),
            "style_languages": by_style,
        }

    @app.post("/api/pick")
    def post_pick(body: PickBody) -> dict[str, Any]:
        """Open the system's file window on this machine and wait for the person (see picker)."""
        from avoc.app.picker import pick, start_folder

        try:
            return {"path": pick(body.kind, start_folder(body.current, Path.cwd()))}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/show-folder")
    def post_show_folder(body: SubtitleStylesBody) -> dict[str, Any]:
        """Open a folder, such as the export just written, in the file manager on this machine."""
        from avoc.app.picker import show_folder

        try:
            show_folder(clean_path(body.path))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {}

    @app.post("/api/add/stop")
    def post_add_stop() -> dict[str, Any]:
        return state.adding.stop()

    @app.post("/api/add/forget")
    def post_add_forget(body: ForgetBody) -> dict[str, Any]:
        try:
            state.adding.forget(body.episode)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return state.summary()

    # The avatar route must come before /media/{kind}/{clip_id}, or "avatar" would be
    # taken as a kind.
    @app.get("/media/avatar/{file}")
    def read_avatar(file: str) -> Any:
        path = state.workspace.labels_dir / "avatars" / file
        if not re.fullmatch(r"[0-9a-f]{16}\.(jpg|png)", file) or not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/media/{kind}/{clip_id}")
    def read_media(kind: str, clip_id: str, context: int = 0, fresh: int = 0) -> Any:
        clip_id = clip_id.rsplit(".", 1)[0]
        if kind not in ("audio", "video"):
            raise HTTPException(404)
        try:
            return FileResponse(state.media(kind, clip_id, context, fresh=bool(fresh)))
        except KeyError as exc:
            raise HTTPException(404) from exc
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/prefetch")
    def post_prefetch(body: PrefetchBody) -> dict[str, Any]:
        """The web page calls this when the person sees a line. In the background, clips from one
        minute before and after are cut first."""
        try:
            queued = state.prefetch(body.clip)
            return {
                "queued": queued,
                "player": state.player(state.workspace.by_id[body.clip].episode),
            }
        except KeyError as exc:
            raise HTTPException(404) from exc

    @app.get("/episode-media/{episode}/{kind}")
    def read_episode_media(episode: str, kind: str) -> Any:
        """The whole-episode copy: `video` (picture only), `vocals` or `original` (sound)."""
        meta = state.workspace.episodes.get(episode)
        if meta is None or kind not in ("video", "vocals", "original"):
            raise HTTPException(404)
        if not state.player(episode)["ready"]:
            raise HTTPException(
                404, say("这一集的整集副本还没做好", "this episode's copy is not ready")
            )
        name = "video.mp4" if kind == "video" else f"{kind}.m4a"
        path = Path(meta["directory"]) / "app_media" / COPY_FOLDER / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/favicon.ico")
    def favicon() -> Any:
        return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")

    @app.get("/")
    def index() -> Any:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
