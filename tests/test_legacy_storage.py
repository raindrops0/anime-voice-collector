"""Older servers could append different records with the same operation number."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from avoc.labels import LabelStore
from avoc.storage import legacy_batches


def label(clip: str, before: str | None, after: str | None) -> dict:
    return {"clip": clip, "before": before, "after": after}


def record(number: int, changes: list[dict], undo: int | list[int] | None = None) -> dict:
    return {
        "batch": number,
        "source": "human" if undo is None else "undo",
        "time": "t",
        "changes": changes,
        "undo_of": undo,
    }


def write(folder: Path, records: list[dict]) -> tuple[Path, bytes]:
    path = folder / "events.jsonl"
    raw = "".join(json.dumps(b) + "\n" for b in records).encode()
    path.write_bytes(raw)
    return path, raw


def test_reused_numbers_keep_every_record_and_find_an_older_undo_target(tmp_path):
    records = [
        record(1, [label("a", None, "A")]),
        record(2, [label("b", None, "B")]),
        record(1, [label("c", None, "C")]),
        record(3, [label("d", None, "D")]),
        record(2, [label("a", "A", None)], undo=1),
        record(3, [label("e", None, "E")]),
        record(4, [label("c", "C", None), label("e", "E", None)], undo=[1, 3]),
        record(5, [label("c", None, "C"), label("e", None, "E")], undo=4),
    ]
    path, raw = write(tmp_path, records)
    with pytest.warns(RuntimeWarning, match="importing all records in file order"):
        store = LabelStore(tmp_path)
    assert path.read_bytes() == raw
    assert len(store.batches) == len(records)
    assert [b["batch"] for b in store.batches] == list(range(1, 9))
    assert store.batches[4]["undo_of"] == 1
    assert store.batches[6]["undo_of"] == [3, 6]
    assert store.batches[7]["undo_of"] == 7
    assert [b["legacy"]["batch"] for b in store.batches] == [b["batch"] for b in records]
    assert store.labels == {"b": "B", "c": "C", "d": "D", "e": "E"}
    assert store.undone() == {1, 7}
    assert store.floor() == 0
    store.apply([{"clip": "f", "label": "F"}])
    assert store.batches[-1]["batch"] == 9
    store.undo()
    assert "f" not in store.labels
    reopened = LabelStore(tmp_path)
    assert reopened.labels == store.labels and reopened.batches == store.batches


def test_out_of_order_unique_numbers_follow_file_order_and_keep_undo_links(tmp_path):
    path, raw = write(
        tmp_path,
        [
            record(10, [label("a", None, "A")]),
            record(30, [label("b", None, "B")]),
            record(20, [label("b", "B", None)], undo=30),
        ],
    )
    with pytest.warns(RuntimeWarning, match="new numbers"):
        store = LabelStore(tmp_path)
    assert path.read_bytes() == raw
    assert [b["batch"] for b in store.batches] == [1, 2, 3]
    assert store.batches[-1]["undo_of"] == 2
    assert store.labels == {"a": "A"}
    assert store.undo_target() == 1


@pytest.mark.parametrize(
    "undo_changes", [[], [label("a", "A", None)], [label("elsewhere", "B", None)]]
)
def test_uncertain_undo_preserves_labels_and_freezes_only_the_older_history(tmp_path, undo_changes):
    path, raw = write(
        tmp_path,
        [
            record(1, [label("a", None, "A")]),
            record(1, [label("a", None, "A")]),
            record(2, undo_changes, undo=1),
        ],
    )
    with pytest.warns(RuntimeWarning) as warnings:
        store = LabelStore(tmp_path)
    assert len(warnings) == 2
    assert path.read_bytes() == raw
    assert store.floor() == 3 and not store.can_undo()
    assert store.labels == ({} if undo_changes == [label("a", "A", None)] else {"a": "A"})
    assert "no clear target" in store.history()[0]["why_not"]
    store.apply([{"clip": "new", "label": "B"}])
    store.undo()
    assert "new" not in store.labels
    assert not store.can_undo()


@pytest.mark.parametrize("field", ["unusable", "overlap", "reject"])
def test_undo_matches_separate_clip_fields(tmp_path, field):
    extra = {"reject": "A"} if field == "reject" else {field: True}
    records = [
        record(1, [{"clip": "a", **extra, "before": False, "after": True}]),
        record(1, [{"clip": "b", **extra, "before": False, "after": True}]),
        record(2, [{"clip": "a", **extra, "before": True, "after": False}], undo=1),
    ]
    path, _ = write(tmp_path, records)
    with pytest.warns(RuntimeWarning):
        batches = legacy_batches(path)
    assert batches[-1]["undo_of"] == 1
    assert batches[-1]["legacy"]["undo_of"] == 1


def test_valid_numbers_with_gaps_do_not_change(tmp_path):
    records = [record(2, [label("a", None, "A")]), record(8, [label("a", "A", None)], undo=2)]
    path, raw = write(tmp_path, records)
    assert legacy_batches(path) == records
    assert path.read_bytes() == raw
