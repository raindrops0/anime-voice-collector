"""Recovery, shared operations, concurrent starts and complete client updates."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from avoc.adding import Adding
from avoc.agent import execute, query
from avoc.app.server import create_app
from avoc.contracts import CommandBody
from avoc.exporting import run_export
from avoc.jobs import Jobs, work
from avoc.labels import ConflictError, LabelStore
from avoc.service import WorkspaceService
from avoc.stages.export import export
from avoc.storage import connect
from tests.test_app import _workspace


def service(tmp_path: Path) -> WorkspaceService:
    return WorkspaceService(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")


def test_failed_rename_keeps_labels_characters_and_identity_together(tmp_path, monkeypatch):
    store = LabelStore(tmp_path)
    store.apply([{"clip": "a", "label": "A"}])
    original = dict(store.roles[0])
    with monkeypatch.context() as change:

        def failed(*args, **kwargs):
            raise OSError("disk full")

        change.setattr(store, "apply", failed)
        with pytest.raises(OSError, match="disk full"):
            store.rename_role("A", "B")
    reopened = LabelStore(tmp_path)
    assert reopened.roles == [original]
    assert reopened.labels == {"a": "A"}
    store.rename_role("A", "B")
    assert store.roles[0]["id"] == original["id"]
    store.undo()
    assert store.roles[0]["id"] == original["id"]


def test_legacy_import_preserves_files_and_recovers_only_an_unfinished_tail(tmp_path):
    folder = tmp_path / "labels"
    folder.mkdir()
    event = {
        "batch": 1,
        "time": "t",
        "source": "human",
        "undo_of": None,
        "changes": [{"clip": "a", "before": None, "after": "A"}],
    }
    content = json.dumps(event).encode() + b'\n{"batch":2,'
    path = folder / "events.jsonl"
    path.write_bytes(content)
    with pytest.warns(RuntimeWarning, match="original is kept"):
        store = LabelStore(folder)
    assert store.labels == {"a": "A"}
    assert path.read_bytes() == content
    store.apply([{"clip": "b", "label": "A"}])
    assert LabelStore(folder).labels == {"a": "A", "b": "A"}
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "events.jsonl").write_bytes(b"{broken}\n" + json.dumps(event).encode())
    with pytest.raises(ValueError, match="record 1"):
        LabelStore(broken)


def test_two_stores_do_not_reuse_batch_numbers_or_drop_other_writes(tmp_path):
    first, second = LabelStore(tmp_path), LabelStore(tmp_path)
    first.apply([{"clip": "a", "label": "A"}])
    second.apply([{"clip": "b", "label": "B"}])
    first.apply([{"clip": "c", "label": "A"}])
    again = LabelStore(tmp_path)
    assert again.labels == {"a": "A", "b": "B", "c": "A"}
    assert [b["batch"] for b in again.batches] == [1, 2, 3]


def test_separate_processes_keep_every_committed_batch(tmp_path):
    LabelStore(tmp_path)
    program = (
        "import sys; from pathlib import Path; from avoc.labels import LabelStore; "
        "LabelStore(Path(sys.argv[1])).apply([{'clip':sys.argv[2],'label':'A'}])"
    )

    def write(number):
        subprocess.run(
            [sys.executable, "-c", program, str(tmp_path), str(number)],
            check=True,
            capture_output=True,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(4)))
    store = LabelStore(tmp_path)
    assert set(store.labels) == {"0", "1", "2", "3"}
    assert [b["batch"] for b in store.batches] == [1, 2, 3, 4]


def test_complete_prediction_changes_are_sent_to_the_client(tmp_path, monkeypatch):
    monkeypatch.setattr("avoc.service.MIN_GUESS_LABELS", 1)
    ws = service(tmp_path)
    ids = list(ws.workspace.by_id)
    ws.operations.execute("label", {"clips": [ids[0]], "label": "A"})
    ws.operations.execute("label", {"clips": [ids[3]], "label": "B"})
    before = ws._snapshot()
    result = ws.operations.execute("label", {"clips": [ids[1]], "label": "A"})
    after = ws._snapshot()
    assert {i for i in after if after[i] != before[i]} <= {c["id"] for c in result["updated"]}


def test_invalid_mixed_batch_is_rejected_before_any_write(tmp_path):
    ws = service(tmp_path)
    client = TestClient(create_app(ws))
    clip = ws.workspace.clips[0].id
    for invalid in ({"clip": clip, "reject": "A"}, {"clip": clip, "unusable": "false"}):
        response = client.post(
            "/api/changes", json={"changes": [{"clip": clip, "label": "A"}, invalid]}
        )
        assert response.status_code == 422
        assert not ws.store.labels and not ws.store.batches
    duplicate = client.post(
        "/api/changes",
        json={"changes": [{"clip": clip, "unusable": True}, {"clip": clip, "unusable": False}]},
    )
    assert duplicate.status_code == 422 and not ws.store.unusable


def test_retries_revisions_and_agent_confirmation_are_independent(tmp_path):
    ws = service(tmp_path)
    clip = ws.workspace.clips[0].id
    command = CommandBody(
        operation="suggest",
        request_id="same",
        expected_revision=0,
        payload={"actor": "test-agent", "changes": [{"clip": clip, "label": "A"}]},
    )
    proposal = execute(ws, command)
    assert execute(ws, command) == proposal
    assert not ws.store.labels and not ws.store.batches
    with pytest.raises(ValueError, match="person confirms"):
        execute(
            ws,
            CommandBody(
                operation="label", request_id="no", payload={"clips": [clip], "label": "A"}
            ),
        )
    confirmed = ws.operations.execute(
        "accept", {"suggestion": proposal["id"]}, request_id="confirm", expected_revision=0
    )
    assert confirmed["state"]["revision"] == 1
    assert ws.store.labels == {clip: "A"}
    assert execute(ws, command) == proposal
    with pytest.raises(ConflictError):
        ws.operations.execute("label", {"clips": [clip], "label": "B"}, expected_revision=0)
    with pytest.raises(ConflictError):
        ws.operations.execute("label", {"clips": [clip], "label": "B"}, request_id="same")


def test_a_retried_change_keeps_only_line_ids_and_answers_with_todays_views(tmp_path):
    ws = service(tmp_path)
    first, second = (c.id for c in ws.workspace.clips[:2])
    payload = {"clips": [first], "label": "A"}
    original = ws.operations.execute("label", payload, request_id="once")
    db = connect(ws.store.path)
    try:
        saved = json.loads(db.execute("SELECT result FROM requests WHERE id='once'").fetchone()[0])
    finally:
        db.close()
    assert "state" not in saved and "updated" not in saved
    assert saved["updated_ids"] == [first]
    ws.operations.execute("label", {"clips": [second], "label": "A"})
    again = ws.operations.execute("label", payload, request_id="once")
    assert again["batch"] == original["batch"]
    assert [c["id"] for c in again["updated"]] == [first] and again["ripple"] == 0
    assert again["state"]["revision"] == original["state"]["revision"] + 1
    assert ws.store.labels == {first: "A", second: "A"}


def test_old_databases_drop_the_whole_answers_kept_for_retries(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    connect(path).close()
    db = sqlite3.connect(path, isolation_level=None)
    lines = [{"id": i, "text": "x" * 10_000} for i in ("a", "moved")]
    whole = {"batch": 3, "updated": lines, "ripple": 1, "state": {}}
    job = {"id": "job", "kind": "export", "state": "queued", "result": None, "error": None}
    db.executemany(
        "INSERT INTO requests VALUES (?, ?, ?)",
        [("change", "f", json.dumps(whole)), ("job", "g", json.dumps(job))],
    )
    db.execute("PRAGMA user_version = 1")
    db.close()
    db = connect(path)
    try:
        rows = dict(db.execute("SELECT id, result FROM requests"))
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        db.close()
    assert json.loads(rows["change"]) == {"batch": 3, "ripple": 1, "updated_ids": ["a"]}
    assert json.loads(rows["job"]) == job


def test_pagination_refuses_to_mix_different_revisions(tmp_path):
    ws = service(tmp_path)
    page = query(ws, "clips", limit=2)
    next_page = query(ws, "clips", limit=2, cursor=page["next"])
    assert not {c["id"] for c in page["items"]} & {c["id"] for c in next_page["items"]}
    ws.operations.execute("label", {"clips": [page["items"][0]["id"]], "label": "A"})
    with pytest.raises(ConflictError):
        query(ws, "clips", limit=2, cursor=page["next"])


def test_names_cannot_escape_export_and_unselected_tracks_do_not_block_it(tmp_path):
    from avoc.exporting import ExportClip

    wav = tmp_path / "voice.wav"
    sf.write(wav, np.zeros(48000), 48000)
    clip = ExportClip("a", "ep1", 0, 0.2)
    root = tmp_path / "out"
    written = export({"../outside": [clip]}, {"ep1": wav, "unused": tmp_path / "missing.wav"}, root)
    assert written[0].path.resolve().is_relative_to(root.resolve())


def test_saved_export_can_finish_after_reopening_and_retry_publication(tmp_path):
    ws = service(tmp_path)
    clip = ws.workspace.clips[0]
    wav = Path(ws.workspace.episodes[clip.episode]["vocals"])
    sf.write(wav, np.zeros(12 * 48000), 48000)
    ws.operations.execute("label", {"clips": [clip.id], "label": "A"})
    plan = ws.plan_export(["A"], False, "folder", tmp_path / "out")
    with ws.store.transaction():
        job = ws.jobs.create("export", plan, ws.store._db)
    work(ws.store.path, job["id"])
    reopened = Jobs(ws.store.path)
    assert reopened.get(job["id"])["state"] == "done"
    result = run_export(plan, job["id"])
    assert result["files"] == 1 and "next" in result


def test_export_process_finishes_after_the_service_closes(tmp_path):
    ws = service(tmp_path)
    clip = ws.workspace.clips[0]
    sf.write(Path(ws.workspace.episodes[clip.episode]["vocals"]), np.zeros(12 * 48000), 48000)
    ws.operations.execute("label", {"clips": [clip.id], "label": "A"})
    job = ws.operations.execute(
        "export",
        {"roles": ["A"], "out": str(tmp_path / "out"), "form": "folder"},
        request_id="export",
    )
    ws.close()
    deadline = time.monotonic() + 20
    saved = ws.jobs.get(job["id"])
    while saved["state"] in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.1)
        saved = ws.jobs.get(job["id"])
    assert saved["state"] == "done", saved
    assert saved["result"]["files"] == 1


def test_agent_http_reports_errors_without_confirming_its_suggestions(tmp_path):
    ws = service(tmp_path)
    client = TestClient(create_app(ws))
    capabilities = client.get("/api/agent/capabilities").json()
    assert set(capabilities["operations"]) == {"add", "export", "suggest"}
    clip = client.get("/api/agent/clips", params={"limit": 1}).json()["items"][0]
    denied = client.post(
        "/api/agent/commands",
        json={
            "operation": "label",
            "request_id": "no",
            "payload": {"clips": [clip["id"]], "label": "A"},
        },
    )
    assert denied.status_code == 400 and denied.json()["code"] == "invalid_request"
    accepted = client.post(
        "/api/commands",
        json={
            "operation": "label",
            "request_id": "yes",
            "expected_revision": 0,
            "payload": {"clips": [clip["id"]], "label": "A"},
        },
    )
    assert accepted.status_code == 200
    conflict = client.post(
        "/api/commands",
        json={
            "operation": "label",
            "request_id": "old",
            "expected_revision": 0,
            "payload": {"clips": [clip["id"]], "label": "B"},
        },
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "revision_conflict"
    invalid = client.post(
        "/api/agent/commands",
        json={
            "operation": "suggest",
            "request_id": "bad",
            "payload": {"actor": "agent", "changes": [{"clip": clip["id"], "unusable": "false"}]},
        },
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_request"


def test_parallel_add_calls_only_launch_one_process(tmp_path, monkeypatch):
    job = Adding(tmp_path, lambda _: None)
    entered, release = threading.Event(), threading.Event()
    launches = []
    errors = []

    def check(*args):
        entered.set()
        assert release.wait(5)
        return "ep1"

    def launch(*args):
        launches.append(args[0])
        job.state = "running"
        return job.status()

    monkeypatch.setattr(job, "_check", check)
    monkeypatch.setattr(job, "_remember", lambda *a, **kwargs: None)
    monkeypatch.setattr(job, "_launch", launch)

    def start():
        try:
            job.start(tmp_path, tmp_path)
        except ValueError as exc:
            errors.append(str(exc))

    first, second = threading.Thread(target=start), threading.Thread(target=start)
    first.start()
    assert entered.wait(5)
    second.start()
    checked = threading.Event()
    reader = threading.Thread(target=lambda: (job.status(), checked.set()))
    reader.start()
    try:
        assert checked.wait(1), "Reading status must not wait for episode checks"
    finally:
        release.set()
    first.join(5)
    second.join(5)
    reader.join(5)
    assert launches == ["ep1"] and len(errors) == 1
