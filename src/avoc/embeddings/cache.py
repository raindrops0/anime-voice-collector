"""Read cached voiceprints and check their input files and clip order."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from avoc.project import cache_dir, cache_signature, load_episode, read_json, validate_name


def load_embeddings(directory: Path, model: str) -> tuple[list[dict[str, Any]], Any]:
    import numpy as np

    validate_name(model)
    cache = cache_dir(directory, model)
    if read_json(cache / "cache.json") != cache_signature(directory, model):
        raise ValueError(f"{directory} voiceprint cache is out of date. Run embed again")
    records = read_json(cache / "metadata.json")
    vectors = np.load(cache / "vectors.npy", allow_pickle=False)
    _, rows = load_episode(directory)
    by_id = {r["id"]: r for r in rows}
    if (
        vectors.ndim != 2
        or len(vectors) != len(records)
        or not np.isfinite(vectors).all()
        or len({r["id"] for r in records}) != len(records)
        or any(by_id.get(r["id"]) != r for r in records)
    ):
        raise ValueError("The voiceprint matrix does not match the clip information")
    if len(vectors) and not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
        raise ValueError("The voiceprints are not unit-length vectors")
    return records, vectors
