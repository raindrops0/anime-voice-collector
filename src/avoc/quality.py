"""The "low quality" hint: how likely a clip is too noisy for a clean dataset (loud background, two
people at once).

**Features.** WavLM-large (a general speech model, from torchaudio) reads each clip of the 16 kHz
separated vocals. For transformer layers 4, 6 and 8, the mean and the spread over time of each
number are kept: 6144 numbers per clip. They are computed once per episode and cached in
`quality/` next to the voiceprints. Clips shorter than the voiceprint minimum get none.

**Model.** One logistic regression for all characters together: clips labeled as a character are
"clean", the ones marked "low quality" are "low". Measured on usagi's 7 characters, pooling all
characters scored 0.914 ranking accuracy, one model per character only 0.815
(`out/quality-probe/FINDINGS.md`).

**Starter weights.** A model trained on other anime (Teio from Uma Musume, the first usagi labels)
is downloaded once. On its own it scored 0.909 on usagi with no usagi labels. With labels, the
weights are trained starting from it and held back toward it (instead of toward zero), so the hint
works from the first label and fits the anime more as labels grow. Without the starter, the hint
waits for `MIN_EACH` clean and low clips.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avoc.project import digest, load_episode, read_json, write_json

LAYERS = (4, 6, 8)
"""WavLM-large transformer layers used. Layers 3 to 8 all did about as well."""

STRENGTH = 0.02
"""Regularization strength (scikit-learn's `C`). Picked offline; 0.002 to 0.2 barely differ."""

MIN_EACH = 10
"""Without starter weights, the hint starts once this many clips are labeled clean and this many
low."""

HINT = 0.5
"""A clip whose chance of being low quality is at least this shows the hint. On usagi (out of fold,
Teio starter and 200 labels), 0.5 caught 83% of the low clips and wrongly flagged 12% of the clean
ones."""

SET_ASIDE = 0.9
"""An unlabeled clip at least this likely to be low quality is moved to the Skipped list. Measured
as for `HINT`: 75% of the low clips caught, 4% of the clean ones wrongly flagged."""

STARTER_REPO = "RainbowZL/avoc-quality-starter"
STARTER_FILE = "quality-starter-v1.npz"
STARTER_SHA256 = "3727ed71ffb1ca90141af2ae2f566d8bb443438340226c606885fc67b987f114"
"""Where the starter weights are downloaded from (Hugging Face), and the file's SHA-256. A new
version gets a new file name, so a cached old file is never taken for it."""

FOLDER = "quality"


@dataclass(frozen=True)
class Starter:
    """Weights in the space of features scaled by `mean` and `scale`."""

    mean: Any
    scale: Any
    weights: Any
    offset: float


def _signature(directory: Path) -> dict[str, str]:
    from avoc.embeddings.extract import MIN_SECONDS

    episode, _ = load_episode(directory)
    return {
        "model": "torchaudio WAVLM_LARGE",
        "layers": ",".join(map(str, LAYERS)),
        "segments_sha256": digest(directory / "segments.json"),
        "analysis_sha256": digest(Path(episode["analysis"])),
        "min_seconds": f"{MIN_SECONDS:.3f}",
    }


def cached(directory: Path) -> bool:
    signature = directory / FOLDER / "cache.json"
    return signature.exists() and read_json(signature) == _signature(directory)


def compute(directory: Path, device: str = "cpu", report: Any = None) -> int:
    """Compute and cache one episode's features. Returns how many clips got them."""
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio

    from avoc.embeddings.extract import MIN_SECONDS

    episode, rows = load_episode(directory)
    audio, rate = sf.read(episode["analysis"], dtype="float32", always_2d=True)
    if rate != 16000:
        raise ValueError(f"{episode['analysis']} is {rate} Hz, not 16000 Hz")
    mono = audio[:, 0]
    model: Any = torchaudio.pipelines.WAVLM_LARGE.get_model().to(device).eval()
    ids, vectors = [], []
    picked = [r for r in rows if r["end"] - r["start"] >= MIN_SECONDS]
    with torch.inference_mode():
        for k, row in enumerate(picked):
            chunk = mono[int(row["start"] * rate) : int(row["end"] * rate)]
            wave = torch.from_numpy(np.ascontiguousarray(chunk))[None].to(device)
            # WavLM-large expects input scaled to mean 0 and spread 1.
            wave = (wave - wave.mean()) / (wave.std() + 1e-7)
            layers, _ = model.extract_features(wave, num_layers=max(LAYERS))
            parts = []
            for layer in LAYERS:
                frames = layers[layer - 1][0]
                parts += [frames.mean(0), frames.std(0)]
            vectors.append(torch.cat(parts).float().cpu().numpy())
            ids.append(row["id"])
            if report and k % 200 == 0:
                report(k, len(picked))
    folder = directory / FOLDER
    folder.mkdir(exist_ok=True)
    width = 2 * 1024 * len(LAYERS)
    matrix = np.array(vectors, dtype=np.float16) if vectors else np.empty((0, width), np.float16)
    np.save(folder / "vectors.npy", matrix)
    write_json(folder / "ids.json", ids)
    write_json(folder / "cache.json", _signature(directory))
    return len(ids)


def load(directory: Path) -> tuple[list[str], Any] | None:
    """One episode's cached clip IDs and features (float16), or None if missing or out of date."""
    import numpy as np

    if not cached(directory):
        return None
    folder = directory / FOLDER
    ids = read_json(folder / "ids.json")
    vectors = np.load(folder / "vectors.npy", allow_pickle=False)
    return (ids, vectors) if len(ids) == len(vectors) else None


def starter_path() -> Path | None:
    """The starter weights file, downloaded once into the Hugging Face cache. None if it cannot be
    downloaded (for example, offline) or does not match its hash; the hint then waits for labels."""
    try:
        from huggingface_hub import hf_hub_download

        path = Path(hf_hub_download(STARTER_REPO, STARTER_FILE))
    except Exception:
        return None
    if hashlib.sha256(path.read_bytes()).hexdigest() != STARTER_SHA256:
        return None
    return path


def read_starter(path: Path | None) -> Starter | None:
    import numpy as np

    if path is None:
        return None
    z = np.load(path, allow_pickle=False)
    return Starter(z["mean"], z["scale"], z["weights"], float(z["offset"]))


def save_starter(path: Path, starter: Starter) -> None:
    import numpy as np

    np.savez(
        path,
        mean=starter.mean.astype(np.float32),
        scale=starter.scale.astype(np.float32),
        weights=starter.weights.astype(np.float32),
        offset=np.float32(starter.offset),
        layers=np.array(LAYERS),
    )


def fit(features: Any, low: Any, starter: Starter | None = None) -> Starter:
    """Train the logistic regression. `low[i]` is True for a low-quality clip. Clean and low clips
    weigh the same in total (as scikit-learn's `class_weight="balanced"`). The weights and the
    offset are held back toward the starter's (or toward zero with no starter) by
    `(|w - w0|**2 + (b - b0)**2) / (2 * STRENGTH)`,
    and the features are scaled as the starter's were (or by these clips with no starter)."""
    import numpy as np
    from scipy.optimize import minimize

    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(low, dtype=np.float64)
    if starter is None:
        mean, scale = x.mean(0), x.std(0)
        scale[scale == 0] = 1.0
        w0, b0 = np.zeros(x.shape[1]), 0.0
    else:
        mean, scale = starter.mean.astype(np.float64), starter.scale.astype(np.float64)
        w0, b0 = starter.weights.astype(np.float64), starter.offset
    z = (x - mean) / scale
    count = len(y)
    weight = np.where(y == 1, count / (2 * max(y.sum(), 1)), count / (2 * max(count - y.sum(), 1)))

    def loss(theta: Any) -> tuple[float, Any]:
        w, b = theta[:-1], theta[-1]
        score = z @ w + b
        # log(1 + e^s) - y*s, written to stay finite for large scores.
        each = np.logaddexp(0, score) - y * score
        p = 1 / (1 + np.exp(-score))
        grad = weight * (p - y)
        # The offset is held back too: with clips of one kind only, it would run off to infinity.
        value = (weight * each).sum() + (((w - w0) ** 2).sum() + (b - b0) ** 2) / (2 * STRENGTH)
        return value, np.append(z.T @ grad + (w - w0) / STRENGTH, grad.sum() + (b - b0) / STRENGTH)

    found = minimize(loss, np.append(w0, b0), jac=True, method="L-BFGS-B", options={"maxiter": 500})
    return Starter(mean, scale, found.x[:-1], float(found.x[-1]))


def chances(model: Starter, features: Any, chunk: int = 2048) -> Any:
    """The chance that each clip is low quality, computed a block at a time to keep memory low."""
    import numpy as np

    w = model.weights / model.scale
    b = model.offset - float(model.mean / model.scale @ model.weights)
    out = np.empty(len(features))
    for at in range(0, len(features), chunk):
        score = np.asarray(features[at : at + chunk], dtype=np.float32) @ w.astype(np.float32) + b
        out[at : at + chunk] = 1 / (1 + np.exp(-score))
    return out
