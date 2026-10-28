<div align="center">

<h1><img src="https://github.com/user-attachments/assets/6fe2b479-0f71-46ec-b5bc-9142184db72b" height="48" align="center" alt=""> anime-voice-collector</h1>

**English** · [简体中文](README.zh.md)

**Turn anime episodes into a clean voice dataset of one character, ready for GPT-SoVITS or RVC.<br>Label 10 of their lines, and it sorts the rest for you.**

[![CI](https://github.com/raindrops0/anime-voice-collector/actions/workflows/ci.yml/badge.svg)](https://github.com/raindrops0/anime-voice-collector/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform: Windows · Linux/macOS untested](https://img.shields.io/badge/platform-Windows%20%C2%B7%20Linux%2FmacOS%20untested-0078D6.svg)](#platforms)

### [▶ Try it in your browser, no install](https://raindrops0.github.io/avoc-online-demo/)

[What it does](#what-it-does) · [Install](#install) · [Your first episode](#your-first-episode) · [Labeling](#labeling) · [What you get](#what-you-get) · [Questions](#questions) · [Docs](docs/index.md)

<img src="https://github.com/user-attachments/assets/1e34c75d-3abd-4b24-8196-2888de33e0d6" width="800" alt="Demo: name a group of lines as a character, the machine starts guessing the rest, fix a wrong guess, check the character's list, and export">

</div>

## Try it online

The [online demo](https://raindrops0.github.io/avoc-online-demo/) is the real app, with two short made-up Japanese episodes (voiced by VOICEVOX) already processed. Nothing to install, nothing to upload.

1. In **Groups**, tick the lines of one person and press `N` to name them.
2. Label a few more in **Scenes**, and watch the machine start guessing who says the rest.
3. Fix a wrong guess: it retrains in a moment, and its other guesses change with it.

On your first visit, a short walk-through shows you around the screen and has you label a line. Your labels stay only in that visit, and adding episodes and exporting are turned off. The free server sleeps when nobody uses it, so the page may take about a minute to wake it.

## What it does

To train a voice model of one character, you need minutes of that character speaking alone, each clip with its line. By hand, that means scrubbing through every episode. Most tools stop at speaker diarization (grouping lines by which voice they sound like) and leave naming and checking the groups to you.

Here you label a few lines while watching the scene. A small model learns your character, sorts the rest, and **retrains in a few seconds every time you correct it**. You check its work instead of doing all of it.

<img src="https://github.com/user-attachments/assets/c19aeaa2-5064-4783-9bc1-7193e865da50" width="800" alt="Lines from an episode on a timeline, each sorted into a folder by who said it: Mio, Rin or Other">

| | By hand | Grouping by voice (speaker diarization, such as pyannote) | anime-voice-collector |
| --- | --- | --- | --- |
| Which character is it? | You decide every line | You get "speaker 3" and match it to a character yourself, every episode | You label a few lines; it names the rest |
| When it is wrong | You find it on a second pass | You fix it by hand, and it learns nothing | Your fix retrains it, and its other guesses improve |
| Music and sound effects | You remove them separately | You remove them separately | Removed |
| The words of each line | You type or match them | Not included | Taken from the subtitles, in the language spoken |
| Ready to train GPT-SoVITS or RVC | After more work | After more work | Yes, one export |

- 🎬 **One clip per subtitle line,** so no line is lost to a speech detector.
- 🎤 **Voice only:** music and sound effects are removed from every clip.
- 📺 **Label while watching.** The video plays with each line, with more context one key away.
- 🔇 **Spots noisy lines.** Loud background sound or two people at once get a "maybe low quality" hint from your first label on ([how](docs/features/labeling.md#the-maybe-low-quality-hint)).
- ⌨️ **Keyboard first,** and every step can be undone, even an earlier one alone, from the history.
- 🈶 **The words actually said.** The exported text is in the language spoken, even if you read a translation while labeling.

## Install

You need Windows and, for adding episodes, an NVIDIA graphics card. No card? [Add the episodes on Google Colab's free GPU](docs/guide/install.md#without-an-nvidia-graphics-card) and label on your own computer; on the CPU alone, one episode can take hours.

**The easy way:** download `anime-voice-collector-…-windows.zip` from the [Releases page](https://github.com/raindrops0/anime-voice-collector/releases/latest), unzip it to a short path such as `D:\avoc`, and double-click `start.bat`. The first start downloads about 5 GB, all kept in that folder. Where this page says `uv run …`, run it in the window `terminal.bat` opens.

**With git:** install [uv](https://docs.astral.sh/uv/) (it brings the right Python), then:

```bash
git clone https://github.com/raindrops0/anime-voice-collector.git
cd anime-voice-collector
uv sync --locked
```

You also need [FFmpeg](https://ffmpeg.org/); the app's first page installs it in one click. Details, including installing uv, are in [Install](docs/guide/install.md).

## Your first episode

For each episode you need:

- **the video** (`.mkv`, `.mp4`, …);
- **main subtitles** whose lines match the dialogue (`.ass` or `.srt`), best in the language spoken; each line becomes one clip;
- if you like, **secondary subtitles** you can read, such as a translation, shown in small type under each line.

Start the app on a folder of your choice (`start.bat` does this for you):

```bash
uv run avoc app workspace
```

It opens in your browser at the form to add an episode. Pick the files and press Start: it removes the music, cuts the lines and shows its progress. The subtitle offset (how many seconds the subtitles are off from the sound) is measured for you; the form shows the one-time [Hugging Face](https://huggingface.co) steps this needs. Add the next episodes from the episode menu.

## Labeling

You only name the characters you want (the target characters). Everyone else is "Not a target".

| View | Key | What you do there |
| --- | :---: | --- |
| **Groups** | `G` | Start here. Lines that sound like the same person come as a group: tick the lines of one person and pick who it is. |
| **Scenes** | `S` | Every line in order, with the video. `Enter` accepts the machine's guess, a number picks a character, `Q` is "Not a target", `Shift` + number marks a line low quality, `X` sets it aside. |
| **Characters** | `O` | Everything the machine gave one character, least sure first. Fix the wrong ones, confirm the rest with `Shift+Enter`, then check the lines it may have missed. |
| **Export** | `E` | Write the dataset. |

Once a character has 10 confirmed lines and a few others are "Not a target", the machine starts guessing, and every label after that retrains it in a moment. `Z` undoes, `?` lists every key, and the Guide button runs the walk-through again. The full walk-through is [Your first dataset](docs/guide/first-dataset.md).

## What you get

```text
exports/2026-10-24/
├── Teio/
│   ├── ep01_00083.120000_00085.430000.wav
│   └── ...
├── train.list      (GPT-SoVITS only: path|character|language|text)
└── rejected.tsv    (lines left out, and why)
```

Each clip is one line of one character: voice only, mono, at the sample rate of the video, with even loudness. Lines marked low quality are never exported. Export makes one folder per character for RVC, or adds `train.list` with each line's text for GPT-SoVITS.

## Questions

**Can I use translated subtitles?** Yes, but an episode cut from a translation can only be exported as sound (RVC and such), not with text for GPT-SoVITS. A translation you only want to read goes in the secondary subtitles.

**It stopped halfway, for example out of graphics memory.** Add the same episode again. It continues where it stopped.

**Something doesn't work.** Run `uv run avoc doctor`: it checks the graphics card, FFmpeg, the models and free disk space, and says how to fix anything missing. Include its output when you report a problem.

**Can I do it from the command line?** Yes: `uv run avoc add workspace "Episode 01.mkv" --subs "Episode 01.ja.srt"`. See `uv run avoc --help` or [Commands](docs/reference/commands.md).

## Platforms

Tested on Windows 11 with an NVIDIA graphics card (RTX 4060 Laptop). Linux and macOS can be installed but are not tested yet ([roadmap](docs/ROADMAP.md#platforms)); reports are welcome in the issues.

## Docs

The step-by-step guide, what each view does, every command and the words it uses are in [docs/index.md](docs/index.md). To help, see [CONTRIBUTING.md](docs/CONTRIBUTING.md).

## Usage rules

The code is released under the [MIT License](LICENSE). The audio and text you extract with it belong to the rights holders of the original work, and the MIT License does not cover them. Please use this tool only within these rules:

- ✅ Use extracted material for personal research or study.
- ❌ Do not use extracted audio or text, or models trained on them, for any commercial purpose.
- ❌ Do not use extracted voices to pass yourself off as a character or voice actor.

## Acknowledgements

Built on [audio-separator](https://github.com/nomadkaraoke/python-audio-separator), [anime-speaker-embedding](https://github.com/litagin02/anime_speaker_embedding), [ReDimNet](https://github.com/PalabraAI/redimnet2), [pyannote.audio](https://github.com/pyannote/pyannote-audio) and [pysubs2](https://github.com/tkarabela/pysubs2). The demo's voices are made with [VOICEVOX](https://voicevox.hiroshiba.jp/).
