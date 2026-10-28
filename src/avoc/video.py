"""Cut the short video pieces the interface plays next to each line, and make the whole-episode copy
that replaces them once it is ready."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

VIDEO_HEIGHT = 360
"""Height of the exported picture. Tall enough to see who is speaking. Smaller means faster cutting
and loading."""


PICTURE_PAD = 0.0
"""The switch between two ways of playing a line, to compare them. Seconds of picture shown before
and after each line (and its extra context), so the face is on screen before the voice starts. The
vocals are never heard in that time: the page mutes them there. 0 shows only the line itself; 0.5
was used before. The page reads it from the server, so changing it takes only a restart. To see in
the browser's console when the sound starts, is muted and stops, run
`localStorage.setItem("avoc-debug-playback", "1")` there and reload."""


def media_name(kind: str, clip_id: str, context: int = 0, pad: float = 0.0) -> str:
    """Where one line's cut is kept under `app_media/`: the picture, or the vocals as "audio". With
    more context, the seconds are in the name, and so are the picture's extra milliseconds
    (`PICTURE_PAD`). A picture of the line alone ends in ".line": older cuts of the line alone,
    named without it, had half a second more at each end, and are not used."""
    if kind == "audio":
        return f"audio/{clip_id}{f'.ctx{context}' if context else ''}.wav"
    extra = f".pad{round(pad * 1000)}" if pad else ""
    return f"video/{clip_id}.{f'ctx{context}' if context else 'line'}{extra}.mp4"


def cut_video(video: Path, start: float, end: float, out: Path) -> None:
    """Cut a short piece of video with ffmpeg and convert it to H.264 mp4, which browsers can always
    play.

    The source is HEVC, and browser support for it depends on the browser version, so it cannot be
    relied on. So this always transcodes, and also scales the picture down to `VIDEO_HEIGHT`.
    In measurements, a 2-3 second clip is cut in under half a second, so clips are cut on demand
    rather than all in advance.
    `-ss` goes before `-i` for fast seeking. Without this, every cut would decode from the start.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    # The process number keeps two apps open on the same project from writing into one file.
    temporary = out.with_suffix(f".{os.getpid()}.part.mp4")
    command = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.05, end - start):.3f}",
        "-i", str(video),
        "-vf", f"scale=-2:{VIDEO_HEIGHT}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", "-y", str(temporary),
    ]  # fmt: skip
    try:
        subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            f"Video cut failed. Check that ffmpeg is available and the video can be read: {exc}"
        ) from exc
    temporary.replace(out)


COPY_FOLDER = "episode"
"""Under `app_media/`: the whole-episode copy the page plays once it is ready."""
COPY_VERSION = 1
"""Raised when the way the copy is made changes, so old copies are made again."""


def copy_signature(episode: dict[str, Any]) -> dict[str, Any]:
    """What the copy is made from. Sizes and change times stand in for the contents: hashing a
    video of several GB on every check would take too long."""

    def stamp(path: str | None) -> list[Any] | None:
        if not path or not Path(path).is_file():
            return None
        info = Path(path).stat()
        return [str(path), info.st_size, info.st_mtime_ns]

    return {
        "version": COPY_VERSION,
        "height": VIDEO_HEIGHT,
        "video": stamp(episode.get("video")),
        "vocals": stamp(episode.get("vocals")),
        "original": stamp(episode.get("source")),
    }


def copy_ready(directory: Path, episode: dict[str, Any]) -> bool:
    record = directory / "app_media" / COPY_FOLDER / "copy.json"
    try:
        return json.loads(record.read_text(encoding="utf-8")) == copy_signature(episode)
    except (OSError, ValueError):
        return False


def make_copy(directory: Path, episode: dict[str, Any], device: str) -> str:
    """Make the whole-episode copy the page plays instead of one cut per line:

    - `video.mp4`: the picture only, H.264 at `VIDEO_HEIGHT`, with a keyframe every second, so
      jumping to any line starts at once. Not made for an episode with no video.
    - `vocals.m4a` and `original.m4a`: the separated vocals and the audio track the voices were
      taken from, in AAC. The page plays one of them along with the muted picture.

    On an NVIDIA GPU (`device` "cuda") the picture is decoded, scaled and encoded on the GPU, which
    measured 36 seconds for a 24-minute AV1 episode; if that fails (an old driver, a codec the GPU
    cannot decode) it is done on the CPU, 70 seconds. On the CPU, decoding the source is most of
    the time, so a faster encoder setting barely helps. Returns which of the two made the picture.
    """
    folder = directory / "app_media" / COPY_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    signature = copy_signature(episode)
    (folder / "copy.json").unlink(missing_ok=True)
    made = "none"
    if signature["video"]:
        source = str(episode["video"])
        # A keyframe every second, by time, whatever the frame rate.
        keys = ["-force_key_frames", "expr:gte(t,n_forced*1)"]
        gpu = [
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", source,
            "-map", "0:v:0", "-vf", f"scale_cuda=-2:{VIDEO_HEIGHT}:format=nv12",
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "30", *keys,
        ]  # fmt: skip
        # The GPU's H.264 encoder takes only 8-bit pictures, and many sources are 10-bit.
        cpu = [
            "-i", source, "-map", "0:v:0", "-vf", f"scale=-2:{VIDEO_HEIGHT},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", *keys,
        ]  # fmt: skip
        tries = [("gpu", gpu), ("cpu", cpu)] if device == "cuda" else [("cpu", cpu)]
        for name, args in tries:
            try:
                _ffmpeg([*args, "-an", "-sn", "-dn"], folder / "video.mp4")
                made = name
                break
            except ValueError:
                if name == "cpu":
                    raise
    for name in ("vocals", "original"):
        if signature[name]:
            source = str(episode["source" if name == "original" else "vocals"])
            args = ["-i", source, "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
            _ffmpeg(args, folder / f"{name}.m4a")
    (folder / "copy.json").write_text(json.dumps(signature), encoding="utf-8")
    return made


def _ffmpeg(args: list[str], out: Path) -> None:
    temporary = out.with_suffix(f".{os.getpid()}.part{out.suffix}")
    command = ["ffmpeg", "-v", "error", "-nostdin", *args, "-movflags", "+faststart", "-y"]
    try:
        subprocess.run([*command, str(temporary)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Making {out.name} failed: {exc}") from exc
    temporary.replace(out)
