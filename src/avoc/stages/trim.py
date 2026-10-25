"""Tighten each clip to the voice inside its subtitle line.

Subtitles come on a little before the speech and stay a little after it. Measured on the 13
episodes cut from Netflix subtitles (6,201 clips), the silence at the two ends of a clip was 0.18
seconds at the median, more than 0.5 seconds in 22% of clips, and 13.8% of all clip time. Played one
after another, the lines sounded broken up, and the silence also went into voiceprints and exports.

**Only the loudness of the separated vocals is used, no model, and no clip is dropped or split.**
Cutting by a speech detection model was ruled out (see docs/DECISIONS.md). Here the subtitle line
still decides that there is a clip; the loudness only moves its two ends inward.
The voice ran past the subtitle line in only 1.3% of clips at the start and 2.3% at the end, so the
ends are never moved outward.
"""

from __future__ import annotations

from typing import Any

FRAME = 0.01
"""Loudness is measured over frames of this many seconds."""

BELOW_PEAK = 30.0
"""A frame has voice when it is within this many decibels of the loud part of the clip (its 95th
percentile frame). 30 dB below is a thousandth of the energy."""

FLOOR = -50.0
"""A frame quieter than this, in dBFS (decibels relative to the loudest possible sound), never has
voice, however quiet the clip."""

KEEP_BEFORE = 0.15
"""Seconds kept before the first frame with voice: a soft first sound, such as a breath or an "s",
can be quieter than the bar."""

KEEP_AFTER = 0.2
"""Seconds kept after the last frame with voice, for a fading last sound."""

BURST = 0.1
BURST_BELOW = 10.0
"""A run of frames with voice at either end, shorter than `BURST` seconds and more than
`BURST_BELOW` decibels quieter than the loud part of the clip, and further from the next run than
`KEEP_BEFORE` (or `KEEP_AFTER`), is a click or a breath, not the line: it does not hold that end. A
run closer than that may be a soft first or last sound, and falls inside the kept part anyway. Short
runs as loud as the rest are kept, because they are mostly short
words: of the short runs that stand apart at the ends of the 13 Amazon-cut episodes, those under
0.05 seconds peaked 16 dB below the loud part at the median, those up to 0.1 seconds only 4 dB
below. With both conditions, 77 of 5,927 clips get shorter, by 18 seconds in all."""


def voice_span(audio: Any, sample_rate: int, start: float, end: float) -> tuple[float, float]:
    """The part of `start`..`end` that has voice, with `KEEP_BEFORE` and `KEEP_AFTER` around it,
    never outside `start`..`end`. Unchanged when no frame has voice or the clip is too short to
    measure. `audio` is the mono vocal track."""
    import numpy as np

    hop = max(1, int(FRAME * sample_rate))
    chunk = audio[int(start * sample_rate) : int(end * sample_rate)]
    frames = len(chunk) // hop
    if frames < 10:
        return start, end
    energy = (chunk[: frames * hop].reshape(frames, hop).astype(np.float64) ** 2).mean(axis=1)
    level = 10 * np.log10(energy + 1e-18)
    loud = float(np.percentile(level, 95))
    bar = max(loud - BELOW_PEAK, FLOOR)
    voiced = level > bar
    if not voiced.any():
        return start, end
    edges = np.flatnonzero(np.diff(np.concatenate([[False], voiced, [False]]).astype(np.int8)))
    runs = list(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))

    def burst(run: tuple[int, int], gap: int, keep: float) -> bool:
        low, high = run
        return (
            (high - low) * FRAME < BURST
            and level[low:high].max() < loud - BURST_BELOW
            and gap * FRAME > keep
        )

    while len(runs) > 1 and burst(runs[0], runs[1][0] - runs[0][1], KEEP_BEFORE):
        runs.pop(0)
    while len(runs) > 1 and burst(runs[-1], runs[-1][0] - runs[-2][1], KEEP_AFTER):
        runs.pop()
    first = start + runs[0][0] * hop / sample_rate
    last = start + runs[-1][1] * hop / sample_rate
    return max(start, first - KEEP_BEFORE), min(end, last + KEEP_AFTER)
