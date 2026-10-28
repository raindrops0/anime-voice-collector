"""The same checked operations for people using the page, scripts or agent tools."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from avoc.contracts import (
    AcceptBody,
    AddBody,
    ChangesBody,
    ExportBody,
    LabelBody,
    RevertBody,
    RoleBody,
    SuggestionBody,
)
from avoc.labels import IGNORED, OTHER
from avoc.language import say
from avoc.storage import retry_form

if TYPE_CHECKING:
    from avoc.service import WorkspaceService


class Operations:
    def __init__(self, workspace: WorkspaceService) -> None:
        self.workspace = workspace

    def execute(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        ws = self.workspace
        fingerprint = hashlib.sha256(
            json.dumps([operation, payload], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        with ws.lock:
            with ws.store.transaction():
                saved = ws.store.saved_request(request_id, fingerprint) if request_id else None
                if saved is not None:
                    result = self._replay(saved)
                else:
                    with ws.store.transaction(expected_revision):
                        if operation == "accept" and expected_revision is None:
                            raise ValueError(
                                "Read the workspace and give its revision to confirm a suggestion"
                            )
                        ws.retrain_if_changed()
                        result = self._run(operation, payload)
                        if request_id:
                            ws.store.remember_request(request_id, fingerprint, retry_form(result))
            if operation in {"export", "add"} and ws.jobs.get(result["id"])["state"] == "queued":
                ws.jobs.launch(result["id"])
            return result

    def _replay(self, saved: dict[str, Any]) -> dict[str, Any]:
        """A retried change answers with the step it made, and its lines and the overview as they
        are now: newer than when it ran, which is what the page needs anyway. Lines whose guesses
        moved are not listed again; `ripple` is 0 so the page does not wait for them."""
        if "updated_ids" not in saved:
            return saved
        ws = self.workspace
        rest = {k: v for k, v in saved.items() if k != "updated_ids"}
        by_id = ws.workspace.by_id
        updated = [ws.view(by_id[i]) for i in saved["updated_ids"] if i in by_id]
        return {**rest, "updated": updated, "ripple": 0, "state": ws.summary()}

    def _clips(self, ids: list[str]) -> None:
        if not ids or any(i not in self.workspace.workspace.by_id for i in ids):
            raise ValueError(say("片段不存在", "no such clip"))

    def _run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        ws = self.workspace
        if operation == "label":
            label_body = LabelBody.model_validate(payload)
            self._clips(label_body.clips)

            def make() -> Any:
                label = (
                    ws.store.new_role()
                    if label_body.new_role
                    else (label_body.label or "").strip() or None
                )
                cast = {"unnamed": [label]} if label_body.new_role else None
                role = ws.store.role(label) if label else None
                low = (
                    label_body.unusable
                    and label is not None
                    and label not in (OTHER, IGNORED)
                    and (role is None or bool(role.get("target")))
                )
                changes = [{"clip": c, "label": label} for c in label_body.clips]
                changes += [{"clip": c, "unusable": low} for c in label_body.clips]
                batch = ws.store.apply(changes, cast=cast)
                chosen["role"] = label
                return batch

            chosen: dict[str, Any] = {}
            return {**ws.change(make), **chosen}
        if operation == "changes":
            changes_body = ChangesBody.model_validate(payload)
            self._clips([c.clip for c in changes_body.changes])
            changes = [c.model_dump() for c in changes_body.changes]
            for change in changes:
                for key in ("label", "reject"):
                    if key in change:
                        change[key] = next(
                            (r["name"] for r in ws.store.roles if r["id"] == change[key]),
                            change[key],
                        )
            return ws.change(lambda: ws.store.apply(changes))
        if operation == "role":
            body = RoleBody.model_validate(payload)
            if body.new_name is not None:
                return ws.change(lambda: ws.store.rename_role(body.name, body.new_name or ""))
            return ws.change(lambda: self._update_role(body))
        if operation in ("undo", "revert"):
            report: dict[str, Any] = {"skipped": [], "kept": 0}

            def revert() -> Any:
                ids = (
                    ([t] if (t := ws.store.undo_target()) is not None else [])
                    if operation == "undo"
                    else RevertBody.model_validate(payload).batches
                )
                if not ids:
                    return None
                batch, found = ws.store.revert(ids, source=operation)
                report.update(found)
                return batch

            return {**ws.change(revert), **report}
        if operation == "add":
            from avoc.adding import clean_path
            from avoc.pipeline import next_episode_name
            from avoc.project import validate_name

            add = AddBody.model_validate(payload)
            if add.resume:
                raise ValueError("Resume the saved job by its ID")
            if not add.video.strip() or not add.subtitles.strip():
                raise ValueError("Both video and subtitles are needed")
            taken = [
                json.loads(row[0]).get("name")
                for row in ws.store._db.execute(
                    "SELECT body FROM jobs WHERE kind='add' "
                    "AND state IN ('queued','running','cancelling')"
                )
            ]
            name = validate_name(add.name or next_episode_name(ws.workspace.root))
            if not add.name:
                number = 1
                while name in taken:
                    name = f"ep{number:02d}"
                    number += 1
                    if (ws.workspace.root / "episodes" / name).exists():
                        taken.append(name)
            if name in taken or (ws.workspace.root / "episodes" / name).exists():
                raise ValueError(
                    "This episode name is already in use; resume its saved job instead"
                )
            record = {**add.model_dump(), "name": name}
            for key in ("video", "subtitles", "display_subtitles"):
                if record[key]:
                    record[key] = str(clean_path(record[key]).resolve())
            return ws.jobs.create("add", record, ws.store._db)
        if operation == "export":
            export_body = ExportBody.model_validate(payload)
            plan = ws.plan_export(
                export_body.roles, export_body.include_auto, export_body.form, Path(export_body.out)
            )
            return ws.jobs.create("export", plan, ws.store._db)
        if operation == "suggest":
            suggestion = SuggestionBody.model_validate(payload)
            self._clips([c.clip for c in suggestion.changes])
            identifier = uuid4().hex
            record = {**suggestion.model_dump(), "revision": ws.store.revision}
            ws.store._db.execute(
                "INSERT INTO suggestions(id,actor,body) VALUES (?,?,?)",
                (identifier, suggestion.actor, json.dumps(record)),
            )
            return {"id": identifier, "status": "pending", **record}
        if operation == "accept":
            accepted = AcceptBody.model_validate(payload)
            row = ws.store._db.execute(
                "SELECT body,status FROM suggestions WHERE id=?", (accepted.suggestion,)
            ).fetchone()
            if row is None or row[1] != "pending":
                raise ValueError("No pending suggestion with this ID")
            proposed = json.loads(row[0])
            result = self._run("changes", {"changes": proposed["changes"]})
            if result["batch"] is not None:
                ws.store.batches[-1]["suggestion"] = accepted.suggestion
                ws.store.batches[-1]["proposed_by"] = proposed["actor"]
            ws.store._db.execute(
                "UPDATE suggestions SET status='accepted' WHERE id=?", (accepted.suggestion,)
            )
            return result
        raise ValueError(f"Unknown operation: {operation}")

    def _update_role(self, body: RoleBody) -> Any:
        self.workspace.store.update_role(body.name, color=body.color, target=body.target)
        # A character change may alter every prediction without touching a labeled clip.
        return {"batch": None, "changes": []}
