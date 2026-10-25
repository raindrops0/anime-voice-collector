"""Small episode folders shared by the tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from avoc.project import cache_signature, segment_rows, write_json


def _unit(matrix: np.ndarray) -> np.ndarray:
    return (matrix / np.linalg.norm(matrix, axis=1, keepdims=True)).astype(np.float32)


def episode(
    root: Path,
    name: str,
    vectors: np.ndarray,
    spans: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """One episode where every clip has a voiceprint; the directions are given by the caller.
    `spans` are the clips (one per vector; by default 0.9 seconds each, a second apart) and
    `extra` more fields for episode.json."""
    directory = root / name
    directory.mkdir()
    vocals = directory / f"{name}.wav"
    sf.write(vocals, np.zeros(16000), 16000)
    analysis = directory / "analysis.wav"
    analysis.write_bytes(name.encode())
    write_json(
        directory / "episode.json",
        {
            "schema": "episode.v1",
            "name": name,
            "vocals": str(vocals),
            "analysis": str(analysis),
            "source": str(vocals),
            "sample_rate": 16000,
            **(extra or {}),
        },
    )
    if spans is None:
        spans = [{"start": i, "end": i + 0.9} for i in range(len(vectors))]
    rows = segment_rows(name, spans)
    write_json(directory / "segments.json", rows)
    cache = directory / "embeddings/redimnet2-b6"
    cache.mkdir(parents=True)
    np.save(cache / "vectors.npy", _unit(vectors))
    write_json(cache / "metadata.json", rows)
    write_json(cache / "cache.json", cache_signature(directory, "redimnet2-b6"))
    return directory
