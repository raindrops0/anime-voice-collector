"""Automatic subtitle alignment check."""

from avoc.stages.subtitle import find_offset


def test_offset_is_measured_not_assumed() -> None:
    """When the subtitles are 1 second early compared with the audio track,
    measure the -1 second offset and shift the subtitles back."""
    speech = [(10.0, 12.0), (20.0, 23.0), (30.0, 31.5)]
    lines = [(a + 1.0, b + 1.0) for a, b in speech]
    offset, overlap = find_offset(lines, speech, 40.0)
    assert abs(offset + 1.0) < 0.05
    assert overlap > 0.9


def test_offset_of_zero_when_already_aligned() -> None:
    """When the subtitles already line up, do not shift them."""
    speech = [(5.0, 8.0), (15.0, 19.0)]
    offset, overlap = find_offset(speech, speech, 30.0)
    assert abs(offset) < 0.05
    assert overlap > 0.95


def test_wrong_subtitles_show_up_as_a_low_overlap() -> None:
    """Subtitles from the wrong episode must show up as a low overlap.
    This is the check that guards against silent misalignment."""
    speech = [(10.0, 12.0), (20.0, 23.0)]
    unrelated = [(40.0, 40.5), (60.0, 60.5)]
    _, overlap = find_offset(unrelated, speech, 90.0)
    assert overlap < 0.6


def episode_speech(until: float, seed: int = 1) -> list[tuple[float, float]]:
    """Lines of 1 to 3 seconds with pauses of 0.3 to 2 seconds, like dialogue."""
    import random

    pick = random.Random(seed)
    spans, t = [], 5.0
    while t < until:
        length = pick.uniform(1.0, 3.0)
        spans.append((round(t, 2), round(t + length, 2)))
        t += length + pick.uniform(0.3, 2.0)
    return spans


def test_a_jump_in_the_middle_gets_a_part_of_its_own() -> None:
    """Subtitles made for another release of the video jump at the break in the middle: here
    0.6 seconds early before it, 0.1 seconds after. One offset fits only one half."""
    from avoc.stages.subtitle import find_offsets, shift_lines

    speech = episode_speech(600.0) + [(a + 610.0, b + 610.0) for a, b in episode_speech(590.0, 2)]
    lines = [(a + 0.6, b + 0.6) if a < 605 else (a + 0.1, b + 0.1) for a, b in speech]
    _, one = find_offset(lines, speech, 1200.0)
    parts, overlap = find_offsets(lines, speech, 1200.0)
    assert [round(o, 2) for _, o in parts] == [-0.6, -0.1]
    assert 600 < parts[1][0] < 616  # The first line after the break.
    assert overlap > 0.95 > one
    assert shift_lines([(700.0, 701.0)], parts) == [(699.9, 700.9)]


def test_no_jump_stays_one_part() -> None:
    from avoc.stages.subtitle import find_offsets

    speech = episode_speech(1200.0)
    parts, overlap = find_offsets([(a - 0.4, b - 0.4) for a, b in speech], speech, 1200.0)
    assert parts == [(0.0, 0.4)]
    assert overlap > 0.95


def test_episodes_cut_before_parts_have_one() -> None:
    from avoc.stages.subtitle import describe_parts, episode_parts

    assert episode_parts({"subtitle_offset": -0.95}) == [(0.0, -0.95)]
    parts = episode_parts(
        {"subtitle_offset": -1.09, "subtitle_offsets": [[0, -1.09], [732, -0.65]]}
    )
    assert parts == [(0.0, -1.09), (732.0, -0.65)]
    assert describe_parts(parts) == "-1.09 seconds; from 12:12, -0.65 seconds"


def test_text_lines_take_each_part_offset(tmp_path) -> None:
    from avoc.workspace import subtitle_lines

    path = tmp_path / "ep.srt"
    path.write_text(
        "1\n00:00:10,000 --> 00:00:11,000\nbefore\n\n2\n00:13:00,000 --> 00:13:01,000\nafter\n",
        encoding="utf-8",
    )
    episode = {"subtitles": str(path), "subtitle_offset": -1.0,
               "subtitle_offsets": [[0, -1.0], [700, -0.5]]}  # fmt: skip
    assert subtitle_lines(episode) == [(9.0, 10.0, "before"), (779.5, 780.5, "after")]
