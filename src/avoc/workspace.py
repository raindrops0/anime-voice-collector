"""One workspace. Each episode has its own folder under `episodes/`. `labels/` holds the label
records and the character list.

On load, each clip's subtitle text is looked up from the subtitles, the clips are split into scenes
at pauses, and the caches of several voiceprint models are joined into one table. A clip shorter
than 0.5 seconds has no voiceprint (see MIN_SECONDS in embeddings/extract.py). These clips still
appear in the interface, but the machine cannot make a prediction for them, so a person must
identify them.

A clip shorter than `SKIP_SECONDS`, or whose spoken text has at most `SKIP_SYLLABLES` syllables, is
skipped by default, so a person does not need to label it. See `Clip.skipped`.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avoc import quality
from avoc.embeddings.cache import load_embeddings
from avoc.language import Words
from avoc.project import episode_dirs as episode_dirs
from avoc.project import load_episode
from avoc.settings import DEFAULT_MODELS as DEFAULT_MODELS
from avoc.settings import GROUPING_MODEL as GROUPING_MODEL
from avoc.stages.subtitle import subtitle_lines as subtitle_lines
from avoc.stages.text_subtitle import TextLine
from avoc.stages.text_subtitle import text_for as text_for

SCENE_GAP = 3.0
"""If the pause between two lines of dialogue is longer than this many seconds, a new scene starts.
This is only used to split the dialogue for display. It does not affect identifying anyone."""

SKIP_SECONDS = 1.0
"""Clips shorter than this many seconds are of little use for training speech synthesis, so by
default a person does not need to label them. A short clip right next to other lines used to be
kept, in case the subtitles had split up one long line; that kept 89% of the short clips, most of
them interjections."""

SKIP_SYLLABLES = 2
"""A clip whose spoken text has at most this many syllables is skipped however long it is: a
drawn-out interjection or shout, such as あっ, ハッ or うおーっ. In the 13 Amazon-cut episodes this
skips 220 clips of 1 second or more; 9 were Teio's in the old labels, such as よーし and おーい.
At 3 syllables it would also skip names and short answers, such as テイオー and えっ 僕？"""


OVERLAP_SECONDS = 0.1
"""Two clips whose voice overlaps by more than this are marked as spoken at once. Smaller overlaps
are timing noise. Subtitle makers leave a gap between lines that follow each other, so in the 13
Netflix-cut episodes an overlap was almost never a short handover: of 288 pairs over 0.1 seconds,
the median was 1.0 seconds, and in 70% one line lay wholly inside the other."""


@dataclass(frozen=True)
class Clip:
    id: str
    episode: str
    start: float
    end: float
    text: str
    scene: int
    row: int | None
    """Row number in the voiceprint table. None when there is no voiceprint."""
    spoken_hits: tuple[TextLine, ...] | None = None
    """The lines in the spoken language that touch this clip (see `touching` in
    stages/text_subtitle.py). None when the episode has no text in the spoken language."""
    display: str = ""
    """The secondary subtitle line that overlaps this clip, shown small under `text`. Empty when the
    episode has no secondary subtitles or none of their lines overlaps."""
    line_start: float | None = None
    line_end: float | None = None
    """The subtitle line the clip was cut from; `start` and `end` are the part with voice inside it.
    The text is looked up by the line, so tightening never loses a clip its words. None for clips
    cut before edges were tightened, whose own time is the line's."""
    overlap: bool = False
    """Its voice overlaps another clip's by more than `OVERLAP_SECONDS`: two lines spoken at once,
    so most likely two voices in it."""
    syllables: int | None = None
    """About how many syllables its spoken text has (see `syllables` in stages/text_language.py).
    None when it has no text in the spoken language."""

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def line(self) -> tuple[float, float]:
        """The time of the subtitle line the clip was cut from."""
        low = self.start if self.line_start is None else self.line_start
        return low, self.end if self.line_end is None else self.line_end

    @property
    def skipped(self) -> bool:
        """Too short, or too few syllables. It is skipped by default, so a person does not need to
        label it."""
        few = self.syllables is not None and self.syllables <= SKIP_SYLLABLES
        return self.duration < SKIP_SECONDS or few


@dataclass(frozen=True)
class SpokenText:
    """Where an episode's text in the spoken language comes from."""

    language: str
    assumed: bool
    """True when no tag or person said what is spoken, and Japanese was taken."""
    source: str | None
    """`cut` when the main subtitles are in that language, or None when there is no such text."""
    problem: Words | None = None
    """Why there is no text, for the person. None when there is."""
    lines: tuple[TextLine, ...] = ()
    """Lines in the spoken language, in audio-track time."""


def spoken_text(episode: dict[str, Any]) -> SpokenText:
    """The spoken-language text comes from the main subtitles, when they are in that language. A
    missing or unreadable file is reported, not raised, so the interface still opens."""
    from avoc.pipeline import spoken_language
    from avoc.stages.subtitle import episode_parts
    from avoc.stages.text_subtitle import load_text_lines, shifted, subtitle_languages, turn_lines

    spoken = spoken_language(episode)
    assumed = not episode.get("spoken_language") or episode.get("spoken_from") == "assumed"
    language = Words(name_of_in("zh", spoken), name_of_in("en", spoken))

    def failed(zh: str, en: str) -> SpokenText:
        return SpokenText(spoken, assumed, None, Words(zh, en))

    path = Path(episode.get("subtitles") or "")
    if not path.is_file():
        return failed("没记主字幕", "no main subtitles are recorded")
    styles = episode.get("subtitle_styles")
    parts = episode_parts(episode)
    try:
        if episode.get("segmentation") == "speaker_turns":
            # Cut one person at a time, so each clip's text is its own line; see `turn_lines`.
            lines = turn_lines(path, styles)
            return SpokenText(spoken, assumed, "cut", None, tuple(shifted(lines, parts)))
        if spoken in subtitle_languages(path, styles):
            lines = load_text_lines(path, styles, spoken)
            return SpokenText(spoken, assumed, "cut", None, tuple(shifted(lines, parts)))
    except ValueError as exc:
        return failed(str(exc), str(exc))
    return failed(
        f"主字幕不是{language.zh}，这一集导不出文字",
        f"the main subtitles are not in {language.en}, so this episode has no text to export",
    )


def name_of_in(page: str, code: str) -> str:
    """A language's name in one page language, for messages built before a request."""
    from avoc.stages.text_language import LANGUAGES

    words = LANGUAGES.get(code)
    return (words.zh if page == "zh" else words.en) if words else code


def hits_for(lines: tuple[TextLine, ...], starts: list[float], reach: float, start: float,
             end: float) -> tuple[TextLine, ...]:  # fmt: skip
    """`touching` with a binary search: `starts` are the lines' starts and `reach` the longest
    line, so only lines that can reach the clip are looked at."""
    from avoc.stages.text_subtitle import touching

    low = bisect.bisect_left(starts, start - reach)
    high = bisect.bisect_right(starts, end)
    return tuple(touching(list(lines[low:high]), start, end))


@dataclass
class Workspace:
    root: Path
    episodes: dict[str, dict[str, Any]]
    """Episode name to the contents of episode.json, plus an extra `directory` entry."""
    clips: list[Clip]
    features: Any
    grouping: Any
    models: tuple[str, ...]
    skipped: dict[str, Words] = field(default_factory=dict)
    """Episode name to the reason it was not loaded. Usually the voiceprints are incomplete."""
    by_id: dict[str, Clip] = field(default_factory=dict)
    spoken: dict[str, SpokenText] = field(default_factory=dict)
    """Episode name to its text in the spoken language."""
    quality: Any = None
    """The low-quality hint's features, one float16 row per clip that has them (see quality.py)."""
    quality_rows: dict[str, int] = field(default_factory=dict)
    """Clip ID to its row in `quality`."""
    quality_missing: list[str] = field(default_factory=list)
    """Episodes whose quality features are not computed yet."""

    def __post_init__(self) -> None:
        self.by_id = {c.id: c for c in self.clips}

    @property
    def labels_dir(self) -> Path:
        return self.root / "labels"


def display_lines(episode: dict[str, Any]) -> list[tuple[float, float, str]]:
    """The lines of the display subtitles (see `attach_display_subtitles` in pipeline.py), in
    audio-track time. Empty when there are none or the file is gone."""
    from avoc.stages.subtitle import episode_parts, load_dialogue, offset_at

    path = Path(episode.get("display_subtitles") or "")
    if not path.is_file():
        return []
    parts = episode_parts(episode, "display_subtitle_offset")
    lines = load_dialogue(path, episode.get("display_subtitle_styles"))
    return [
        (
            d["start"] + offset_at(parts, d["start"]),
            d["end"] + offset_at(parts, d["start"]),
            d["text"],
        )
        for d in lines
    ]


def syllables_of(
    hits: tuple[TextLine, ...] | None, low: float, high: float, language: str
) -> int | None:
    """How many syllables the clip's spoken text has, or None when it has none."""
    from avoc.stages.text_language import syllables
    from avoc.stages.text_subtitle import match_hits

    text = match_hits(hits, low, high)[0] if hits else ""
    return syllables(text, language) if text else None


def overlapping(spans: list[tuple[float, float]]) -> set[tuple[float, float]]:
    """The spans, sorted by start, that share more than `OVERLAP_SECONDS` with another span."""
    found: set[tuple[float, float]] = set()
    for k, (start, end) in enumerate(spans):
        for low, high in spans[k + 1 :]:
            if low >= end:
                break
            if min(end, high) - low > OVERLAP_SECONDS:
                found.update({(start, end), (low, high)})
    return found


def load_workspace(
    root: Path, models: tuple[str, ...] = DEFAULT_MODELS, grouping: str = GROUPING_MODEL
) -> Workspace:
    import numpy as np

    episodes: dict[str, dict[str, Any]] = {}
    clips: list[Clip] = []
    feature_rows: list[Any] = []
    grouping_rows: list[Any] = []
    skipped: dict[str, Words] = {}
    spoken: dict[str, SpokenText] = {}
    quality_parts: list[Any] = []
    quality_rows: dict[str, int] = {}
    quality_missing: list[str] = []
    for directory in episode_dirs(root):
        episode, rows = load_episode(directory)
        try:
            ids, parts = _aligned_vectors(directory, (*models, grouping))
        except (FileNotFoundError, ValueError) as exc:
            # Usually avoc add was interrupted partway. Skip this episode so the whole interface
            # does not fail to open.
            skipped[episode["name"]] = (
                Words(
                    "声纹没算全。在界面里点「接着做」，或者再运行一遍加这一集的 avoc add 命令",
                    "voiceprints are incomplete. Press Carry on in the interface, "
                    "or run the same avoc add command again",
                )
                if isinstance(exc, FileNotFoundError)
                else Words(
                    f"各声纹模型覆盖的片段不同，重跑 avoc embed（{exc}）",
                    f"the voiceprint models cover different clips; rerun avoc embed ({exc})",
                )
            )
            continue
        episodes[episode["name"]] = {**episode, "directory": str(directory)}
        joined = np.concatenate(parts[: len(models)], axis=1)
        joined /= np.linalg.norm(joined, axis=1, keepdims=True)
        position = {clip_id: len(feature_rows) + k for k, clip_id in enumerate(ids)}
        feature_rows.extend(joined)
        grouping_rows.extend(parts[-1])
        found = quality.load(directory)
        if found is None:
            quality_missing.append(episode["name"])
        else:
            first = sum(len(q) for q in quality_parts)
            quality_rows.update({clip_id: first + k for k, clip_id in enumerate(found[0])})
            quality_parts.append(found[1])

        said = spoken[episode["name"]] = spoken_text(episode)
        said_starts = [x.start for x in said.lines]
        reach = max((x.end - x.start for x in said.lines), default=0.0)
        lines = subtitle_lines(episode)
        starts = [line[0] for line in lines]
        # The main subtitle line is shown large; a secondary subtitle line, small under it.
        shown = display_lines(episode)
        shown_starts = [line[0] for line in shown]
        spans = sorted((float(row["start"]), float(row["end"])) for row in rows)
        both = overlapping(spans)
        scene, previous_end = 0, None
        for row in rows:
            if previous_end is not None and row["start"] - previous_end > SCENE_GAP:
                scene += 1
            previous_end = row["end"] if previous_end is None else max(previous_end, row["end"])
            start, end = float(row["start"]), float(row["end"])
            # Words come from the subtitle line the clip was cut from, not from its tightened time.
            low = float(row.get("line_start", start))
            high = float(row.get("line_end", end))
            hits = (
                None if said.source is None else hits_for(said.lines, said_starts, reach, low, high)
            )
            clips.append(
                Clip(
                    id=row["id"],
                    episode=episode["name"],
                    start=start,
                    end=end,
                    text=text_for(lines, starts, low, high),
                    scene=scene,
                    row=position.get(row["id"]),
                    spoken_hits=hits,
                    display=text_for(shown, shown_starts, low, high),
                    line_start=row.get("line_start"),
                    line_end=row.get("line_end"),
                    overlap=(start, end) in both,
                    syllables=syllables_of(hits, low, high, said.language),
                )
            )
    width = feature_rows[0].shape[0] if feature_rows else 0
    return Workspace(
        root=root,
        episodes=episodes,
        clips=clips,
        features=np.stack(feature_rows) if feature_rows else np.empty((0, width)),
        grouping=np.stack(grouping_rows) if grouping_rows else np.empty((0, 0)),
        models=models,
        skipped=skipped,
        spoken=spoken,
        quality=np.concatenate(quality_parts) if quality_parts else None,
        quality_rows=quality_rows,
        quality_missing=quality_missing,
    )


def _aligned_vectors(directory: Path, models: tuple[str, ...]) -> tuple[list[str], list[Any]]:
    """Each model's voiceprints are put in the same clip order. If a cache is missing, this raises
    FileNotFoundError. If the models cover different clips, it raises ValueError."""
    parts = []
    ids: list[str] | None = None
    for model in models:
        records, vectors = load_embeddings(directory, model)
        order = {r["id"]: i for i, r in enumerate(records)}
        if ids is None:
            ids = [r["id"] for r in records]
        elif set(order) != set(ids):
            raise ValueError(str(directory))
        parts.append(vectors[[order[i] for i in ids]])
    assert ids is not None
    return ids, parts
