"""Pairing the videos and subtitles in two folders by episode number, to add several episodes at
once."""

from __future__ import annotations

from pathlib import Path

import pytest

from avoc.app.batch import episode_number, pair


@pytest.mark.parametrize(
    ("name", "number"),
    [
        ("Gochuumon wa Usagi Desu ka 2015 S02E03-[1080p][BDRIP][x265.OPUS].mkv", 3),
        ("[kamigami] Gochuumon wa Usagi Desu ka S2 - 11 [1080p x265 Ma10p AAC][JPN].ass", 11),
        ("[Sakurato] Gochuumon wa Usagi Desu ka？ BLOOM [01][HEVC-10bit 1080p AAC][CHS].ass", 1),
        ("[HaSub][Gochuumon wa Usagi desu ka][12][BDRip][CHT, JPN].ass", 12),
        ("[Group] Show - 07v2 (BD 1080p).mkv", 7),
        ("ご注文はうさぎですか 第05話.srt", 5),
        ("Show EP09 1080p.mp4", 9),
        ("show 4 x264 10bit.mkv", 4),
        ("notes.ass", None),
    ],
)
def test_the_episode_number_is_read_from_the_file_name(name: str, number: int | None) -> None:
    assert episode_number(name) == number


def test_files_are_paired_by_number(tmp_path: Path) -> None:
    videos, subs = tmp_path / "v", tmp_path / "s"
    videos.mkdir()
    subs.mkdir()
    for name in ("Show S01E01 [AV1].mkv", "Show S01E01 [x265].mkv", "Show S01E02.mkv", "a.txt"):
        (videos / name).write_text("x", encoding="utf-8")
    for name in ("[G] Show - 02 [JPN].ass", "[G] Show - 03 [JPN].ass", "fonts.ass"):
        (subs / name).write_text("x", encoding="utf-8")
    # A file picked in the folder stands for the folder.
    found = pair(f'"{videos / "Show S01E02.mkv"}"', str(subs))
    assert [(e["number"], len(e["videos"]), len(e["subtitles"])) for e in found["episodes"]] == [
        (1, 2, 0),
        (2, 1, 1),
        (3, 0, 1),
    ]
    assert found["no_number"] == [str(subs / "fonts.ass")]
    with pytest.raises(ValueError, match="cannot find the subtitle folder"):
        pair(str(videos), str(tmp_path / "nowhere"))
