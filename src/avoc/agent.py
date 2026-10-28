"""Agent operations share the workspace service and never create confirmed labels."""

from __future__ import annotations

import json
from typing import Any

from avoc.contracts import (
    AddBody,
    CommandBody,
    ExportBody,
    JobView,
    PageView,
    SuggestionBody,
    SummaryView,
)
from avoc.labels import ConflictError
from avoc.storage import connect

AGENT_OPERATIONS = frozenset({"suggest", "export", "add"})


def capabilities() -> dict[str, Any]:
    return {
        "version": 1,
        "queries": ["state", "clips", "clip", "suggestions", "jobs"],
        "operations": {
            "suggest": SuggestionBody.model_json_schema(),
            "export": ExportBody.model_json_schema(),
            "add": AddBody.model_json_schema(),
        },
        "command": CommandBody.model_json_schema(),
        "confirmation": (
            "Suggestions are not training labels. "
            "A person confirms them through the editing entry point."
        ),
    }


def query(workspace: Any, name: str, **options: Any) -> Any:
    with workspace.lock:
        workspace.retrain_if_changed()
        revision = workspace.store.revision
        if name == "state":
            return workspace.summary()
        if name == "jobs":
            return workspace.jobs.all()
        if name == "suggestions":
            db = connect(workspace.store.path)
            try:
                return [
                    {"id": i, "status": status, **json.loads(body)}
                    for i, status, body in db.execute(
                        "SELECT id,status,body FROM suggestions ORDER BY rowid DESC LIMIT 100"
                    )
                ]
            finally:
                db.close()
        if name == "clip":
            clip = workspace.workspace.by_id.get(options.get("id"))
            if clip is None:
                raise ValueError("No such clip")
            context = options.get("context", 2)
            if not isinstance(context, int) or not 0 <= context <= 5:
                raise ValueError("Context must be from 0 to 5 lines")
            same = [c for c in workspace.workspace.clips if c.episode == clip.episode]
            position = same.index(clip)
            return {
                "revision": revision,
                "clip": workspace.view(clip),
                "context": [
                    workspace.view(c)
                    for c in same[max(0, position - context) : position + context + 1]
                ],
                "media": {
                    "audio": f"/media/audio/{clip.id}.wav",
                    "video": f"/media/video/{clip.id}.mp4",
                },
            }
        if name != "clips":
            raise ValueError(f"Unknown query: {name}")
        limit = options.get("limit", 50)
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("Limit must be from 1 to 200")
        after = ""
        if cursor := options.get("cursor"):
            version, separator, after = cursor.partition(":")
            if not separator or not version.isdigit():
                raise ValueError("Invalid page cursor")
            if int(version) != revision:
                raise ConflictError("The workspace changed; start the list again")
        role = options.get("role")
        if role:
            role = next((r["name"] for r in workspace.store.roles if r["id"] == role), role)
        found = []
        for c in sorted(workspace.workspace.clips, key=lambda c: c.id):
            if c.id <= after or (options.get("episode") and c.episode != options["episode"]):
                continue
            if role and workspace.role_of(c) != role:
                continue
            if options.get("status") and workspace.status(c) != options["status"]:
                continue
            found.append(workspace.view(c))
            if len(found) > limit:
                break
        return {
            "revision": revision,
            "items": found[:limit],
            "next": f"{revision}:{found[limit - 1]['id']}" if len(found) > limit else None,
        }


def execute(workspace: Any, command: CommandBody) -> dict[str, Any]:
    if command.operation not in AGENT_OPERATIONS:
        raise ValueError(
            "Agents can submit suggestions and start exports; a person confirms labels"
        )
    return workspace.operations.execute(
        command.operation,
        command.payload,
        request_id=command.request_id,
        expected_revision=command.expected_revision,
    )


def router(workspace: Any) -> Any:
    from fastapi import APIRouter

    routes = APIRouter(prefix="/api/agent", tags=["agent"])

    @routes.get("/capabilities")
    def read_capabilities() -> dict[str, Any]:
        return capabilities()

    @routes.get("/state", response_model=SummaryView)
    def read_state() -> Any:
        return query(workspace, "state")

    @routes.get("/clips", response_model=PageView)
    def read_clips(
        episode: str | None = None,
        role: str | None = None,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Any:
        return query(
            workspace,
            "clips",
            episode=episode,
            role=role,
            status=status,
            limit=limit,
            cursor=cursor,
        )

    @routes.get("/clips/{clip}")
    def read_clip(clip: str, context: int = 2) -> Any:
        return query(workspace, "clip", id=clip, context=context)

    @routes.get("/suggestions")
    def read_suggestions() -> Any:
        return query(workspace, "suggestions")

    @routes.get("/jobs")
    def read_jobs() -> Any:
        return query(workspace, "jobs")

    @routes.get("/jobs/{job}", response_model=JobView)
    def read_job(job: str) -> Any:
        return workspace.jobs.get(job)

    @routes.post("/commands")
    def post_command(body: CommandBody) -> Any:
        return execute(workspace, body)

    return routes
