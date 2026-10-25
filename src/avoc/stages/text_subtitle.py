"""Give each clip its text in the language spoken, from the main subtitles it was cut from. When
they are in that language alone, each clip is one person's part of an entry (see `turn_lines`), and
its text is that part. Bilingual ones work too: only their lines in the spoken language are used,
matched to each clip by time, and a clip whose line cannot be found in full is not exported, with
the reason recorded.

Several lines in one subtitle entry are often two people each saying one sentence. So the entry is
split into lines, and its time is shared among the lines by character count. Speaker names, sound
notes and other marks are removed by the rules in captions.py. A speaker name, where the subtitles
give one, is used to spot other people's lines that got mixed in.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avoc.language import say
from avoc.stages.captions import MISSING

MIN_AGREEMENT = 0.6
"""After matching, the two subtitle files must agree on display times (overlap divided by union) by
at least this much. Otherwise they probably are not the subtitles for this episode.

In episodes 1 to 3, the four sources of Japanese subtitles scored between 0.67 and 0.78 against the
Chinese subtitles. A wrong match to the next episode scored only about 0.50."""

TOUCH = 0.1
"""A line counts as touching a clip only if they overlap by more than this many seconds."""

INSIDE = 0.7
"""At least this share of each touching line must fall inside the clip."""

SPARE = 0.8
"""Subtitles often stay on screen a little longer than the speech. If a line sticks out past the
clip at either end by less than this many seconds, the whole line still counts as inside."""

COVER = 0.5
"""The touching lines together must cover at least this share of the clip. Otherwise part of the
clip has no text."""

MIXED = 0.2
"""A line tagged with someone else's name that overlaps the clip by more than this many seconds
means someone else's speech is mixed into the clip."""

OWN_TAG_SHARE = 0.5
"""For a character's clips, one name must make up at least this share of the named lines they
touch. Only then is that name accepted as the character's name in the subtitles."""


@dataclass(frozen=True)
class TextLine:
    start: float
    end: float
    text: str
    speaker: str
    """The name in the speaker tag at the start of the line. Empty if there is none."""


def _entries(
    path: Path, styles: list[str] | None, subs: Any = None
) -> list[tuple[Any, list[tuple[str, str]]]]:
    """Each subtitle entry with its lines of spoken words, as (entry, [(words, speaker)]). With
    `styles`, only the dialogue lines of those styles, as clips are cut from them; without, every
    entry with text. `subs` is the file already read, if it is."""
    from avoc.stages.captions import spoken_lines
    from avoc.stages.subtitle import read_subtitles, usable

    found = []
    for event in read_subtitles(path) if subs is None else subs:
        if event.end <= event.start or not event.is_text:  # Comments and drawings have no lines.
            continue
        if styles is not None and not (event.style in styles and usable(event)):
            continue
        if parts := spoken_lines(event.plaintext):
            found.append((event, parts))
    return found


def _languages(entries: list[tuple[Any, list[tuple[str, str]]]]) -> list[list[str | None]]:
    from avoc.stages.text_language import line_languages

    return line_languages((e.style, [text for text, _ in parts]) for e, parts in entries)


def subtitle_languages(path: Path, styles: list[str] | None = None) -> dict[str, float]:
    """The languages of a subtitle file's lines, with their shares, most first. A bilingual file
    has two. See stages/text_language.py."""
    from avoc.stages.text_language import file_languages

    return file_languages(code for codes in _languages(_entries(path, styles)) for code in codes)


def style_languages(path: Path, styles: list[str] | None = None) -> dict[str, str]:
    """The language most of each style's lines are in. A bilingual file that keeps each language in
    its own style has one style per language; reading text aloud cuts clips only from the one in the
    language spoken. A style with no letters in any line is left out."""
    entries = _entries(path, styles)
    counts: dict[str, Counter[str]] = {}
    for (event, _), codes in zip(entries, _languages(entries), strict=True):
        counts.setdefault(event.style, Counter()).update(code for code in codes if code)
    return {style: found.most_common(1)[0][0] for style, found in counts.items() if found}


def spoken_styles(path: Path, styles: list[str], spoken: str) -> list[str]:
    """Of the dialogue `styles`, the ones to cut clips from: in a bilingual file that keeps each
    language in its own style, only the style in the language spoken. Then the file counts as being
    in the spoken language alone, and is cut one person at a time (see `turn_lines`). A style whose
    language is not known stays. If no style is in the language spoken, all stay."""
    found = style_languages(path, styles)
    kept = [s for s in styles if found.get(s, spoken) == spoken]
    return kept or styles


def translation_styles(path: Path, styles: list[str], spoken: str) -> list[str]:
    """Of the dialogue `styles` of secondary subtitles, the ones to show while labeling: in a
    bilingual file that keeps each language in its own style, only the translation, since the
    spoken language is already shown from the main subtitles. If every style is in the language
    spoken, all stay."""
    found = style_languages(path, styles)
    kept = [s for s in styles if found.get(s) != spoken]
    return kept or styles


def load_text_lines(
    path: Path, styles: list[str] | None = None, spoken: str | None = None
) -> list[TextLine]:
    """Read an ASS or SRT file, split it into lines of spoken words, and sort by time. The times
    are the subtitle file's own.

    With `spoken`, only the lines in that language are kept, so the Chinese half of a bilingual
    file is dropped. An entry's time is shared, by character count, among the lines kept.
    `styles` works as in `_entries`."""
    entries = _entries(path, styles)
    languages = _languages(entries) if spoken else [[None] * len(p) for _, p in entries]
    lines: list[TextLine] = []
    for (event, parts), codes in zip(entries, languages, strict=True):
        kept = [part for part, code in zip(parts, codes, strict=True) if code == spoken]
        total = sum(len(text) for text, _ in kept)
        at, span = event.start / 1000.0, (event.end - event.start) / 1000.0
        for text, speaker in kept:
            length = span * len(text) / total
            lines.append(TextLine(at, at + length, text, speaker))
            at += length
    return sorted(lines, key=lambda line: (line.start, line.end))


SAME_ENTRY_GAP = 0.05
"""Two entries with the same text, the second starting at most this many seconds after the first
ends, are one entry. Some subtitles break an entry wherever another entry starts or ends on screen,
so one line shows up as several entries in a row."""


COLOR_TAG = re.compile(r"\\1?c&H([0-9A-Fa-f]{1,8})&?")
"""A text color in an ASS line: \\c&HBBGGRR& or \\1c&HBBGGRR&; some TV caption files leave out
the last & and add a leading 00. SRT font colors are turned into the same tag when the file is
read."""

SCALE_TAG = re.compile(r"\\fsc([xy])([\d.]+)")

KANA = re.compile(r"[ぁ-ゖァ-ヺー]+")


READING_SIZE = 60.0
"""Readings in TV captions are drawn at half width and height (\\fscx50\\fscy50). Fansub groups
draw some spoken lines a little smaller, at 70% to 95%, for a whisper or a voice far away."""


def reading_row(event: Any) -> bool:
    """Whether a subtitle line is only how the words of another line are read: kana alone, drawn at
    most `READING_SIZE` percent wide and high from its first character. TV captions put such
    readings on their own line above the words, as in ぶいん over 部員."""
    if not KANA.fullmatch(event.plaintext.strip()):
        return False
    head = event.text.split("}", 1)[0] if event.text.startswith("{") else ""
    if "\\fsc" in event.text[len(head) + 1 :]:
        return False  # The size changes later in the line, so not all of it is small.
    scale = {axis: float(value) for axis, value in SCALE_TAG.findall(head)}
    return scale.get("x", 100) <= READING_SIZE and scale.get("y", 100) <= READING_SIZE


def main_color(event: Any, default: str) -> str:
    """The color, as BBGGRR, that most visible characters of a subtitle line are drawn in.
    `default` is the line style's own color. A color on a single word or a space does not count."""
    counts: Counter[str] = Counter()
    color = default
    for piece in re.split(r"(\{[^}]*\})", re.sub(r"\\[Nnh]", "", event.text)):
        if piece.startswith("{"):
            for found in COLOR_TAG.findall(piece):
                color = found.lower().zfill(6)[-6:]
        else:
            counts[color] += sum(not c.isspace() for c in piece)
    return counts.most_common(1)[0][0] if counts else default


def _style_color(subs: Any, style: str) -> str:
    found = subs.styles.get(style)
    if found is None:
        return "ffffff"
    c = found.primarycolor
    return f"{c.b:02x}{c.g:02x}{c.r:02x}"


def _shown_together(path: Path, styles: list[str] | None) -> list[tuple[float, float, list[str]]]:
    """The dialogue entries, each as its parts of one text color, with rows on their own lines.

    Done in three steps. Readings on their own line (see `reading_row`) are dropped. One line
    broken into entries in a row is joined back (see `SAME_ENTRY_GAP`). Then the lines that share
    both times become one entry: TV captions keep each row on screen as its own line, so one
    sentence wrapped onto two rows, or two people shown at once, come as two lines with the same
    times. Their rows stay in file order, which is their order on screen. A change of text color
    starts a new person: TV captions give each main character a color, while a wrapped sentence
    keeps its color."""
    from avoc.stages.subtitle import read_subtitles

    subs = read_subtitles(path)
    events = [e for e, _ in _entries(path, styles, subs)]
    times = Counter((e.start, e.end) for e in events if not reading_row(e))
    events = [e for e in events if not (reading_row(e) and times[(e.start, e.end)])]
    rows: list[list[Any]] = []  # [start, end, text, color, place in file]
    last: dict[str, list[Any]] = {}
    for place, event in sorted(enumerate(events), key=lambda item: (item[1].start, item[1].end)):
        start, end, text = event.start / 1000.0, event.end / 1000.0, event.plaintext
        before = last.get(text)
        if before is not None and start <= before[1] + SAME_ENTRY_GAP:
            before[1] = max(before[1], end)
            continue
        color = main_color(event, _style_color(subs, event.style))
        last[text] = [start, end, text, color, place]
        rows.append(last[text])
    groups: dict[tuple[float, float], list[list[Any]]] = {}
    for row in rows:
        groups.setdefault((row[0], row[1]), []).append(row)
    found = []
    for (start, end), shown in sorted(groups.items(), key=lambda item: item[0]):
        parts: list[str] = []
        color = None
        for _, _, text, now, _ in sorted(shown, key=lambda row: row[4]):
            if parts and now == color:
                parts[-1] += "\n" + text
            else:
                parts.append(text)
            color = now
        found.append((start, end, parts))
    return found


def turn_lines(path: Path, styles: list[str] | None = None) -> list[TextLine]:
    """The lines of subtitles in the language spoken, one for each person in each entry, sorted by
    time. Clips are cut from them when the subtitles are in the spoken language; see
    `speaker_turns` in captions.py for where an entry is split, and `_shown_together` for lines
    shown at the same time. An entry's time is shared among its people by character count, as in
    `load_text_lines`. The times are the subtitle file's own."""
    from avoc.stages.captions import speaker_turns

    lines: list[TextLine] = []
    for start, end, parts in _shown_together(path, styles):
        turns = [turn for part in parts for turn in speaker_turns(part)]
        total = sum(len(words) for turn in turns for words, _ in turn)
        at = start
        for turn in turns:
            length = (end - start) * sum(len(words) for words, _ in turn) / total
            speaker = next((name for _, name in turn if name), "")
            lines.append(TextLine(at, at + length, " ".join(w for w, _ in turn), speaker))
            at += length
    return sorted(lines, key=lambda line: (line.start, line.end))


def shifted(lines: list[TextLine], parts: list[tuple[float, float]]) -> list[TextLine]:
    """Subtitle times to audio-track times, with each part's offset (see `find_offsets`)."""
    from avoc.stages.subtitle import offset_at

    return [
        TextLine(x.start + offset_at(parts, x.start), x.end + offset_at(parts, x.start), x.text,
                 x.speaker)
        for x in lines
    ]  # fmt: skip


def _shared(line: TextLine, start: float, end: float) -> float:
    return min(line.end, end) - max(line.start, start)


def touching(lines: list[TextLine], start: float, end: float) -> list[TextLine]:
    return [x for x in lines if _shared(x, start, end) > TOUCH]


def own_tag(hits: Iterable[TextLine]) -> str | None:
    """The name this character has in the subtitles. `hits` are the lines touched by all of this
    character's clips. If the most common name among the named lines makes up less than
    `OWN_TAG_SHARE`, the result is None."""
    tags = Counter(x.speaker for x in hits)
    tags.pop("", None)
    if not tags:
        return None
    name, count = tags.most_common(1)[0]
    return name if count >= OWN_TAG_SHARE * sum(tags.values()) else None


def same_name(a: str, b: str) -> bool:
    """Whether two speaker names are the same person. Subtitles often give the full name once and
    a short one after: トウカイテイオー and テイオー. テイオーたち is other people too."""
    return a.endswith(b) or b.endswith(a)


def match(
    lines: list[TextLine], start: float, end: float, tag: str | None = None
) -> tuple[str, str | None]:
    """The clip's dialogue text, and the reason it is not accepted. A reason of None means it
    matched.

    `tag` is this character's name in the subtitles (see `own_tag`). When it is known, lines tagged
    with another name are someone else's speech. When it is not known, lines count as someone
    else's only if the touched lines carry two or more different names.
    """
    return match_hits(touching(lines, start, end), start, end, tag)


def match_hits(
    hits: Sequence[TextLine], start: float, end: float, tag: str | None = None
) -> tuple[str, str | None]:
    """`match`, given the lines that touch the clip (see `touching`)."""
    named = {x.speaker for x in hits if x.speaker}
    others = [x for x in hits if x.speaker and not same_name(x.speaker, tag)] if tag else []
    if any(_shared(x, start, end) > MIXED for x in others) or (not tag and len(named) > 1):
        return "", say("台词里有别人的话", "someone else's line is mixed in")
    hits = [x for x in hits if x not in others]
    texts: list[str] = []
    for x in hits:
        if x.text not in texts:  # The same line is often shown twice.
            texts.append(x.text)
    text = " ".join(texts)
    if not hits:
        return "", say("没有对上的台词", "no matching line")
    if MISSING in text:
        return text, say(
            "台词里有字幕显示不出的字（〓）",
            "the line has a character the subtitles cannot show (〓)",
        )
    for x in hits:
        inside = _shared(x, start, end) / (x.end - x.start)
        if inside < INSIDE and max(start - x.start, x.end - end) > SPARE:
            return text, say("有一行台词只对上一部分", "a line only partly matches")
    covered = sum(_shared(x, start, end) for x in hits) / (end - start)
    if covered < COVER:
        return text, say("台词只盖住片段一小部分", "the lines cover only a small part of the clip")
    return text, None
