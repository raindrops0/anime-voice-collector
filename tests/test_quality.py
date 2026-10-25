"""The "low quality" hint's model: training, chances, and the starter weights as a prior."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from avoc.quality import chances, fit, read_starter, save_starter


def _clips(count: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Low clips sit higher on the first feature; the second is noise."""
    rng = np.random.default_rng(seed)
    low = rng.random(count) < 0.3
    x = rng.normal(size=(count, 2))
    x[:, 0] += 3 * low
    return x, low


def test_the_hint_ranks_low_clips_first() -> None:
    x, low = _clips(400, 0)
    model = fit(x, low)
    p = chances(model, x)
    assert p[low].mean() > 0.5 > p[~low].mean() + 0.1


def test_few_labels_stay_close_to_the_starter(tmp_path: Path) -> None:
    x, low = _clips(400, 1)
    starter = fit(x, low)
    save_starter(tmp_path / "starter.npz", starter)
    loaded = read_starter(tmp_path / "starter.npz")
    assert loaded is not None
    np.testing.assert_allclose(loaded.weights, starter.weights, rtol=1e-5)
    # Three clean clips, no low one: alone they say nothing about low quality, but with the starter
    # the hint still points the same way.
    few = fit(x[~low][:3], np.zeros(3, bool), loaded)
    assert few.weights[0] > 0.5 * loaded.weights[0]
    p = chances(few, x)
    assert p[low].mean() > p[~low].mean() + 0.3
