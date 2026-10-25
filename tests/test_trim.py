import numpy as np
import pytest

from avoc.stages.trim import KEEP_AFTER, KEEP_BEFORE, voice_span

RATE = 16000


def track(*parts: tuple[float, float, float]) -> np.ndarray:
    """Two seconds of silence with a tone from `start` to `end` seconds at each `loudness`."""
    samples = np.zeros(RATE * 2)
    for start, end, loudness in parts:
        a, b = int(start * RATE), int(end * RATE)
        samples[a:b] = np.sin(np.arange(b - a) * 0.3) * loudness
    return samples


def test_the_ends_move_in_to_the_voice() -> None:
    start, end = voice_span(track((0.8, 1.4, 0.1)), RATE, 0.0, 2.0)
    assert start == pytest.approx(0.8 - KEEP_BEFORE)
    assert end == pytest.approx(1.4 + KEEP_AFTER)


def test_a_short_quiet_burst_apart_from_the_voice_does_not_hold_an_end() -> None:
    # A 40 ms click 20 dB below the voice, 0.3 seconds before it and 0.4 seconds after it.
    audio = track((0.4, 0.44, 0.01), (0.8, 1.4, 0.1), (1.8, 1.84, 0.01))
    start, end = voice_span(audio, RATE, 0.0, 2.0)
    assert start == pytest.approx(0.8 - KEEP_BEFORE)
    assert end == pytest.approx(1.4 + KEEP_AFTER)


def test_a_short_loud_sound_is_a_word_and_holds_the_end() -> None:
    start, _ = voice_span(track((0.4, 0.44, 0.1), (0.8, 1.4, 0.1)), RATE, 0.0, 2.0)
    assert start == pytest.approx(0.4 - KEEP_BEFORE)


def test_a_quiet_sound_right_before_the_voice_is_kept() -> None:
    start, _ = voice_span(track((0.6, 0.64, 0.01), (0.7, 1.4, 0.1)), RATE, 0.0, 2.0)
    assert start == pytest.approx(0.6 - KEEP_BEFORE)
