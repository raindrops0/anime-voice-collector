from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from avoc.app.demo import DemoHub, pack
from avoc.app.server import AppState, create_app
from tests.fixtures import episode

MODEL = ("redimnet2-b6",)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "episodes").mkdir(parents=True)
    episode(root / "episodes", "ep1", np.eye(6)[:, :3] + 0.1)
    return root


def test_the_demo_turns_off_work_on_the_servers_disk(tmp_path: Path) -> None:
    state = AppState(_workspace(tmp_path), MODEL, grouping=MODEL[0])
    state.demo = True
    client = TestClient(create_app(state))
    assert client.get("/api/state").json()["demo"] is True
    body = {"roles": ["A"], "out": str(tmp_path / "out")}
    assert client.post("/api/export", json=body).status_code == 403
    assert client.post("/api/pick", json={"kind": "video"}).status_code == 403
    assert client.post("/api/add/queue", json={"episodes": []}).status_code == 403
    assert client.get("/api/doctor").status_code == 403
    command = {"operation": "export", "payload": body, "request_id": "r1"}
    assert client.post("/api/commands", json=command).status_code == 400
    assert client.post("/api/agent/commands", json=command).status_code == 400
    assert not (tmp_path / "out").exists()
    # Labeling still works, and the add form's status can still be read.
    ids = [c.id for c in state.workspace.clips]
    assert client.post("/api/label", json={"clips": ids[:2], "label": "A"}).status_code == 200
    assert client.get("/api/add").status_code == 200


def test_each_visitor_labels_their_own_copy(tmp_path: Path) -> None:
    template = tmp_path / "template"
    pack(_workspace(tmp_path), template)
    meta = json.loads((template / "episodes/ep1/episode.json").read_text("utf-8"))
    assert meta["vocals"] == "ep1.wav"  # relative, so the template can move

    hub = DemoHub(template, models=MODEL, prepare=False)
    with TestClient(hub) as first, TestClient(hub) as second:
        assert first.get("/").status_code == 200
        state = first.get("/api/state").json()
        assert state["demo"] is True
        clips = first.get("/api/clips").json()
        first.post("/api/label", json={"clips": [clips[0]["id"]], "label": "A"})
        assert second.get("/").status_code == 200
        assert [r["name"] for r in second.get("/api/state").json()["roles"]] == []
        assert [r["name"] for r in first.get("/api/state").json()["roles"]] == ["A"]
        (copy,) = [v.root for v in hub.visits.values() if v.state.store.labels]
        vocals = json.loads((copy / "episodes/ep1/episode.json").read_text("utf-8"))["vocals"]
        assert Path(vocals).is_absolute() and Path(vocals).is_file()

    # A tab whose copy is gone is told to reload, rather than starting over unnoticed.
    stale = TestClient(DemoHub(template, models=MODEL, prepare=False))
    stale.cookies.set("avoc_demo", "gone")
    gone = stale.get("/api/state")
    assert gone.status_code == 410
    assert gone.headers["cache-control"] == "no-store"  # or the browser keeps answering 410
    assert stale.get("/favicon.ico").status_code == 200


def test_a_spare_copy_waits_for_the_next_visitor(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "template"
    pack(_workspace(tmp_path), template)
    monkeypatch.setattr("avoc.quality.starter_path", lambda: None)
    hub = DemoHub(template, models=MODEL, prepare=False)
    hub._prepare()
    assert hub.spare is not None
    spare_key, _ = hub.spare
    assert [p.name for p in hub.folder.iterdir()] == [spare_key]  # the warm-up copy is gone
    client = TestClient(hub)
    assert client.get("/").status_code == 200
    assert list(hub.visits) == [spare_key]
    assert client.get("/api/state").json()["roles"] == []


def test_the_oldest_copies_make_room(tmp_path: Path) -> None:
    template = tmp_path / "template"
    pack(_workspace(tmp_path), template)
    hub = DemoHub(template, limit=2, models=MODEL, prepare=False)
    clients = [TestClient(hub) for _ in range(3)]
    for client in clients:
        client.get("/")
    assert len(hub.visits) == 2
    assert clients[0].get("/api/state").status_code == 410
    assert clients[2].get("/api/state").status_code == 200
