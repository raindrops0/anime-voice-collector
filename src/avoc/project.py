"""Current data format: one description file and one clip table per episode. The cache is checked
against the input content."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def resolve_device(device: str) -> str:
    """`auto` uses `cuda` if there is an NVIDIA GPU, otherwise `cpu`. Other values are returned as
    they are."""
    if device != "auto":
        return device
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def time_key(row: dict[str, Any]) -> tuple[float, float]:
    return round(float(row["start"]), 3), round(float(row["end"]), 3)


def validate_name(name: str) -> str:
    from avoc.language import say

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError(
            say(
                f"集名只能用英文字母、数字、下划线和连字符，开头不能是符号：{name}",
                "Episode name may only contain English letters, digits, underscores and hyphens, "
                f"and must start with a letter or digit: {name}",
            )
        )
    return name


def line_key(row: dict[str, Any]) -> tuple[float, float]:
    """The subtitle time of a clip: `line_start` and `line_end`, or for clips cut before edges were
    tightened, its own time."""
    return (
        round(float(row.get("line_start", row["start"])), 3),
        round(float(row.get("line_end", row["end"])), 3),
    )


def segment_rows(episode: str, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clips are not filtered by audio quality. `start` and `end` are the part with voice (see
    stages/trim.py); `line_start` and `line_end`, when given, are the subtitle line it was cut from.
    The ID is tied to the episode name and the subtitle time, so reordering or regrouping does not
    change it, and neither does tightening the edges another way."""
    validate_name(episode)
    rows = []
    seen = set()
    order = sorted(spans, key=lambda r: (float(r["start"]), float(r["end"]), line_key(r)))
    for row in order:
        start, end = float(row["start"]), float(row["end"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError("Clip times must be finite, and 0 <= start < end")
        key = line_key(row)
        if not (math.isfinite(key[0]) and math.isfinite(key[1])):
            raise ValueError("Clip subtitle times must be finite")
        if not key[0] <= round(start, 3) < round(end, 3) <= key[1]:
            raise ValueError("A clip must lie inside its subtitle line")
        if key in seen:
            raise ValueError("Clip has a duplicate time range (in milliseconds)")
        seen.add(key)
        identity = f"{episode}:{key[0]:.3f}:{key[1]:.3f}"
        out = {
            "id": hashlib.sha256(identity.encode()).hexdigest()[:20],
            "episode": episode,
            "start": start,
            "end": end,
        }
        if "line_start" in row or "line_end" in row:
            out["line_start"] = float(row.get("line_start", start))
            out["line_end"] = float(row.get("line_end", end))
        rows.append(out)
    return rows


EPISODE_PATHS = ("source", "video", "vocals", "analysis", "subtitles", "display_subtitles")
"""The keys in `episode.json` that name a file. A file inside the workspace is written relative to
the episode's folder, so the workspace still works after being moved to another computer, such as
after adding episodes on a cloud GPU (scripts/colab/). Other files are written as full paths."""


def read_episode(directory: Path) -> dict[str, Any]:
    """`episode.json`, with every file path made a full path again."""
    episode = read_json(directory / "episode.json")
    here = directory.resolve()
    for key in EPISODE_PATHS:
        if episode.get(key):
            # Not resolve(): that would follow the links the online demo makes (app/demo.py).
            episode[key] = os.path.normpath(here / episode[key])
    return episode


def save_episode(directory: Path, episode: dict[str, Any]) -> None:
    here = directory.resolve()
    workspace = here.parent.parent
    saved = dict(episode)
    for key in EPISODE_PATHS:
        if saved.get(key):
            path = Path(os.path.normpath(here / saved[key]))
            inside = path.is_relative_to(workspace)
            saved[key] = Path(os.path.relpath(path, here)).as_posix() if inside else str(path)
    write_json(directory / "episode.json", saved)


def load_episode(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    episode = read_episode(directory)
    if episode.get("schema") != "episode.v1":
        raise ValueError(f"Not a current episode directory: {directory}")
    validate_name(episode["name"])
    rows = read_json(directory / "segments.json")
    if segment_rows(episode["name"], rows) != rows:
        raise ValueError(f"{directory}: clip IDs, episode name, or order do not match")
    return episode, rows


def cache_signature(directory: Path, model: str) -> dict[str, str]:
    """Fingerprint of the voiceprint cache. If any of these items changes, the old cache must be
    thrown away and recomputed.

    The minimum duration must also be recorded, because it decides which clips get a voiceprint.
    Without this item, after raising the minimum, the old cache would still pass the check, grouping
    would keep using short clips that should have been dropped, and there would be no error.
    """
    from avoc.embeddings.extract import MIN_SECONDS

    episode, _ = load_episode(directory)
    signature = {
        "model": model,
        "segments_sha256": digest(directory / "segments.json"),
        "analysis_sha256": digest(Path(episode["analysis"])),
        "min_seconds": f"{MIN_SECONDS:.3f}",
    }
    return signature


def cache_dir(directory: Path, model: str) -> Path:
    validate_name(model)
    return directory / "embeddings" / model


def episode_dirs(root: Path) -> list[Path]:
    folder = root / "episodes"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if (p / "episode.json").exists())


def free_export_folder(root: Path) -> Path:
    """Where an export goes unless the person picks another folder: exports/<today> in the
    workspace, or <today>-2 and so on when that one already holds an export."""
    base = root.resolve() / "exports" / time.strftime("%Y-%m-%d")
    folder, number = base, 1
    while folder.exists() and any(folder.iterdir()):
        number += 1
        folder = base.with_name(f"{base.name}-{number}")
    return folder
