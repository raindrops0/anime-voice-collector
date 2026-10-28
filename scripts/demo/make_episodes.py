"""Make the two short episodes of the online demo from script.json.

Each line is read by a VOICEVOX voice, the lines are laid one after another with a little music
under them, and the result is written as a video (a waveform on a plain background) with Japanese
subtitles, ready for `avoc add`. The voices are VOICEVOX's, so the demo must credit them, for
example "VOICEVOX:ずんだもん" (see the voice terms at https://zunko.jp/con_ongen_kiyaku.html).

Needs the VOICEVOX engine running (http://127.0.0.1:50021) and FFmpeg. Run from the repository
root:

    uv run python scripts/demo/make_episodes.py data/demo-episodes
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

ENGINE = "http://127.0.0.1:50021"
RATE = 48000
LEAD_SECONDS = 2.0
OVERLAP_START = 0.3
"""A line marked "+" starts this many seconds after the line before it."""
FONT = "C\\:/Windows/Fonts/meiryo.ttc"
TITLES = {"ep01": "ずんだ喫茶 第1話", "ep02": "ずんだ喫茶 第2話"}


def engine(path: str, body: bytes | None = None, **query: object) -> bytes:
    url = f"{ENGINE}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url, data=body, method="POST" if body is not None or path != "/speakers" else "GET"
    )
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request) as answer:
        return answer.read()


def style_ids() -> dict[tuple[str, str], int]:
    speakers = json.loads(engine("/speakers"))
    return {(s["name"], style["name"]): style["id"] for s in speakers for style in s["styles"]}


def speak(text: str, speaker: int) -> np.ndarray:
    query = json.loads(engine("/audio_query", b"", text=text, speaker=speaker))
    query.update(outputSamplingRate=RATE, prePhonemeLength=0.05, postPhonemeLength=0.08)
    wav = engine("/synthesis", json.dumps(query).encode(), speaker=speaker)
    audio, rate = sf.read(io.BytesIO(wav), dtype="float32")
    assert rate == RATE
    return audio


def music(seconds: float, rng: np.random.Generator) -> np.ndarray:
    """A quiet loop of four soft chords with a plucked note on each beat, and some room noise:
    enough for the music remover to have something to remove."""
    t = np.arange(int(seconds * RATE)) / RATE
    chords = [[220.0, 277.18, 329.63], [196.0, 246.94, 293.66], [174.61, 220.0, 261.63],
              [196.0, 246.94, 329.63]]  # fmt: skip
    bar = 2.4
    out = np.zeros_like(t)
    for i, chord in enumerate(chords):
        on = (np.floor(t / bar) % len(chords)) == i
        for f in chord:
            out += on * 0.05 * np.sin(2 * np.pi * f * t)
    beat = bar / 4
    phase = t % beat
    note = np.array([440.0, 523.25, 659.25, 587.33])[(np.floor(t / beat) % 4).astype(int)]
    out += 0.06 * np.sin(2 * np.pi * note * t) * np.exp(-phase * 6)
    out += rng.normal(0, 0.004, len(t))
    return out.astype(np.float32)


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def episode(name: str, lines: list[list[str]], voices: dict[str, str], out: Path) -> None:
    ids = style_ids()
    rng = np.random.default_rng(len(name) + int(name[-2:]))
    takes, spans = [], []
    clock, last_start = LEAD_SECONDS, LEAD_SECONDS
    for voice, style, text in lines:
        audio = speak(text, ids[(voices[voice.lstrip("+")], style)])
        start = last_start + OVERLAP_START if voice.startswith("+") else clock
        takes.append((start, audio))
        spans.append((start, start + len(audio) / RATE, text))
        last_start = start
        clock = max(clock, start + len(audio) / RATE) + float(rng.uniform(0.35, 1.1))
        print(f"{name} {srt_time(start)} {voices[voice.lstrip('+')]}: {text}")
    total = clock + LEAD_SECONDS
    voice_track = np.zeros(int(total * RATE), dtype=np.float32)
    for start, audio in takes:
        at = int(start * RATE)
        voice_track[at : at + len(audio)] += audio
    mix = voice_track + music(total, rng)
    mix /= max(1.0, float(np.abs(mix).max()) / 0.95)
    sound = out / f"{name}.wav"
    sf.write(sound, mix, RATE)
    (out / f"{name}.ja.srt").write_text(
        "\n".join(
            f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n"
            for i, (a, b, text) in enumerate(spans, 1)
        ),
        encoding="utf-8",
    )
    picture = (
        f"color=c=0x23324a:s=1280x720:r=24:d={total:.2f}[bg];"
        "[0:a]showwaves=s=1280x260:mode=cline:colors=0x9fe3c0:r=24[w];"
        "[bg][w]overlay=0:300,"
        f"drawtext=fontfile='{FONT}':text='{TITLES[name]}':fontcolor=white:fontsize=44:x=60:y=60"
        "[v]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(sound), "-filter_complex", picture,
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "26", "-pix_fmt", "yuv420p",
         "-c:a", "flac", "-metadata:s:a:0", "language=jpn", str(out / f"{name}.mkv")],
        check=True,
    )  # fmt: skip
    sound.unlink()


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    script = json.loads((Path(__file__).parent / "script.json").read_text(encoding="utf-8"))
    for name, lines in script["episodes"].items():
        episode(name, lines, script["voices"], out)


if __name__ == "__main__":
    main()
