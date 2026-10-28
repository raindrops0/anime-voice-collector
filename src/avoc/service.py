"""Workspace operations shared by the web app, command line and agent tools."""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from avoc import quality
from avoc.adding import Adding
from avoc.labels import IGNORED, OTHER, LabelStore
from avoc.language import Words, say
from avoc.model import (
    AUTO_CONFIDENCE,
    MIN_GUESS_LABELS,
    Guess,
    Weights,
    guessed_targets,
    train_and_predict,
)
from avoc.project import free_export_folder as free_export_folder
from avoc.project import read_json, resolve_device, write_json
from avoc.video import (
    PICTURE_PAD,
    copy_ready,
)
from avoc.workspace import DEFAULT_MODELS, GROUPING_MODEL, Clip, load_workspace

PURPOSES = ("tts", "audio")
"""What the voices can be collected for; see `AppState.purpose`."""
GROUP_THRESHOLD = 0.70
"""The Groups view uses anime-va's threshold."""
MAYBE_FLOOR = 0.05
"""The "possibly missed" list in the Characters view only includes clips whose chance of being the
target is at least this number."""
UNUSABLE = Words("人标了质量低", "marked low quality")
"""Why a clip someone marked low quality was skipped on export, as written in rejected.tsv."""
MAYBE_LIMIT = 100
"""The "possibly missed" list shows at most this many clips, most likely first."""


def _code_stamp() -> float:
    """When the program's own Python files last changed. The page files are read from disk on
    every request, so after an update (git pull) a running server would serve the new page with
    its old code; comparing this stamp with the one at start tells the page to ask for a
    restart."""
    return max(p.stat().st_mtime for p in Path(__file__).parent.rglob("*.py"))


class WorkspaceService:
    def __init__(
        self,
        root: Path,
        models: tuple[str, ...] = DEFAULT_MODELS,
        grouping: str = GROUPING_MODEL,
        device: str = "cpu",
        background: bool = False,
    ) -> None:
        """`background` turns on the jobs that run by themselves: downloading the low-quality
        hint's starter (`_quality_setup`) and making whole-episode copies (`_copy_loop`). Off in
        tests, which have nothing to download and no real video."""
        self.models, self.grouping_model = models, grouping
        self.device = resolve_device(device)
        """Where the classifier is trained: "cuda" or "cpu"."""
        self._weights: Weights | None = None
        """The last training's answer, the starting point of the next one."""
        self.code_stamp = _code_stamp()
        self.workspace = load_workspace(root, models, grouping)
        self.store = LabelStore(self.workspace.labels_dir)
        self.adding = Adding(root, lambda _: self.reload())
        self.adding.drop_records(set(self.workspace.episodes))
        self.lock = threading.RLock()
        from avoc.operations import Operations

        self.operations = Operations(self)
        from avoc.jobs import Jobs

        self.jobs = Jobs(self.store.path, self.adding if background else None)
        self._trained_revision = -1
        self.guesses: dict[int, Guess] = {}
        self.trained: dict[str, Any] = {}
        self.tags: dict[str, str | None] = {}
        self.low: dict[str, float] = {}
        """Clip ID to the chance it is low quality (see quality.py). Empty until the hint works."""
        self._starter: quality.Starter | None = None
        self._quality_key: Any = None
        self.quality_info: dict[str, Any] = {}
        self.background = background
        from avoc.playback import Playback

        self.playback = Playback(self)
        self.retrain()
        if background:
            threading.Thread(target=self._quality_setup, daemon=True).start()

    def reload(self) -> None:
        """Load the workspace again after an episode was added. Labels are kept as they are."""
        workspace = load_workspace(self.workspace.root, self.models, self.grouping_model)
        with self.lock:
            self.workspace = workspace
            self.retrain()
        self.adding.drop_records(set(workspace.episodes))

    # Model

    def retrain_if_changed(self) -> None:
        if self.store.refresh():
            self.workspace = load_workspace(self.workspace.root, self.models, self.grouping_model)
        if self._trained_revision != self.store.revision:
            self.retrain()

    def retrain(self) -> None:
        """Each labeled clip gives the names it may be (see `train_and_predict`): its target, or
        "other" plus the targets added since it was labeled "other". A clip labeled as a
        character who is not a target is surely "other". "Not this character" takes that name
        out. Clips marked "low quality" are not used in training."""
        targets = self.store.targets()
        everyone = frozenset((*targets, OTHER))
        answers: dict[int, frozenset[str]] = {}
        rejects: dict[int, set[str]] = {}
        for clip_id, clip in self.workspace.by_id.items():
            if clip.row is None:
                continue
            rejected = self.store.rejects.get(clip_id, set())
            if rejected:
                rejects[clip.row] = set(rejected)
            name = self.store.labels.get(clip_id)
            if clip_id in self.store.unusable or name == IGNORED or (name is None and not rejected):
                continue
            if name is None:
                may = everyone
            elif name in targets:
                may = frozenset({name})
            elif name == OTHER:
                may = everyone - self.store.against.get(clip_id, set())
            else:
                may = frozenset({OTHER})
            may -= rejected
            if may and may != everyone:
                answers[clip.row] = may
        began = time.perf_counter()
        trained = train_and_predict(
            self.workspace.features,
            targets,
            answers,
            rejects,
            MIN_GUESS_LABELS,
            self.device,
            self._weights,
        )
        self.guesses, self._weights = trained.guesses, trained.weights
        guessed = set(guessed_targets(targets, answers, MIN_GUESS_LABELS))
        self.trained = {
            "labels": len(answers),
            "roles": len(targets),
            "seconds": round(time.perf_counter() - began, 2),
            "device": self.device,
            "familiar_threshold": trained.threshold,
            "min_labels": MIN_GUESS_LABELS,
            # Targets the machine does not guess yet, with what it has of them so far.
            "waiting": {
                t: {
                    "lines": sum(s == {t} for s in answers.values()),
                    "others": sum(t not in s for s in answers.values()),
                }
                for t in targets
                if t not in guessed
            },
        }
        self._find_tags(set(targets))
        self._train_quality()
        self._trained_revision = self.store.revision

    def _quality_setup(self) -> None:
        """In the background: download the starter weights, then train the hint again. Episodes
        added before the hint existed get their features from `avoc quality`, not here: WavLM
        takes several GB of memory, too much for every running app to load on its own."""
        starter = quality.read_starter(quality.starter_path())
        with self.lock:
            self._starter = starter
            self._train_quality()

    def _train_quality(self) -> None:
        """Train the "low quality" hint on the clips labeled as a character: "clean", or "low"
        when marked low quality. Lines labeled "not a target" or "ignored" are left out. With the
        starter weights it works from the first label; without, it waits for `quality.MIN_EACH`
        of each kind."""
        ws = self.workspace
        names = {r["name"] for r in self.store.roles}
        picked = sorted(
            (row, clip_id in self.store.unusable)
            for clip_id, name in self.store.labels.items()
            if name in names and (row := ws.quality_rows.get(clip_id)) is not None
        )
        # Train again only when the workspace, the labels used or the starter changed.
        last = self._quality_key
        if last and last[0] is ws and last[1] == picked and last[2] is self._starter:
            return
        self._quality_key = (ws, picked, self._starter)
        lows = sum(low for _, low in picked)
        cleans = len(picked) - lows
        ready = ws.quality is not None and (
            self._starter is not None or min(lows, cleans) >= quality.MIN_EACH
        )
        self.quality_info.update(
            clean=cleans,
            low=lows,
            starter=self._starter is not None,
            ready=ready,
            min_each=quality.MIN_EACH,
            missing=list(ws.quality_missing),
        )
        if not ready:
            self.low = {}
            return
        model = self._starter
        if picked:
            rows = [row for row, _ in picked]
            model = quality.fit(ws.quality[rows], [low for _, low in picked], self._starter)
        assert model is not None
        chances = quality.chances(model, ws.quality)
        self.low = {clip_id: float(chances[row]) for clip_id, row in ws.quality_rows.items()}

    def _find_tags(self, targets: set[str]) -> None:
        """Each target character's name in the subtitles, from the lines their clips touch. It
        tells their lines from someone else's in a clip; see `own_tag`."""
        from avoc.stages.text_subtitle import own_tag

        hits: dict[str, list[Any]] = {t: [] for t in targets}
        for clip in self.workspace.clips:
            role = self.role_of(clip, targets)
            if role is not None and clip.spoken_hits:
                hits[role].extend(clip.spoken_hits)
        self.tags = {role: own_tag(found) for role, found in hits.items()}

    def role_of(self, clip: Clip, targets: set[str] | None = None) -> str | None:
        """The target character a clip belongs to, by a person's label or else the machine's top
        guess. None for "other" and for clips nobody has an answer for."""
        targets = set(self.store.targets()) if targets is None else targets
        label = self.store.labels.get(clip.id)
        if label is not None:
            return label if label in targets else None
        guess = self.guesses.get(clip.row) if clip.row is not None else None
        return guess.names[0] if guess and guess.names[0] in targets else None

    def spoken_of(self, clip: Clip, role: str | None) -> tuple[str, str | None]:
        """The clip's text in the spoken language, and why it cannot be exported (None if it
        can). `role` picks whose name in the subtitles counts as their own."""
        return self.text_of(clip, self.tags.get(role) if role else None)

    def text_of(self, clip: Clip, tag: str | None) -> tuple[str, str | None]:
        """`spoken_of`, with the character's name in the subtitles given (see `own_tag`)."""
        from avoc.stages.text_subtitle import match_hits

        if clip.spoken_hits is None:
            said = self.workspace.spoken.get(clip.episode)
            return "", str(said.problem) if said and said.problem else say("没有台词", "no text")
        return match_hits(clip.spoken_hits, *clip.line, tag)

    # Views

    def status(self, clip: Clip) -> str:
        if self.store.labels.get(clip.id) == IGNORED:
            return "ignored"
        if clip.id in self.store.labels:
            return "confirmed"
        if clip.skipped:
            return "skipped"
        if self.low.get(clip.id, 0.0) >= quality.SET_ASIDE:
            return "likely_low"
        # No voiceprint is almost always a short line, skipped above; the rare long one is silent,
        # or missing from a cache. Either way the machine has no guess.
        guess = self.guesses.get(clip.row) if clip.row is not None else None
        if guess is None:
            return "unlabeled"
        return (
            "auto" if guess.confidence >= AUTO_CONFIDENCE and guess.familiar is True else "review"
        )

    def view(self, clip: Clip) -> dict[str, Any]:
        guess = self.guesses.get(clip.row) if clip.row is not None else None
        role = self.role_of(clip)
        spoken, problem = self.spoken_of(clip, role)
        return {
            "spoken": spoken,
            "spoken_problem": problem,
            "role": role,
            "id": clip.id,
            "episode": clip.episode,
            "start": round(clip.start, 3),
            "end": round(clip.end, 3),
            "duration": round(clip.duration, 2),
            "short": clip.skipped,
            "overlap": clip.overlap,
            "text": clip.text,
            "display": clip.display,
            "scene": clip.scene,
            "voiced": clip.row is not None,
            "label": self.store.labels.get(clip.id),
            "rejects": sorted(self.store.rejects.get(clip.id, ())),
            "unusable": clip.id in self.store.unusable,
            # The chance of low quality, sent only when it is high enough to show the hint.
            "low": round(low, 3) if (low := self.low.get(clip.id, 0.0)) >= quality.HINT else None,
            "guess": [
                {"name": n, "p": p} for n, p in zip(guess.names, guess.probabilities, strict=True)
            ]
            if guess
            else [],
            "familiar": guess.familiar if guess else None,
            "status": self.status(clip),
        }

    def _unfinished(self, not_cut: list[str]) -> dict[str, str]:
        """Episodes not loaded, and why: ones with clips but not all voiceprints, and ones whose
        clips were never cut, known only from the record of episodes being added."""
        unfinished = {name: str(why) for name, why in self.workspace.skipped.items()}
        for name in not_cut:
            unfinished.setdefault(
                name,
                say(
                    "上次没加完，片段还没切好。接着做要从头切，这一步最慢",
                    "not finished last time, and its clips were never cut. Carrying on starts "
                    "the cutting over, the slowest step",
                ),
            )
        return unfinished

    def summary(self) -> dict[str, Any]:
        self.retrain_if_changed()
        per_episode: dict[str, Counter[str]] = {e: Counter() for e in self.workspace.episodes}
        work: Counter[str] = Counter()
        confirmed: Counter[str] = Counter()
        predicted: Counter[str] = Counter()
        to_check: Counter[str] = Counter()
        seconds: defaultdict[str, float] = defaultdict(float)
        low_seconds: defaultdict[str, float] = defaultdict(float)
        for clip in self.workspace.clips:
            state = self.status(clip)
            per_episode[clip.episode][state] += 1
            hinted = self.low.get(clip.id, 0.0) >= quality.HINT
            if state in ("review", "unlabeled") and not hinted:
                work[clip.episode] += 1
            label = self.store.labels.get(clip.id)
            if state == "confirmed" and label:
                confirmed[label] += 1
                seconds[label] += clip.duration
                if clip.id in self.store.unusable:
                    low_seconds[label] += clip.duration
            elif state in ("auto", "review") and clip.row is not None:
                name = self.guesses[clip.row].names[0]
                predicted[name] += 1
                if not hinted:
                    to_check[name] += 1

        def counts(name: str) -> dict[str, Any]:
            """How many lines were confirmed and how many the machine assigned. `to_check` is the
            part of those without the "maybe low quality" hint: what "Confirm the rest" in the
            Characters view confirms. Also the total seconds of confirmed lines, and the seconds of
            those marked "low quality"."""
            return {
                "confirmed": confirmed[name],
                "predicted": predicted[name],
                "to_check": to_check[name],
                "seconds": round(seconds[name], 1),
                "low_seconds": round(low_seconds[name], 1),
            }

        # Target characters are always listed, even with no lines yet. Characters that are no
        # longer targets are listed too when they have labels, so they can be added back.
        roles = [
            {**role, **counts(role["name"])}
            for role in self.store.roles
            if role.get("target") or confirmed[role["name"]]
        ]
        roles.sort(key=lambda r: (not r.get("target"), -(r["confirmed"] + r["predicted"])))
        blocked = self._blocked()
        not_cut = self.adding.not_cut()
        return {
            "episodes": [
                {
                    "name": name,
                    "video": bool(meta.get("video")),
                    "offset": meta.get("subtitle_offset"),
                    # More than one when the subtitle timing jumped within the episode; then
                    # the add form does not fill in its offset for the next one.
                    "offset_parts": len(meta.get("subtitle_offsets") or [None]),
                    "counts": dict(per_episode[name]),
                    # Lines still to do: not confident or not guessed, without the "maybe low
                    # quality" hint. What Scenes lists under To do.
                    "work": work[name],
                    # The whole-episode copy is ready to play.
                    "player": copy_ready(Path(meta["directory"]), meta),
                    "spoken": self._spoken_summary(name, blocked[name]),
                }
                for name, meta in self.workspace.episodes.items()
            ],
            "workspace": str(self.workspace.root.resolve()),
            "revision": self.store.revision,
            "export_folder": str(free_export_folder(self.workspace.root)),
            "skipped": self._unfinished(not_cut),
            "not_cut": not_cut,
            "roles": roles,
            "other": counts(OTHER),
            "model": {**self.trained, "auto_confidence": AUTO_CONFIDENCE},
            "quality": {**self.quality_info, "hint": quality.HINT, "set_aside": quality.SET_ASIDE},
            # Seconds of picture before and after each line, with the vocals muted there.
            "picture_pad": PICTURE_PAD,
            "can_undo": self.store.can_undo(),
            "outdated": _code_stamp() > self.code_stamp,
            "purpose": self.purpose(),
        }

    # What the voices are for

    @property
    def _purpose_file(self) -> Path:
        return self.workspace.labels_dir / "purpose.json"

    def purpose(self) -> str | None:
        """What the voices are collected for: "tts" (reading text aloud, so each line's text is
        needed too) or "audio" (sound only). Chosen once, at the start; None until then."""
        path = self._purpose_file
        return read_json(path)["purpose"] if path.exists() else None

    def set_purpose(self, purpose: str) -> None:
        """Record the choice. It is made once: switching midway is not supported yet."""
        if purpose not in PURPOSES:
            raise ValueError(say(f"不认识的用途：{purpose}", f"unknown purpose: {purpose}"))
        chosen = self.purpose()
        if chosen is not None and chosen != purpose:
            raise ValueError(
                say(
                    "收集声音做什么用，开始时已经选定，中途换还不支持",
                    "what the voices are for was chosen at the start; switching midway is not "
                    "supported yet",
                )
            )
        write_json(self._purpose_file, {"purpose": purpose})

    def _blocked(self) -> Counter[str]:
        """Per episode, how many clips of target characters cannot be exported with text."""
        targets = set(self.store.targets())
        blocked: Counter[str] = Counter()
        for clip in self.workspace.clips:
            if role := self.role_of(clip, targets):
                blocked[clip.episode] += self.spoken_of(clip, role)[1] is not None
        return blocked

    def _spoken_summary(self, episode: str, blocked: int) -> dict[str, Any]:
        """The episode's spoken language and where its text comes from."""
        said = self.workspace.spoken[episode]
        return {
            "language": said.language,
            "assumed": said.assumed,
            "source": said.source,
            "problem": str(said.problem) if said.problem else None,
            "blocked": blocked,
        }

    # Changes

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        """Every value sent to a client, independent of where it keeps the line in a list."""
        return {clip.id: self.view(clip) for clip in self.workspace.clips}

    def change(self, batch_maker: Any) -> dict[str, Any]:
        """Make one change and retrain. Returns the clips it changed directly, the clips whose
        predictions changed as a side effect, and the new overview."""
        with self.lock:
            before = self._snapshot()
            batch = batch_maker()
            if batch is None:
                return {"batch": None, "updated": [], "ripple": 0, "state": self.summary()}
            self.retrain()
            after = self._snapshot()
            touched = {c["clip"] for c in batch["changes"]}
            moved = [i for i in after if after[i] != before[i] and i not in touched]
            return {
                "batch": batch["batch"],
                "undo": batch.get("undo_of") is not None,
                "updated": [self.view(self.workspace.by_id[i]) for i in [*touched, *moved]
                            if i in self.workspace.by_id],
                "ripple": len(moved),
                "state": self.summary(),
            }  # fmt: skip

    # Groups view

    def groups(self, episode: str | None) -> list[dict[str, Any]]:
        from sklearn.cluster import AgglomerativeClustering

        # Only lines still to do, as in "Only to do" in Scenes: not labeled, not skipped, with a
        # voiceprint, not a guess the machine is confident about, and without the "maybe low
        # quality" hint.
        pool = [
            c
            for c in self.workspace.clips
            if (episode is None or c.episode == episode)
            and c.row is not None
            and self.status(c) in ("review", "unlabeled")
            and self.low.get(c.id, 0.0) < quality.HINT
        ]
        if len(pool) < 2:
            return []
        vectors = self.workspace.grouping[[c.row for c in pool]]
        found = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=GROUP_THRESHOLD,
        ).fit_predict(vectors)
        members: dict[int, list[Clip]] = {}
        for clip, group in zip(pool, found, strict=True):
            members.setdefault(int(group), []).append(clip)
        result: list[dict[str, Any]] = []
        for clips in members.values():
            if len(clips) < 2:
                continue
            clips.sort(key=lambda c: (c.episode, c.start))
            hints = Counter(
                self.guesses[c.row].names[0]
                for c in clips
                if c.row in self.guesses and self.guesses[c.row].names[0] != OTHER
            ).most_common(1)
            result.append(
                {
                    "size": len(clips),
                    "seconds": round(sum(c.duration for c in clips), 1),
                    "hint": {"name": hints[0][0], "share": round(hints[0][1] / len(clips), 2)}
                    if hints
                    else None,
                    "clips": [self.view(c) for c in clips],
                }
            )
        result.sort(key=lambda g: -len(g["clips"]))
        return result

    def role_clips(self, role: str, only_maybe: bool = False) -> list[dict[str, Any]]:
        """Characters view: clips confirmed for this character, clips the machine assigned to
        them (skipped ones included), and the "possibly missed" clips (`maybe`).

        Possibly missed clips are ones the machine did not assign to them, but whose chance of being
        them is not low. These are clips not labeled yet, and clips labeled "other" while that
        character was not yet a target character. After a new target character is added, the
        earlier "other" labels are checked again from here.
        "Other" has no possibly-missed list. A clip the machine did not give to "other" was given to
        some target character, and it is checked within that character.
        Confirmed "other" clips are sorted starting from the ones closest to a target character,
        so wrong labels show up first. Sorting happens once when the list is fetched, so a clip
        does not jump after it is labeled.
        With `only_maybe`, only the possibly missed clips: after each change the web app fetches
        them again, so updating the list can add and take out the ones that changed.
        """
        mine: list[Clip] = []
        maybe: list[tuple[float, Clip]] = []
        for clip in self.workspace.clips:
            label = self.store.labels.get(clip.id)
            if label == role:
                mine.append(clip)
                continue
            guess = self.guesses.get(clip.row) if clip.row is not None else None
            if guess is None or role in self.store.rejects.get(clip.id, ()):
                continue
            # Short lines nobody labeled, and lines a person ignored, are listed under Ignored
            # when the machine gives them to this character, never as possibly missed.
            if (label is None and clip.skipped) or label == IGNORED:
                if guess.names[0] == role:
                    mine.append(clip)
                continue
            unchecked = label is None or (
                label == OTHER and role not in self.store.against.get(clip.id, ())
            )
            if label is None and guess.names[0] == role:
                mine.append(clip)
            elif role != OTHER and unchecked and guess.p(role) >= MAYBE_FLOOR:
                maybe.append((guess.p(role), clip))
        maybe.sort(key=lambda pair: -pair[0])
        missed = [{**self.view(c), "maybe": True} for _, c in maybe[:MAYBE_LIMIT]]
        if only_maybe:
            return missed
        views = [self.view(c) for c in mine]
        if role == OTHER:
            views.sort(
                key=lambda c: -max((g["p"] for g in c["guess"] if g["name"] != OTHER), default=0)
            )
        return views + missed

    def references(self, name: str) -> list[dict[str, Any]]:
        """The few clips that work best as reference audio for this character. Clips confirmed by a
        person and between 1.5 and 6 seconds long come first."""
        own = [
            c
            for c in self.workspace.clips
            if self.store.labels.get(c.id) == name and c.row is not None
        ]
        own.sort(key=lambda c: (not 1.5 <= c.duration <= 6.0, -c.duration))
        return [self.view(c) for c in own[:3]]

    # Media

    def media(self, kind: str, clip_id: str, context: int = 0, fresh: bool = False) -> Path:
        return self.playback.media(kind, clip_id, context, fresh)

    def prefetch(self, clip_id: str, seconds: float = 60.0) -> int:
        return self.playback.prefetch(clip_id, seconds)

    def player(self, name: str) -> dict[str, Any]:
        return self.playback.player(name)

    def want_copy(self, name: str) -> None:
        self.playback.want_copy(name)

    def close(self) -> None:
        self.playback.close()
        if self.adding.status()["state"] == "running":
            self.adding.stop()

    def save_avatar(self, name: str, data_url: str) -> dict[str, Any]:
        head, _, body = data_url.partition(",")
        if head not in ("data:image/jpeg;base64", "data:image/png;base64"):
            raise ValueError(say("头像只收 JPEG 或 PNG", "the picture must be JPEG or PNG"))
        raw = base64.b64decode(body, validate=True)
        if len(raw) > 2_000_000:
            raise ValueError(say("头像太大", "the picture is too large"))
        file = hashlib.sha256(raw).hexdigest()[:16] + (".jpg" if "jpeg" in head else ".png")
        folder = self.workspace.labels_dir / "avatars"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / file).write_bytes(raw)
        return self.store.update_role(name, avatar=file)

    # Export

    def set_spoken(self, episode: str, code: str) -> dict[str, Any]:
        from avoc.pipeline import set_spoken_language

        meta = self.workspace.episodes.get(episode)
        if meta is None:
            raise ValueError(say(f"没有 {episode} 这一集", f"there is no episode {episode}"))
        result = set_spoken_language(Path(meta["directory"]), code)
        self.reload()
        return result

    def _text_for_export(
        self, assigned: dict[str, list[Clip]], form: str, texts: dict[str, str],
        rejected: list[dict[str, Any]],
    ) -> str:  # fmt: skip
        """Fill `texts` with each clip's spoken text, move the clips without it from `assigned`
        to `rejected`, and return the languages wanted, for a message when none is left."""
        from avoc.stages.text_language import name_of
        from avoc.stages.text_subtitle import own_tag

        wanted: set[str] = set()
        for role, clips in assigned.items():
            # Whose name in the subtitles is this character's, from the clips exported for them.
            tag = own_tag(x for c in clips for x in c.spoken_hits or ())
            kept = []
            for clip in clips:
                language = self.workspace.spoken[clip.episode].language
                wanted.add(language)
                text, reason = self.text_of(clip, tag)
                if reason is None:
                    texts[clip.id] = text
                    kept.append(clip)
                else:
                    rejected.append({"role": role, "clip": clip, "reason": reason, "text": text})
            clips[:] = kept
        return say("、", ", ").join(name_of(code) for code in sorted(wanted))

    def plan_export(
        self, roles: list[str], include_auto: bool, form: str, out: Path
    ) -> dict[str, Any]:
        """Capture exactly which clips and text to export before the slow file writes."""
        if form not in ("gpt-sovits", "folder"):
            raise ValueError(say("不认识的导出格式", "unknown export format"))
        if out.exists() and any(out.iterdir()):
            raise ValueError(
                say(
                    f"{out} 已存在且不是空的，换一个目录",
                    f"{out} already exists and is not empty. Pick another folder",
                )
            )
        assigned: dict[str, list[Clip]] = {name: [] for name in roles}
        rejected: list[dict[str, Any]] = []
        for clip in self.workspace.clips:
            label = self.store.labels.get(clip.id)
            state = self.status(clip)
            role = None
            if state == "confirmed" and label in assigned:
                role = label
            elif include_auto and state == "auto" and clip.row is not None:
                top = self.guesses[clip.row].names[0]
                role = top if top in assigned else None
            if role is None:
                continue
            if clip.id in self.store.unusable:
                rejected.append({"role": role, "clip": clip, "reason": str(UNUSABLE), "text": ""})
            else:
                assigned[role].append(clip)
        if not any(assigned.values()):
            raise ValueError(
                say(
                    f"没有可导出的片段：{len(rejected)} 条都标了质量低",
                    f"nothing to export: all {len(rejected)} clips are marked low quality",
                )
                if rejected
                else say("没有可导出的片段", "nothing to export")
            )
        texts: dict[str, str] = {}
        if form != "folder":
            problems = self._text_for_export(assigned, form, texts, rejected)
            if not any(assigned.values()):
                raise ValueError(
                    say(
                        f"一条也没导出：没有一条片段有{problems}台词。这些集是用别的语言的字幕切的，"
                        "只能导出音频；要文字就用这种语言的字幕重新加这几集",
                        f"nothing was exported: no clip has {problems} text. These episodes were "
                        "cut from subtitles in another language, so only audio can be exported; "
                        "for text, add them again with subtitles in that language",
                    )
                )

        def record(clip: Clip) -> dict[str, Any]:
            return {"id": clip.id, "episode": clip.episode, "start": clip.start, "end": clip.end}

        return {
            "revision": self.store.revision,
            "workspace": str(self.workspace.root.resolve()),
            "assigned": {
                name: [record(c) for c in clips] for name, clips in assigned.items() if clips
            },
            "vocals": {name: meta["vocals"] for name, meta in self.workspace.episodes.items()},
            "languages": {name: said.language for name, said in self.workspace.spoken.items()},
            "texts": texts,
            "rejected": [
                {**r, "clip": {**record(r["clip"]), "text": r["clip"].text}} for r in rejected
            ],
            "folders": {
                name: role["id"] for name in assigned if (role := self.store.role(name)) is not None
            },
            "form": form,
            "out": str(out.resolve()),
        }

    def export(self, roles: list[str], include_auto: bool, form: str, out: Path) -> dict[str, Any]:
        """The synchronous entry point; callers need not hold the workspace lock."""
        from avoc.exporting import run_export

        with self.lock:
            plan = self.plan_export(roles, include_auto, form, out)
        result = run_export(plan)
        return {**result, "next": str(free_export_folder(self.workspace.root))}
