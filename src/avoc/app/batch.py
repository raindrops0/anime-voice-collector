"""Pair the videos in one folder with the subtitles in another by episode number, so several
episodes can be added at once.

Release groups write the number in many ways: `S02E03`, `[03]`, ` - 03 `, `第03話`. Numbers that
are not the episode, such as the year, `1080p`, `x265` or `10bit`, are left out.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from avoc.language import say

VIDEO_SUFFIXES = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".flv", ".wmv"}
SUBTITLE_SUFFIXES = {".ass", ".ssa", ".srt"}

NUMBER_RULES = [
    re.compile(r"S\d{1,2}\s*E(\d{1,3})(?!\d)", re.IGNORECASE),
    re.compile(r"第\s*(\d{1,3})\s*[話话集回]"),
    re.compile(r"\[(\d{1,3})(?:v\d)?\]", re.IGNORECASE),
    re.compile(r"\s-\s(\d{1,3})(?:v\d)?(?=[\s\[(.]|$)", re.IGNORECASE),
    re.compile(r"(?:EP?|#)\s?(\d{1,3})(?!\d)", re.IGNORECASE),
]
"""Tried in order; the first that matches gives the number."""
LOOSE_NUMBER = re.compile(r"(?<![\dA-Za-z])(\d{1,3})(?![\dA-Za-z])")
"""Last resort: a number of one to three digits standing alone, so `1080p`, `x265` and `10bit`
are not taken."""


def episode_number(file_name: str) -> int | None:
    """The episode number in a file name, or None when there is none."""
    stem = Path(file_name).stem
    for rule in NUMBER_RULES:
        if found := rule.search(stem):
            return int(found.group(1))
    numbers = LOOSE_NUMBER.findall(stem)
    return int(numbers[-1]) if numbers else None


def files_in(text: str, suffixes: set[str], what: str) -> list[Path]:
    """The files of one kind in a folder. A file picked in the folder stands for its folder."""
    from avoc.app.adding import clean_path

    path = clean_path(text)
    folder = path.parent if path.is_file() else path
    if not folder.is_dir():
        raise ValueError(
            say(f"找不到{what}文件夹：{folder}", f"cannot find the {what} folder: {folder}")
        )
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes)


def pair(videos: str, subtitles: str, display_subtitles: str = "") -> dict[str, Any]:
    """Every episode number found in either folder, with the files that carry it. A number can
    have several files, such as two encodes of one episode; the page lets the person narrow them
    down. Files with no number are listed apart."""
    kinds = {
        "videos": files_in(videos, VIDEO_SUFFIXES, say("视频", "video")),
        "subtitles": files_in(subtitles, SUBTITLE_SUFFIXES, say("字幕", "subtitle")),
    }
    if display_subtitles.strip():
        kinds["display_subtitles"] = files_in(
            display_subtitles, SUBTITLE_SUFFIXES, say("辅助字幕", "secondary subtitle")
        )
    episodes: dict[int, dict[str, list[str]]] = {}
    no_number: list[str] = []
    for kind, paths in kinds.items():
        for path in paths:
            number = episode_number(path.name)
            if number is None:
                no_number.append(str(path))
                continue
            entry = episodes.setdefault(number, {k: [] for k in kinds})
            entry[kind].append(str(path))
    return {
        "episodes": [{"number": n, **episodes[n]} for n in sorted(episodes)],
        "no_number": no_number,
    }
