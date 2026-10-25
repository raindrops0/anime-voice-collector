"""Human labels in a workspace: an append-only event log, plus a character list.

**Why append-only.** Each action is written as one line that records the state before and after
the change. Old lines are never edited. This way any step can be undone, and the full set of labels
at any moment can be replayed. If the power fails while writing, at most the last line is lost.

One line is one batch of changes (`batch`). Naming a whole group, or confirming the rest in one
click, is one batch, and undo takes back a whole batch at once.
An undo is also a batch. It records which batches it takes back (`undo_of`), and it can itself be
taken back, which puts them back. Any batch still in effect can be taken back, not only the
newest. A line changed again by a later batch keeps the later value. See `revert`.

**Target characters and "other".** The user only names the characters they want (target
characters). Everyone else is labeled "other" (`OTHER`).
"Other" means "not any target character at the time". So each "other" label also records which
target characters existed when it was made (`against`). If a new target character is added later,
old "other" labels do not count against it, and a person must check them again. When a target
character is removed, its labels stay as they are: a clip that belongs to one character is
certainly not any other target character, so it can still be used as a negative example. Adding
the character back loses nothing.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from avoc.language import Words, say
from avoc.project import read_json, write_json

PALETTE = (
    "#7F77DD",
    "#1D9E75",
    "#D85A30",
    "#D4537E",
    "#378ADD",
    "#639922",
    "#BA7517",
    "#E24B4A",
    "#5F5E5A",
    "#534AB7",
    "#0F6E56",
    "#993C1D",
    "#993556",
    "#185FA5",
    "#3B6D11",
    "#854F0B",
)
"""Colors are handed out in turn, in the order characters appear. A color only helps a person
recognize who is who. It means nothing more."""

UNNAMED = Words("角色 {}", "Character {}")
"""Characters the user has not named yet are called this for now. The name is only a key in the
label records, so naming a character is renaming it."""

OTHER = "__other__"
""""Other": not any target character at the time. Clips where several people talk with no target
character, and cheering sound effects are labeled this."""

IGNORED = "__ignored__"
"""Ignored: the person cannot tell who it is, for example a passer-by voiced by a target's voice
actor. Such a clip is set aside: it is not used for training, not exported, and not work to do.
Unlike "other", it does not teach the machine that this voice is not a target."""

SPECIAL = frozenset({OTHER, IGNORED})
"""Labels that are not character names."""

RETIRED = frozenset({"__unclear__", "__multiple__", "__not_speech__"})
"""Retired old labels: unsure, more than one person, or not speech. Since the question became only
"is it a target character?", these are no longer used. On 2026-10-23 they were all cleared, so
people re-listen under the new rules. When an old record is replayed, undone, or an old archive is
imported and these show up, they count as no label."""

FLAGS = ("unusable",)
"""Switches that can be turned on for a labeled target character. They are recorded separately
from the name, and the name still stands for the target.

`unusable` ("low quality"): too much background sound, someone else speaking at the same time, and
so on. Such clips cannot go into the clean dataset. They are not used to recognize people: they
are neither examples of the target nor negative examples, because the target's voice really is in
them. They are skipped on export.
Clips where several people talk and no target character is present are simply labeled "other".
They do not need this switch.
"""

OLD_FLAGS = {"overlap": "unusable"}
"""Switches that were renamed or merged. There used to be a separate "multiple people" switch,
later merged into "low quality". When old records are replayed, they count under the new name."""


def flag_of(change: dict[str, Any]) -> str | None:
    """Which switch this change sets, with old names swapped for new ones. Returns None if the
    change is not a switch change."""
    for key in (*FLAGS, *OLD_FLAGS):
        if key in change:
            return OLD_FLAGS.get(key, key)
    return None


def current(name: str | None) -> str | None:
    """Strip leading and trailing spaces. An empty label and a retired old label both count as no
    label."""
    name = (name or "").strip()
    return None if not name or name in RETIRED else name


def undone_by(batch: dict[str, Any]) -> list[int]:
    """The batches this batch takes back; empty for an ordinary batch. Older records hold a single
    number."""
    value = batch.get("undo_of")
    if value is None:
        return []
    return [value] if isinstance(value, int) else list(value)


def cast_steps(batch: dict[str, Any]) -> list[dict[str, Any]]:
    """The changes a batch made to the character list, in the order they were made. An ordinary
    batch has at most one step. A batch that takes back others lists its steps under `steps`, since
    it may rename or merge several characters."""
    cast = batch.get("cast") or {}
    rest = {k: v for k, v in cast.items() if k != "steps"}
    return [*cast.get("steps", ()), *([rest] if rest else [])]


class LabelStore:
    """Reads and writes one workspace's labels and character list. Every change goes through
    `apply`. It is thread-safe."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.events_path = folder / "events.jsonl"
        self.cast_path = folder / "cast.json"
        self.labels: dict[str, str] = {}
        self.against: dict[str, set[str]] = {}
        """Clips labeled "other", and which target characters existed when they were labeled."""
        self.rejects: dict[str, set[str]] = {}
        self.flags: dict[str, set[str]] = {flag: set() for flag in FLAGS}
        """Clips where each switch is on. See `FLAGS`."""
        self.unusable = self.flags["unusable"]
        self.batches: list[dict[str, Any]] = []
        self.roles: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        folder.mkdir(parents=True, exist_ok=True)
        if self.cast_path.exists():
            self.roles = list(read_json(self.cast_path)["roles"])
        # Early character lists did not have these fields. Back then every name was typed by a
        # person, so each one must be checked. Pattern numbers are filled in list order.
        for index, role in enumerate(self.roles):
            role.setdefault("named", True)
            role.setdefault("pattern", index)
            role.setdefault("target", True)
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    batch = json.loads(line)
                    self._replay(batch)
                    self.batches.append(batch)
        # The character list is the source of truth in cast.json. When replaying history, do not
        # create characters, or old names that were later renamed would come back.
        # Only names that still have clips but are missing from the list get added.
        missing = {n for n in self.labels.values() if n not in SPECIAL and not self.role(n)}
        for name in sorted(missing):
            self._ensure_role(name, save=False)
        if missing:
            self._save_cast()

    # Reading

    def role(self, name: str) -> dict[str, Any] | None:
        return next((r for r in self.roles if r["name"] == name), None)

    def targets(self) -> list[str]:
        """The current target characters, in the order of the character list."""
        return [r["name"] for r in self.roles if r.get("target")]

    def can_undo(self) -> bool:
        return self.undo_target() is not None

    def undo_target(self) -> int | None:
        """What Z takes back: the newest batch still in effect, leaving out the undos Z itself
        wrote, so pressing Z again goes further back instead of putting the last one back."""
        with self._lock:
            undone = self.undone()
            floor = self.floor()
            for batch in reversed(self.batches):
                if batch["batch"] <= floor:
                    return None
                if batch["source"] != "undo" and batch["batch"] not in undone:
                    return batch["batch"]
            return None

    def undone(self) -> set[int]:
        """Batches whose effect is taken back now. A batch is taken back by a later batch that is
        itself still in effect, so taking back an undo puts the batches it undid back."""
        undoers: dict[int, list[int]] = {}
        for batch in self.batches:
            for target in undone_by(batch):
                undoers.setdefault(target, []).append(batch["batch"])
        out: set[int] = set()
        for batch in reversed(self.batches):
            if any(u not in out for u in undoers.get(batch["batch"], ())):
                out.add(batch["batch"])
        return out

    def floor(self) -> int:
        """The last imported batch. It and every batch before it cannot be taken back: an import
        sets many labels at once from elsewhere."""
        imports = (b["batch"] for b in self.batches if b["source"].startswith("import"))
        return max(imports, default=0)

    def history(self, limit: int = 50, before: int | None = None) -> list[dict[str, Any]]:
        """The newest batches first, each with a short account of what it did, and whether it can
        be taken back now. `before` continues a list from that batch on."""
        with self._lock:
            undone = self.undone()
            floor = self.floor()
            by_id = {b["batch"]: b for b in self.batches}
            undoers: dict[int, list[int]] = {}
            for batch in self.batches:
                for target in undone_by(batch):
                    undoers.setdefault(target, []).append(batch["batch"])
            out = []
            for batch in reversed(self.batches):
                if before is not None and batch["batch"] >= before:
                    continue
                if len(out) >= limit:
                    break
                by = [u for u in undoers.get(batch["batch"], ()) if u not in undone]
                out.append(
                    {
                        **_account(batch),
                        "undone_by": max(by) if by else None,
                        "why_not": self._why_not(batch, undone, floor, by_id),
                    }
                )
            return out

    # Writing

    def apply(
        self,
        changes: list[dict[str, Any]],
        source: str = "human",
        undo_of: int | list[int] | None = None,
        cast: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Write one batch of changes. Each change is `{"clip", "label"}` (an empty `label` clears
        the label), `{"clip", "reject", "on"}` (this clip is not a certain character), or
        `{"clip", flag name: on or off}` (see `FLAGS`). Changes that do not actually change
        anything are dropped.

        When a clip is labeled "other", the current target characters are recorded. If the change
        includes `against`, that list is used instead (undo and migration do this).
        Characters this batch creates are recorded in the batch's `cast.created`. Renames and
        merges given in `cast` are recorded too. On undo, the character list is changed back. See
        `_undo_cast`."""
        with self._lock:
            targets = self.targets()
            effective: list[dict[str, Any]] = []
            created: list[str] = []
            for change in changes:
                clip = change["clip"]
                if "reject" in change:
                    before = change["reject"] in self.rejects.get(clip, set())
                    if before != bool(change["on"]):
                        effective.append(
                            {"clip": clip, "reject": change["reject"], "before": before,
                             "after": bool(change["on"])}
                        )  # fmt: skip
                    continue
                flag = flag_of(change)
                if flag is not None:
                    before = clip in self.flags[flag]
                    on = next(v for k, v in change.items() if OLD_FLAGS.get(k, k) == flag)
                    if before != bool(on):
                        effective.append(
                            {
                                "clip": clip,
                                flag: True,
                                "before": before,
                                "after": bool(on),
                            }
                        )
                    continue
                label = current(change.get("label"))
                previous = self.labels.get(clip)
                old = sorted(self.against.get(clip, ())) if previous == OTHER else None
                new = sorted(change.get("against", targets)) if label == OTHER else None
                if previous != label or old != new:
                    entry: dict[str, Any] = {"clip": clip, "before": previous, "after": label}
                    if old is not None:
                        entry["before_against"] = old
                    if new is not None:
                        entry["against"] = new
                    effective.append(entry)
                    if label is not None and label not in SPECIAL:
                        if self.role(label) is None:
                            created.append(label)
                        self._ensure_role(label)
            # An undo is recorded even when nothing actually changes (for example, when it takes
            # back the batch that cleared retired old labels). Otherwise that batch would look
            # never undone, and repeated undo would get stuck on it. A rename or merge is recorded
            # too, even for a character with no clips.
            if not effective and undo_of is None and not cast:
                return None
            batch: dict[str, Any] = {
                "batch": (self.batches[-1]["batch"] + 1) if self.batches else 1,
                "time": datetime.now(UTC).isoformat(timespec="seconds"),
                "source": source,
                "undo_of": undo_of,
                "changes": effective,
            }
            if created or cast:
                batch["cast"] = {**(cast or {}), **({"created": created} if created else {})}
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(batch, ensure_ascii=False) + "\n")
            self._replay(batch)
            self.batches.append(batch)
            return batch

    def undo(self) -> dict[str, Any] | None:
        """Take back what Z takes back (see `undo_target`)."""
        with self._lock:
            target = self.undo_target()
            return None if target is None else self.revert([target], source="undo")[0]

    def revert(
        self, ids: list[int], source: str = "revert"
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Take back the given batches, newest first, written as one new batch. Returns that batch
        (None when nothing could be taken back) and a report.

        A line that a later batch still in effect changed again keeps the later value; the report
        counts these as `kept`. Renames and merges are taken back for the whole character, so lines
        labeled with the new name later go back with it. A batch is left out whole when a name it
        needs back is now taken, or a character it needs is gone; the report lists these under
        `skipped`. Characters a batch made are removed once no line is left with them."""
        with self._lock:
            by_id = {b["batch"]: b for b in self.batches}
            undone = self.undone()
            floor = self.floor()
            wanted = sorted(set(ids), reverse=True)
            if not wanted:
                raise ValueError(say("没有选中要撤销的操作", "no step chosen to take back"))
            for number in wanted:
                if number not in by_id:
                    raise ValueError(say(f"没有第 {number} 步", f"no step {number}"))
                if why := self._why_not(by_id[number], undone, floor, by_id):
                    raise ValueError(say(f"第 {number} 步：", f"step {number}: ") + why)
            pending = _Pending(self)
            steps: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            done: list[int] = []
            kept = 0
            for number in wanted:
                batch = by_id[number]
                own = cast_steps(batch)
                if (clash := self._clash(own)) is not None:
                    skipped.append({"batch": number, "name": clash})
                    continue
                done.append(number)
                for step in reversed(own):
                    steps += self._take_back_roles(step, pending)
                for change in batch["changes"]:
                    kept += not pending.take_back(change)
                for step in reversed(own):
                    steps += self._drop_unused(step, pending)
            report = {"skipped": skipped, "kept": kept}
            if not done:
                return None, report
            undo_of: int | list[int] = done[0] if len(done) == 1 else done
            # `steps` is written even when empty: it tells this batch from undos of older versions,
            # which did not record the characters they changed back.
            new = self.apply(
                pending.changes(), source=source, undo_of=undo_of, cast={"steps": steps}
            )
            return new, report

    def update_role(self, name: str, **fields: Any) -> dict[str, Any]:
        """Change the color, the avatar, or whether this is a target character. To rename, use
        `rename_role`.

        Adding or removing target characters does not change any label. See the module notes."""
        with self._lock:
            role = self.role(name)
            if role is None:
                raise ValueError(say(f"没有这个角色：{name}", f"no such character: {name}"))
            for key in ("color", "avatar", "target"):
                if key in fields and fields[key] is not None:
                    role[key] = fields[key]
            self._save_cast()
            return role

    def new_role(self) -> str:
        """Make a character that has no name yet, and return its temporary name. Labels for it must
        be written next with `apply`, and `cast` must include `{"unnamed": [name]}`. Only then does
        undoing that batch remove this character too."""
        with self._lock:
            number = 1
            while self.role(str(UNNAMED).format(number)) is not None:
                number += 1
            name = str(UNNAMED).format(number)
            self._ensure_role(name, named=False)
            return name

    def rename_role(self, old: str, new: str) -> dict[str, Any] | None:
        """Rename, which is also how a name is given. If the new name already exists, this merges
        the two characters, so their clips are joined together."""
        new = new.strip()
        with self._lock:
            if self.role(old) is None:
                raise ValueError(say(f"没有这个角色：{old}", f"no such character: {old}"))
            if current(new) is None or new in SPECIAL:
                raise ValueError(
                    say(
                        "新名字不能为空，也不能是「不是目标」",
                        'the new name cannot be empty or "Not a target"',
                    )
                )
            if new == old:
                return None
            moved: list[dict[str, Any]] = [
                {"clip": c, "label": new} for c, n in self.labels.items() if n == old
            ]
            cast: dict[str, Any]
            if self.role(new) is None:
                role = self.role(old)
                assert role is not None
                cast = {"renamed": {"from": old, "to": new, "named": role["named"]}}
                role["name"] = new
                role["named"] = True
            else:
                merged = self.role(old)
                kept = self.role(new)
                assert merged is not None and kept is not None
                cast = {
                    "merged": {
                        "role": dict(merged),
                        "at": self.roles.index(merged),
                        "into": new,
                        "target": bool(kept.get("target")),
                    }
                }
                kept["target"] = bool(kept.get("target")) or bool(merged.get("target"))
                self.roles = [r for r in self.roles if r["name"] != old]
            self._save_cast()
            for clip, names in self.rejects.items():
                if old in names:
                    moved.append({"clip": clip, "reject": old, "on": False})
                    moved.append({"clip": clip, "reject": new, "on": True})
            for clip, names in self.against.items():
                if old in names and self.labels.get(clip) == OTHER:
                    renamed = (names - {old}) | {new}
                    moved.append({"clip": clip, "label": OTHER, "against": sorted(renamed)})
            # Recorded even when no clip moves, so the rename can still be undone.
            return self.apply(moved, cast=cast)

    # Internal

    def _why_not(
        self,
        batch: dict[str, Any],
        undone: set[int],
        floor: int,
        by_id: dict[int, dict[str, Any]],
    ) -> str | None:
        """Why this batch cannot be taken back, or None when it can. Whether the names it needs
        are free is only known when taking it back; see `_clash`."""
        if batch["batch"] <= floor:
            return say(
                "导入的标签，以及导入之前的操作，不能撤销",
                "imported labels, and the steps before them, cannot be taken back",
            )
        if batch["batch"] in undone:
            return say("已经撤销了", "already taken back")
        targets = [by_id[t] for t in undone_by(batch) if t in by_id]
        if "cast" not in batch and any(cast_steps(t) for t in targets):
            return say(
                "这是旧版本的撤销，没有记下它改回的角色",
                "an undo from an older version, which did not record the characters it put back",
            )
        return None

    def _clash(self, steps: list[dict[str, Any]]) -> str | None:
        """The first character name that keeps these character-list steps from being taken back:
        a name to give back that is taken now, or a character that is gone. None when all can be."""
        names = {r["name"] for r in self.roles}
        for step in reversed(steps):
            if renamed := step.get("renamed"):
                if renamed["from"] in names or renamed["to"] not in names:
                    return renamed["from"] if renamed["from"] in names else renamed["to"]
                names = (names - {renamed["to"]}) | {renamed["from"]}
            if merged := step.get("merged"):
                name = merged["role"]["name"]
                if name in names or merged["into"] not in names:
                    return name if name in names else merged["into"]
                names.add(name)
            if split := step.get("split"):
                for name in (split["role"], split["into"]):
                    if name not in names:
                        return name
                names.discard(split["role"])
            for entry in step.get("deleted", ()):
                if entry["role"]["name"] in names:
                    return entry["role"]["name"]
                names.add(entry["role"]["name"])
        return None

    def _take_back_roles(self, step: dict[str, Any], pending: _Pending) -> list[dict[str, Any]]:
        """Take back one step's renames, merges and removals of characters, before its lines go
        back. Returns the steps that would undo this, to be recorded with the new batch."""
        out: list[dict[str, Any]] = []
        if renamed := step.get("renamed"):
            role = self.role(renamed["to"])
            assert role is not None
            out.append({"renamed": {"from": renamed["to"], "to": renamed["from"],
                                    "named": role["named"]}})  # fmt: skip
            role["name"] = renamed["from"]
            role["named"] = renamed["named"]
            pending.move_all(renamed["to"], renamed["from"])
        if merged := step.get("merged"):
            kept = self.role(merged["into"])
            assert kept is not None
            out.append({"split": {"role": merged["role"]["name"], "into": merged["into"],
                                  "target": bool(kept.get("target"))}})  # fmt: skip
            kept["target"] = merged["target"]
            self.roles.insert(min(merged["at"], len(self.roles)), dict(merged["role"]))
        if split := step.get("split"):
            # Taking back the undo of a merge merges again, all of the character's lines.
            role = self.role(split["role"])
            kept = self.role(split["into"])
            assert role is not None and kept is not None
            at = self.roles.index(role)
            out.append({"merged": {"role": dict(role), "at": at, "into": split["into"],
                                   "target": bool(kept.get("target"))}})  # fmt: skip
            kept["target"] = split["target"]
            self.roles.remove(role)
            pending.move_all(split["role"], split["into"])
        if deleted := step.get("deleted"):
            for entry in reversed(deleted):
                self.roles.insert(min(entry["at"], len(self.roles)), dict(entry["role"]))
            out.append({"created": [entry["role"]["name"] for entry in deleted]})
        if out:
            self._save_cast()
        return out

    def _drop_unused(self, step: dict[str, Any], pending: _Pending) -> list[dict[str, Any]]:
        """After a step's lines went back: remove the characters it made that no line has now.
        For example, making a new character with N and then pressing Z leaves no empty character
        behind."""
        made = [*step.get("created", ()), *step.get("unnamed", ())]
        used = pending.names_in_use()
        gone = []
        for name in made:
            role = self.role(name)
            if role is not None and name not in used:
                gone.append({"role": dict(role), "at": self.roles.index(role)})
                self.roles.remove(role)
        if not gone:
            return []
        self._save_cast()
        return [{"deleted": gone}]

    def _replay(self, batch: dict[str, Any]) -> None:
        for change in batch["changes"]:
            clip = change["clip"]
            if "reject" in change:
                names = self.rejects.setdefault(clip, set())
                if change["after"]:
                    names.add(change["reject"])
                else:
                    names.discard(change["reject"])
            elif (flag := flag_of(change)) is not None:
                flagged = self.flags[flag]
                if change["after"]:
                    flagged.add(clip)
                else:
                    flagged.discard(clip)
            else:
                self.against.pop(clip, None)
                after = current(change["after"])
                if after is None:
                    self.labels.pop(clip, None)
                else:
                    self.labels[clip] = after
                    if after == OTHER:
                        self.against[clip] = set(change.get("against", ()))

    def _ensure_role(self, name: str, save: bool = True, named: bool = True) -> None:
        """A new character is a target character by default. A person who bothers to name someone
        probably wants that person."""
        if self.role(name) is None:
            # Pattern numbers only go up and are never reused. A character that was deleted or
            # merged does not pass its pattern on to a new character.
            pattern = max((int(r["pattern"]) for r in self.roles), default=-1) + 1
            self.roles.append(
                {
                    "name": name,
                    "named": named,
                    "color": PALETTE[pattern % len(PALETTE)],
                    "pattern": pattern,
                    "target": True,
                    "avatar": None,
                }
            )
            if save:
                self._save_cast()

    def _save_cast(self) -> None:
        write_json(self.cast_path, {"schema": "cast.v1", "roles": self.roles})


class _Pending:
    """The labels while working out a take-back: the store's labels with the planned changes on
    top. Nothing is written until `LabelStore.apply` gets `changes()`."""

    def __init__(self, store: LabelStore) -> None:
        self.store = store
        self.labels: dict[str, tuple[str | None, frozenset[str] | None]] = {}
        self.rejects: dict[tuple[str, str], bool] = {}
        self.flags: dict[tuple[str, str], bool] = {}

    def label(self, clip: str) -> tuple[str | None, frozenset[str] | None]:
        """The clip's label, and for "other" the targets it was judged against."""
        if clip in self.labels:
            return self.labels[clip]
        name = self.store.labels.get(clip)
        return name, frozenset(self.store.against.get(clip, ())) if name == OTHER else None

    def rejected(self, clip: str, name: str) -> bool:
        return self.rejects.get((clip, name), name in self.store.rejects.get(clip, set()))

    def names_in_use(self) -> set[str | None]:
        return {self.label(clip)[0] for clip in {*self.store.labels, *self.labels}}

    def move_all(self, old: str, new: str) -> None:
        """Everything said about one character now goes to another, as renaming does."""
        for clip in {*self.store.labels, *self.labels}:
            name, against = self.label(clip)
            if name == old:
                self.labels[clip] = (new, None)
            elif name == OTHER and against is not None and old in against:
                self.labels[clip] = (OTHER, (against - {old}) | {new})
        for clip in {*self.store.rejects, *(c for c, _ in self.rejects)}:
            if self.rejected(clip, old):
                self.rejects[(clip, old)] = False
                self.rejects[(clip, new)] = True

    def take_back(self, change: dict[str, Any]) -> bool:
        """Put one recorded change back. False when the line was changed again since and keeps
        that later value, or when the character it would go back to is gone."""
        clip = change["clip"]
        # A switch has only two values: it is either back already or as this change left it.
        if "reject" in change:
            self.rejects[(clip, change["reject"])] = change["before"]
            return True
        if (flag := flag_of(change)) is not None:
            self.flags[(flag, clip)] = change["before"]
            return True
        before, after = current(change["before"]), current(change["after"])
        before_against = frozenset(change.get("before_against", ())) if before == OTHER else None
        after_against = frozenset(change.get("against", ())) if after == OTHER else None
        name, against = self.label(clip)
        if before != after:
            if name == before:
                return True
            if name != after:
                return False
        elif before == OTHER:
            # Only the targets "other" was judged against changed.
            if against == before_against:
                return True
            if name != OTHER or against != after_against:
                return False
        else:
            return True
        if before is not None and before not in SPECIAL and self.store.role(before) is None:
            return False
        self.labels[clip] = (before, before_against)
        return True

    def changes(self) -> list[dict[str, Any]]:
        """The planned changes in the form `LabelStore.apply` takes. It drops the ones that end
        where they started."""
        out: list[dict[str, Any]] = []
        for clip, (name, against) in self.labels.items():
            change: dict[str, Any] = {"clip": clip, "label": name}
            if name == OTHER:
                change["against"] = sorted(against or ())
            out.append(change)
        out += [{"clip": c, "reject": n, "on": on} for (c, n), on in self.rejects.items()]
        out += [{"clip": c, flag: on} for (flag, c), on in self.flags.items()]
        return out


def _account(batch: dict[str, Any]) -> dict[str, Any]:
    """A short account of one batch for the history list: how many lines it labeled and as whom,
    how many it marked or unmarked as low quality, and what it did to the character list."""
    lines: list[str] = []
    to: Counter[str | None] = Counter()
    low = Counter[bool]()
    rejects = 0
    for change in batch["changes"]:
        if "reject" in change:
            rejects += 1
        elif flag_of(change) is not None:
            low[bool(change["after"])] += 1
        else:
            if change["clip"] not in lines:
                lines.append(change["clip"])
            if current(change["before"]) != current(change["after"]):
                to[current(change["after"])] += 1
    renamed = merged = None
    created: list[str] = []
    for step in cast_steps(batch):
        if r := step.get("renamed"):
            renamed = {"from": r["from"], "to": r["to"]}
        if m := step.get("merged"):
            merged = {"from": m["role"]["name"], "into": m["into"]}
        created += [*step.get("created", ()), *step.get("unnamed", ())]
    return {
        "batch": batch["batch"],
        "time": batch["time"],
        "source": batch["source"],
        "undo_of": undone_by(batch),
        "lines": len(lines),
        "first": lines[0] if lines else None,
        "to": [{"name": name, "count": count} for name, count in to.most_common()],
        "low": low[True],
        "not_low": low[False],
        "rejects": rejects,
        "renamed": renamed,
        "merged": merged,
        "created": created,
    }
