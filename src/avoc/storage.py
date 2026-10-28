"""Save related workspace changes together and import older label files once."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import warnings
from pathlib import Path
from typing import Any

VERSION = 2
"""1 kept each change's whole answer for retries; 2 keeps only the IDs of the lines it changed."""


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > VERSION:
        db.close()
        raise ValueError("This workspace database was made by a newer program")
    db.execute("PRAGMA synchronous = FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS state (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            revision INTEGER NOT NULL,
            roles TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS batches (number INTEGER PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS suggestions (
            id TEXT PRIMARY KEY, actor TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
            body TEXT NOT NULL, result TEXT, error TEXT, pid INTEGER
        );
    """)
    if version < 2:
        _shrink_requests(db)
    db.execute(f"PRAGMA user_version = {VERSION}")
    return db


def retry_form(result: dict[str, Any]) -> dict[str, Any]:
    """What is kept for a retry. A change's answer holds every changed line and the whole overview,
    about 2 MB on a large workspace, so only the IDs of the lines it changed itself are kept (not
    the lines whose guesses moved, often thousands) and the rest is read again."""
    if "updated" not in result:
        return result
    rest = {k: v for k, v in result.items() if k not in ("state", "updated")}
    own = result["updated"][: len(result["updated"]) - result.get("ripple", 0)]
    return {**rest, "updated_ids": [c["id"] for c in own]}


def _shrink_requests(db: sqlite3.Connection) -> None:
    """Version 1 kept every change's whole answer; keep the short form and give the space back."""
    rows = db.execute("SELECT id, result FROM requests").fetchall()
    if not rows:
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany(
            "UPDATE requests SET result = ? WHERE id = ?",
            [(json.dumps(retry_form(json.loads(result))), i) for i, result in rows],
        )
        db.execute(f"PRAGMA user_version = {VERSION}")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    # Another program may hold the database open; then the freed space is only reused, not
    # given back, which is fine.
    with contextlib.suppress(sqlite3.OperationalError):
        db.execute("VACUUM")


def legacy_batches(path: Path) -> list[dict[str, Any]]:
    """Only an unfinished last line can be recovered; keep the original file untouched."""
    if not path.exists():
        return []
    lines = path.read_bytes().splitlines(keepends=True)
    batches = []
    positions = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            batches.append(json.loads(line))
            positions.append(index + 1)
        except (ValueError, UnicodeDecodeError) as exc:
            if index != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError(f"Cannot read label record {index + 1} in {path}") from exc
            warnings.warn(
                f"Unfinished last label record was left out. The original is kept at {path}",
                RuntimeWarning,
                stacklevel=2,
            )
    numbers = [b["batch"] for b in batches]
    if any(type(number) is not int or number < 1 for number in numbers):
        raise ValueError(f"Label record numbers must be positive whole numbers in {path}")
    if numbers != sorted(set(numbers)):
        return _number_in_file_order(batches, positions, path)
    return batches


def _change_values(change: dict[str, Any], *, reverse: bool = False) -> str:
    """Compare the recorded values of an undo with an earlier change in either direction."""
    if "reject" in change:
        field = ("reject", change["reject"])
    elif "unusable" in change or "overlap" in change:
        field = ("unusable",)
    else:
        field = ("label",)
    before, after = change["before"], change["after"]
    before_against = sorted(change.get("before_against", ())) if before == "__other__" else None
    after_against = sorted(change.get("against", ())) if after == "__other__" else None
    if reverse:
        before, after = after, before
        before_against, after_against = after_against, before_against
    return json.dumps([change["clip"], field, before, after, before_against, after_against])


def _number_in_file_order(
    batches: list[dict[str, Any]], positions: list[int], path: Path
) -> list[dict[str, Any]]:
    """Keep every old write and resolve reused undo numbers only when their values identify it."""
    previous: dict[int, list[dict[str, Any]]] = {}
    repaired = []
    blocked = 0
    for number, (batch, line) in enumerate(zip(batches, positions, strict=True), 1):
        old = batch["batch"]
        original = batch.get("undo_of")
        targets = [original] if isinstance(original, int) else original or []
        undo_values = {_change_values(c) for c in batch["changes"]}
        resolved = []
        missing = []
        for target in targets:
            candidates = previous.get(target, [])
            if len(candidates) > 1:
                candidates = [
                    b
                    for b in candidates
                    if any(_change_values(c, reverse=True) in undo_values for c in b["changes"])
                ]
            if len(candidates) == 1:
                resolved.append(candidates[0]["batch"])
            else:
                missing.append(target)
        entry = {
            **batch,
            "batch": number,
            "legacy": {"batch": old, "undo_of": original, "line": line},
        }
        if isinstance(original, int):
            entry["undo_of"] = resolved[0] if resolved else None
        elif original is not None:
            entry["undo_of"] = resolved
        if missing:
            entry["legacy"]["unresolved_undo"] = missing
            blocked = number
        repaired.append(entry)
        previous.setdefault(old, []).append(entry)
    warnings.warn(
        "Label record numbers repeat or go backwards; importing all records in file order "
        f"with new numbers. The original is kept at {path}",
        RuntimeWarning,
        stacklevel=2,
    )
    if blocked:
        warnings.warn(
            f"Some old undo links cannot be identified. History through step {blocked} cannot "
            "be undone; labels are preserved and new changes can still be undone.",
            RuntimeWarning,
            stacklevel=2,
        )
    return repaired
