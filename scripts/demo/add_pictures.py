"""Replace the waveform in the demo episodes with one picture per line (see pictures.json).

Each picture is shown from the start of its line until the next picture's line starts; the first
one from the start of the episode. The sound is copied unchanged, so the episodes need no new
VOICEVOX run. Pictures are 3:2 and cut to 16:9 around their middle. An episode with no folder of
pictures keeps its waveform; the demo has pictures for ep01 only. Run from the repository root:

    uv run python scripts/demo/add_pictures.py data/demo-episodes data/demo-pictures
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
FPS = 24


def starts(srt: Path) -> list[float]:
    """The start of every subtitle, in seconds; make_episodes.py writes one per line."""
    times = []
    for block in srt.read_text(encoding="utf-8").strip().split("\n\n"):
        start = block.split("\n")[1].split(" --> ")[0]
        h, m, rest = start.split(":")
        s, ms = rest.split(",")
        times.append(int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000)
    return times


def duration(video: Path) -> float:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    answer = subprocess.run([*command, str(video)], capture_output=True, text=True, check=True)
    return float(answer.stdout)


def episode(name: str, shots: list, episodes: Path, pictures: Path) -> None:
    video = episodes / f"{name}.mkv"
    times = starts(episodes / f"{name}.ja.srt")
    if len(times) != len(shots):
        raise SystemExit(f"{name}: {len(times)} subtitles but {len(shots)} lines in pictures.json")
    # Each picture starts with the frame that holds its line's start, so the frame shown when the
    # player jumps to the line is already the line's picture, not the one before.
    shown = [
        (math.floor(times[i] * FPS) / FPS, pictures / name / f"{i + 1:02d}.png")
        for i, s in enumerate(shots)
        if s
    ]
    missing = [str(path) for _, path in shown if not path.is_file()]
    if missing:
        raise SystemExit(f"{name}: missing pictures: {', '.join(missing)}")
    shown[0] = (0.0, shown[0][1])
    ends = [start for start, _ in shown[1:]] + [duration(video)]
    with tempfile.TemporaryDirectory() as folder:
        listing = Path(folder) / "pictures.txt"
        rows = [
            f"file '{path.resolve().as_posix()}'\nduration {end - start:.3f}"
            for (start, path), end in zip(shown, ends, strict=True)
        ]
        # The concat format needs the last file once more, or its duration is ignored.
        rows.append(f"file '{shown[-1][1].resolve().as_posix()}'")
        listing.write_text("\n".join(rows), encoding="utf-8")
        made = Path(folder) / video.name
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-i", str(video),
             "-vf", f"scale=1280:-2,crop=1280:720,fps={FPS},format=yuv420p",
             "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "23", "-c:a", "copy",
             "-metadata:s:a:0", "language=jpn", "-shortest", str(made)],
            check=True,
        )  # fmt: skip
        made.replace(video)
    print(f"{video}: {len(shown)} pictures")


def main() -> None:
    episodes, pictures = Path(sys.argv[1]), Path(sys.argv[2])
    plan = json.loads((HERE / "pictures.json").read_text(encoding="utf-8"))
    for name, shots in plan["episodes"].items():
        if not (pictures / name).is_dir():
            print(f"{name}: no pictures folder, so it keeps the waveform")
            continue
        episode(name, shots, episodes, pictures)


if __name__ == "__main__":
    main()
