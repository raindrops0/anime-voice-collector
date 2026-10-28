"""Read a dialogue subtitle file and estimate its offset from the audio track. Clips take the
subtitle boundaries directly.

The file format is fixed, so pysubs2 reads the times and text of every line. Two things vary from
one subtitle group to the next, and both are handled here without asking the person to fix the
file: the text encoding, and which style (the named look an ASS file gives each line, such as
"Default" or "OP") holds the dialogue.
"""

from __future__ import annotations

import codecs
import re
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

from avoc.language import say

MAX_LINE = 20.0
SEARCH_SECONDS = 30.0
STEP = 0.01
MIN_OVERLAP_RATIO = 0.6

OTHER_ENCODINGS = ["gb18030", "big5", "cp932", "euc_jp", "euc_kr", "cp1252"]
"""Encodings tried for a file that is not UTF-8. Older Chinese subtitles are often GBK (GB18030
covers it) or Big5, older Japanese ones Shift-JIS (cp932 covers it), and older Western ones
Windows-1252. charset-normalizer picks the one whose text reads most like real language. On our
Chinese and Japanese subtitles saved in each of these, it found the right one every time."""

HALF_WIDTH_KANA = re.compile("[｡-ﾟ]")
"""Half-width katakana, which subtitles almost never use. Chinese text read as Shift-JIS turns into
it, and with only a few Chinese lines charset-normalizer can rate that reading as good as the
right one."""

ENCODING_NAMES = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8",
    "utf-16": "UTF-16",
    "utf-32": "UTF-32",
    "gb18030": "GBK",  # GB18030 extends GBK, and GBK is the name people know.
    "big5": "Big5",
    "cp932": "Shift-JIS",
    "euc_jp": "EUC-JP",
    "euc_kr": "EUC-KR",
    "cp1252": "Windows-1252",
}
"""The names people know the encodings by, as text editors show them."""

BYTE_ORDER_MARKS = [
    (codecs.BOM_UTF32_LE, "utf-32"),  # Checked before UTF-16, whose mark it starts with.
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
]

PARTS = 10
SPREAD = 0.5
"""A dialogue style has lines in at least this share of the episode. The time from the first line to
the last is cut into `PARTS` equal parts. Dialogue reaches nearly all of them. Opening and ending
songs sit in one or two."""

SIDE_STYLE = 0.25
"""A second style that is also spread through the episode, with at least this share of the main
style's line count, is dialogue too. This is the usual layout of bilingual subtitles that keep each
language in its own style. Signs and on-screen text are far fewer: in our Chinese subtitles, 40
sign lines against 402 dialogue lines."""


def decode_subtitles(data: bytes) -> tuple[str, str]:
    """The text of a subtitle file, and the name of the encoding it was read with."""
    for mark, encoding in BYTE_ORDER_MARKS:
        if data.startswith(mark):
            return data.decode(encoding), encoding
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    # Best first. charset-normalizer reads sampled pieces of the file and drops an encoding when the
    # pieces read as too messy. Its default pieces of 512 bytes dropped the right encoding for 2 of
    # our 29 test files (real subtitles saved as GBK, Big5, Shift-JIS and EUC-JP); pieces of 64
    # bytes got all 29 right. If every encoding is still dropped, the least messy one is better
    # than giving up.
    found = list(from_bytes(data, cp_isolation=OTHER_ENCODINGS, steps=200, chunk_size=64))
    if not found:
        found = list(from_bytes(data, cp_isolation=OTHER_ENCODINGS, threshold=1.0))
    plausible = [m for m in found if not HALF_WIDTH_KANA.search(str(m))]
    if not found:
        raise UnicodeError("unknown text encoding")
    best = (plausible or found)[0]
    return str(best), best.encoding


def open_subtitles(path: Path) -> tuple[Any, str]:
    """Open a subtitle file with pysubs2, and say which encoding it was read with. pysubs2 tells
    the format from the content, not the file extension: ASS, SSA, SRT, WebVTT and a few more.
    Any problem becomes a ValueError with a plain reason, instead of a library error deep in a
    traceback."""
    import pysubs2

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            say(
                f"打不开这个字幕文件：{path}（{exc}）",
                f"cannot open this subtitle file: {path} ({exc})",
            )
        ) from exc
    try:
        text, encoding = decode_subtitles(data)
    except UnicodeError as exc:
        raise ValueError(
            say(
                f"认不出这个字幕文件的文字编码：{path}。用记事本之类的工具把它另存为 UTF-8 再试",
                f"cannot tell the text encoding of this subtitle file: {path}. Save it as UTF-8 "
                "with a text editor, then try again",
            )
        ) from exc
    try:
        return pysubs2.SSAFile.from_string(text), encoding
    except pysubs2.Pysubs2Error as exc:
        raise ValueError(
            say(
                f"读不出这个字幕文件，它要是 ASS 或 SRT：{path}",
                f"cannot read this subtitle file; it must be ASS or SRT: {path}",
            )
        ) from exc


def read_subtitles(path: Path) -> Any:
    return open_subtitles(path)[0]


KARAOKE = re.compile(r"\\[kK][fo]?\d")
"""A karaoke timing tag, which lights up a song lyric one syllable at a time."""


def usable(event: Any) -> bool:
    """Whether a subtitle line can be a dialogue line, whatever its style. Dropped: comment lines,
    vector drawings, lines with no text (only layout commands), lines longer than `MAX_LINE`, the
    `====` separator lines that fansub groups (subtitle teams) use to split sections, and song
    lyrics timed for karaoke (see `KARAOKE`), which TV captions also put in their one style."""
    return (
        event.is_text  # Neither a comment nor a drawing.
        and 0 < event.end - event.start <= MAX_LINE * 1000
        and bool(event.plaintext.strip())
        and "====" not in event.plaintext
        and not KARAOKE.search(event.text)
    )


PLACED = re.compile(r"\\(pos|move|fn|fr[xyz]?|i?clip|org|fa[xy]|p[1-9])")
"""Tags that place, turn or draw a line on screen, or give it its own font: what on-screen text
(signs) is made with."""

SIGN_STYLE = 0.9
"""A style with at least this share of its lines placed on screen (see `PLACED`) holds signs, when
another style spread through the episode has at most `PLAIN_STYLE` of its lines placed. In
fansub files the sign style can have more lines than the dialogue: in one file 4,365 against 210,
every sign line placed and no dialogue line. TV captions place every line too, but they have only
one style, so they are not touched."""

PLAIN_STYLE = 0.5


def pick_styles(subs: Any) -> list[str]:
    """The styles that hold the dialogue, most lines first. Empty only if no line is usable.

    The main style is the one with the most lines among the styles spread through the episode (see
    `SPREAD`), leaving out sign styles (see `SIGN_STYLE`). Also picked: other spread styles with
    enough lines (see `SIDE_STYLE`), and styles whose name starts with the name of any of these,
    such as "Default - Top" or "JAP_Up" for a second speaker at the top of the screen. An SRT file
    has no styles; pysubs2 puts every line in "Default", so all of them are picked.
    """
    events = [e for e in subs if usable(e)]
    if not events:
        return []
    counts = Counter(e.style for e in events)
    placed = Counter(e.style for e in events if PLACED.search(e.text))
    first = min(e.start for e in events)
    width = max(1, max(e.end for e in events) - first) / PARTS
    parts: dict[str, set[int]] = {}
    for e in events:
        parts.setdefault(e.style, set()).add(min(PARTS - 1, int((e.start - first) / width)))
    spread = [s for s in counts if len(parts[s]) >= SPREAD * PARTS]
    if any(placed[s] <= PLAIN_STYLE * counts[s] for s in spread):
        spread = [s for s in spread if placed[s] < SIGN_STYLE * counts[s]]
    main = max(spread or counts, key=lambda s: counts[s])
    bases = [s for s in spread if s == main or counts[s] >= SIDE_STYLE * counts[main]] or [main]
    return [
        s
        for s, _ in counts.most_common()
        if any(s.casefold().startswith(base.casefold()) for base in bases)
    ]


def describe_styles(path: Path) -> dict[str, Any]:
    """What a person needs to check or change the styles picked: each style's line count, time
    range and a few sample lines, and the styles `pick_styles` chose."""
    subs, encoding = open_subtitles(path)
    by_style: dict[str, list[Any]] = {}
    for event in sorted((e for e in subs if usable(e)), key=lambda e: e.start):
        by_style.setdefault(event.style, []).append(event)
    styles = []
    for name, events in sorted(by_style.items(), key=lambda item: -len(item[1])):
        picks = sorted({0, len(events) // 2, len(events) - 1})
        styles.append(
            {
                "name": name,
                "lines": len(events),
                "first": events[0].start / 1000.0,
                "last": max(e.end for e in events) / 1000.0,
                "samples": [" ".join(events[i].plaintext.split()) for i in picks],
            }
        )
    picked = pick_styles(subs)
    return {
        "format": subs.format,
        "encoding": ENCODING_NAMES.get(encoding, encoding),
        "styles": styles,
        "picked": picked,
        "marked": marked_dialogue(path, picked) if picked else None,
    }


def marked_dialogue(path: Path, styles: list[str] | None = None) -> dict[str, Any] | None:
    """The dialogue lines that would still carry marks into exported text; see captions.py."""
    from avoc.stages.captions import marked, spoken

    return marked(spoken(line["text"]) for line in load_dialogue(path, styles))


def styles_note(path: Path, styles: list[str] | None = None, automatic: bool | None = None) -> str:
    """One line for the person: which styles the dialogue is taken from, and which are left out.
    When the styles were picked automatically (by default, when `styles` is None), it also says
    how to change them."""
    found = describe_styles(path)
    chosen = found["picked"] if styles is None else styles
    if automatic is None:
        automatic = styles is None

    def counted(style: dict[str, Any]) -> str:
        return say(f"{style['name']}（{style['lines']} 句）", f"{style['name']} ({style['lines']})")

    named = [counted(s) for s in found["styles"] if s["name"] in chosen]
    rest = [counted(s) for s in found["styles"] if s["name"] not in chosen]
    if not rest:
        return say(
            f"台词取自字幕样式 {'、'.join(named)}", f"Dialogue taken from {', '.join(named)}"
        )
    if not automatic:
        return say(
            f"台词取自字幕样式 {'、'.join(named)}；没用：{'、'.join(rest)}",
            f"Dialogue taken from {', '.join(named)}; left out: {', '.join(rest)}",
        )
    return say(
        f"台词取自字幕样式 {'、'.join(named)}；没用：{'、'.join(rest)}。要改就用 --styles",
        f"Dialogue taken from {', '.join(named)}; left out: {', '.join(rest)}. "
        "To change this, use --styles",
    )


def load_dialogue(path: Path, styles: list[str] | None = None) -> list[dict[str, Any]]:
    """Read one subtitle file, keep only the dialogue lines, sort them by time, and include the
    line text.

    `styles` names the styles that hold the dialogue. If it is None, they are picked by
    `pick_styles`. Lines are dropped as described in `usable`.
    """
    subs = read_subtitles(path)
    if styles is None:
        styles = pick_styles(subs)
    else:
        check_styles(subs, styles)
    lines = [
        {
            "start": event.start / 1000.0,
            "end": event.end / 1000.0,
            "text": event.plaintext.strip(),
        }
        for event in subs
        if event.style in styles and usable(event)
    ]
    return sorted(lines, key=lambda line: (line["start"], line["end"]))


def check_styles(subs: Any, styles: list[str]) -> None:
    """Refuse a list of styles that is empty or names a style with no usable lines in the file."""
    present = Counter(e.style for e in subs if usable(e))
    if not styles:
        raise ValueError(say("至少要选一个样式", "choose at least one style"))
    missing = [s for s in styles if s not in present]
    if missing:
        have = ", ".join(f"{s} ({n})" for s, n in present.most_common())
        raise ValueError(
            say(
                f"字幕里没有样式 {', '.join(missing)}。有的样式：{have}",
                f"the subtitles have no style {', '.join(missing)}. Styles there: {have}",
            )
        )


def load_lines(path: Path, styles: list[str] | None = None) -> list[tuple[float, float]]:
    """The times of the dialogue lines, sorted by time. Clipping only needs the times. For the text,
    see `load_dialogue`."""
    return [(line["start"], line["end"]) for line in load_dialogue(path, styles)]


def _mask(spans: list[tuple[float, float]], length: int) -> Any:
    """Draw a list of time spans as a timeline with one cell per 10 milliseconds. Cells that contain
    something are 1."""
    import numpy as np

    grid = np.zeros(length, dtype=np.float64)
    for start, end in spans:
        low = max(0, int(start / STEP))
        high = min(length, int(end / STEP))
        if high > low:
            grid[low:high] = 1.0
    return grid


def find_offset(
    lines: list[tuple[float, float]], speech: list[tuple[float, float]], duration: float
) -> tuple[float, float]:
    """How many seconds the subtitles differ from this episode's audio track. Returns (offset,
    overlap score).

    **Why it must be measured and not written in as a fixed number.** The subtitles were made for
    the video, while the audio track we have was extracted separately, so the difference depends on
    the source. In episode 1 it measured 0.94 seconds. From episode 5 on, the source version
    changed, so the offset is almost certainly different.

    How it is measured: slide the "subtitle is showing" timeline against the "model thinks someone
    is speaking" timeline, and find the shift at which they overlap the most. The overlap score is
    the intersection of the two lines divided by their union, so 1.0 means a perfect match.

    If the overlap score is too low (below `MIN_OVERLAP_RATIO`), the subtitles do not belong to this
    episode. The caller must treat that as an error and not push on with cutting.
    """
    import numpy as np

    length = int((duration + SEARCH_SECONDS) / STEP)
    subtitle = _mask(lines, length)
    spoken = _mask(speech, length)

    # Shift by whole cells, so the offset reported is exactly the shift used for scoring. A rounding
    # difference of one cell cannot creep in.
    best_offset, best_score = 0.0, -1.0
    reach = round(SEARCH_SECONDS / STEP)
    for steps in range(-reach, reach):
        moved = np.roll(subtitle, steps)
        union = float(((moved + spoken) > 0).sum())
        score = float((moved * spoken).sum()) / union if union else 0.0
        if score > best_score:
            best_offset, best_score = steps * STEP, score
    return round(best_offset, 3), round(best_score, 4)


Parts = list[tuple[float, float]]
"""The offset of each part of an episode: (subtitle time the part starts at, offset), in order. The
first part starts at 0. Most episodes have one part."""

PART_REACH = 1.5
"""How many seconds a part's offset may differ from the whole episode's."""
PART_GAP = 1.5
"""A part can only start after a pause of at least this many seconds between lines, such as the
break in the middle of an episode, so no line is split between two parts."""
MIN_PART = 60.0
"""Seconds of subtitles a part must span, so a few lines alone cannot pull an offset their way."""
MIN_PART_GAIN = 0.02
"""Each part after the first must add at least this share of the subtitle time to the overlap."""
MAX_PARTS = 4


def offset_at(parts: Parts, time: float) -> float:
    """The offset for a line that starts at `time` in subtitle time."""
    offset = parts[0][1]
    for start, value in parts:
        if time >= start:
            offset = value
    return offset


def shift_lines(lines: list[tuple[float, float]], parts: Parts) -> list[tuple[float, float]]:
    """Subtitle times to audio-track times."""
    return [(a + offset_at(parts, a), b + offset_at(parts, a)) for a, b in lines]


def episode_parts(episode: dict[str, Any], key: str = "subtitle_offset") -> Parts:
    """The parts recorded in episode.json under `key` + "s"; one part for an episode cut before
    there were parts, or with the offset given by hand."""
    recorded = episode.get(f"{key}s")
    if recorded:
        return [(float(start), float(offset)) for start, offset in recorded]
    return [(0.0, float(episode.get(key) or 0.0))]


def describe_parts(parts: Parts) -> str:
    """Such as "-1.09 seconds; from 12:12, -0.65 seconds"."""

    def clock(t: float) -> str:
        return f"{int(t // 60)}:{int(t % 60):02d}"

    first = say(f"{parts[0][1]:+.2f} 秒", f"{parts[0][1]:+.2f} seconds")
    rest = [
        say(f"{clock(start)} 起 {offset:+.2f} 秒", f"from {clock(start)}, {offset:+.2f} seconds")
        for start, offset in parts[1:]
    ]
    return say("；", "; ").join([first, *rest])


def find_offsets(
    lines: list[tuple[float, float]], speech: list[tuple[float, float]], duration: float
) -> tuple[Parts, float]:
    """Like `find_offset`, but an episode may be split into parts with offsets of their own.
    Returns (parts, overlap score over the whole episode).

    **Why.** Subtitles timed for another release of the video (a TV broadcast, say) can jump in
    the middle: the break between the halves has another length there. In kamigami's season 2 of
    Gochuumon wa Usagi desu ka, 7 of 12 episodes jump by 0.2 to 0.9 seconds around minute 12. One
    offset then fits only one half: the overlap fell below `MIN_OVERLAP_RATIO` in three episodes,
    and in others half the clips were cut that far off.

    How: first the whole episode's offset, as before. Then the lines are split into blocks at
    pauses of `PART_GAP` seconds, and the overlap of each block with speech is worked out for
    every offset within `PART_REACH` of it. The best way to group neighboring blocks into at most
    `MAX_PARTS` parts, each with one offset, is found by trying every grouping in turn (dynamic
    programming). A part is kept only if it spans `MIN_PART` seconds and adds `MIN_PART_GAIN` to
    the overlap, so an episode without a jump stays one part."""
    import numpy as np

    lines = sorted(lines)
    centre, score = find_offset(lines, speech, duration)
    length = int((duration + SEARCH_SECONDS) / STEP)
    spoken = _mask(speech, length)
    reach = round(PART_REACH / STEP)
    blocks: list[list[tuple[float, float]]] = [[lines[0]]]
    for before, line in pairwise(lines):
        if line[0] - before[1] >= PART_GAP:
            blocks.append([])
        blocks[-1].append(line)
    # table[i, j]: cells where block i, moved by centre + (j - reach) cells, meets speech.
    table = np.zeros((len(blocks), 2 * reach + 1))
    padded = np.concatenate([np.zeros(reach), spoken, np.zeros(reach)])
    for i, block in enumerate(blocks):
        low = max(0, int((block[0][0] + centre) / STEP))
        high = min(length, int((block[-1][1] + centre) / STEP) + 1)
        if high <= low:
            continue
        cells = _mask([(a + centre, b + centre) for a, b in block], length)[low:high]
        table[i] = np.correlate(padded[low : high + 2 * reach], cells, mode="valid")
    sums = np.vstack([np.zeros(table.shape[1]), np.cumsum(table, axis=0)])

    def best(first: int, end: int) -> tuple[float, int]:
        """Blocks first..end-1 as one part: its overlap and offset column."""
        row = sums[end] - sums[first]
        column = int(row.argmax())
        return float(row[column]), column

    count = len(blocks)
    # found[(p, end)]: the best grouping of blocks 0..end-1 into p parts: (overlap, part starts).
    found = {(1, end): (best(0, end)[0], [0]) for end in range(1, count + 1)}
    for p in range(2, MAX_PARTS + 1):
        for end in range(2, count + 1):
            choices = [
                (found[(p - 1, first)][0] + best(first, end)[0], [*found[(p - 1, first)][1], first])
                for first in range(1, end)
                if (p - 1, first) in found
                and blocks[end - 1][-1][1] - blocks[first][0][0] >= MIN_PART
            ]
            if choices:
                found[(p, end)] = max(choices, key=lambda c: c[0])
    total = sum(b - a for a, b in lines) / STEP
    chosen = found[(1, count)]
    for p in range(2, MAX_PARTS + 1):
        if (p, count) in found and found[(p, count)][0] - chosen[0] >= MIN_PART_GAIN * total:
            chosen = found[(p, count)]
    starts = chosen[1]
    if len(starts) == 1:
        return [(0.0, centre)], score
    ends = [*starts[1:], count]
    parts = [
        (
            0.0 if first == 0 else blocks[first][0][0],
            round(centre + (best(first, end)[1] - reach) * STEP, 3),
        )
        for first, end in zip(starts, ends, strict=True)
    ]
    moved = _mask(shift_lines(lines, parts), length)
    union = float(((moved + spoken) > 0).sum())
    return parts, round(float((moved * spoken).sum()) / union if union else 0.0, 4)


def subtitle_lines(episode: dict[str, Any]) -> list[tuple[float, float, str]]:
    """The subtitle lines for this episode, with the offset already added and converted to
    audio-track time. They come from the styles recorded when the episode was cut. Episodes cut
    before styles were recorded pick them again, which gives the same lines."""
    from avoc.stages.subtitle import episode_parts, load_dialogue, offset_at
    from avoc.stages.text_subtitle import turn_lines

    path = Path(episode.get("subtitles") or "")
    if not path.is_file():
        return []
    parts = episode_parts(episode)
    styles = episode.get("subtitle_styles")
    if episode.get("segmentation") == "speaker_turns":
        timed = [(x.start, x.end, x.text) for x in turn_lines(path, styles)]
    else:
        timed = [(d["start"], d["end"], d["text"]) for d in load_dialogue(path, styles)]
    return [(a + offset_at(parts, a), b + offset_at(parts, a), text) for a, b, text in timed]
