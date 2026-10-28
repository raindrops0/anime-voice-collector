# Install

**English** · [简体中文](install.zh.md)

This page gets the app running on your machine. Next: [make your first dataset](first-dataset.md).

You need Windows. An NVIDIA graphics card is strongly recommended; without one, separating the voices of one episode can take hours. Only adding episodes needs it: you can [add them on a free cloud GPU](#without-an-nvidia-graphics-card) and label on your own computer. Linux and macOS are not tested yet ([platforms](../ROADMAP.md#platforms)).

## The Windows download (easiest)

1. Download `anime-voice-collector-…-windows.zip` from the [Releases page](https://github.com/raindrops0/anime-voice-collector/releases/latest), about 16 MB. It holds the project, `uv.exe`, and two files to double-click.
2. Unzip it to a short path such as `D:\avoc`. Windows refuses file paths longer than 260 characters, and the libraries already use about 170 of them.
3. Double-click `start.bat`. The first start downloads Python and the libraries, about 5 GB; later starts take a few seconds. Keep its window open while you use the app.

What the two files do:

- `start.bat` starts the app on the folder `workspace` inside the download. To open another workspace, drag its folder onto `start.bat`, or run `start.bat D:\my-workspace`. Options after the folder go to `avoc app`, such as `--port 8800`.
- `terminal.bat` opens a command prompt where every `uv run avoc …` command in these docs works as written, such as `uv run avoc doctor`.

Python, the libraries and the downloaded models stay inside the unzipped folder ([how](../../scripts/release/env.bat)), so deleting the folder removes everything; only the Hugging Face token stays in your user folder. To update, unzip the new version over the old folder: your workspace, the libraries and the models stay, and the next start installs only what changed.

## With git

Install [uv](https://docs.astral.sh/uv/), which also installs the right Python. In PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal, so it finds uv, then:

```powershell
git clone https://github.com/raindrops0/anime-voice-collector.git
cd anime-voice-collector
uv sync --locked
uv run avoc doctor
```

## FFmpeg

FFmpeg must be on your `PATH`. On Windows, the app's first page has an "Install it for me in one click" button: it runs [install_ffmpeg.ps1](../../src/avoc/install_ffmpeg.ps1), which installs [Scoop](https://scoop.sh) if you have none and then FFmpeg with it, without administrator rights. avoc can use it at once, without a restart.

To install it yourself, run `scoop install ffmpeg` if you have Scoop, or download the Windows build from [ffmpeg.org](https://ffmpeg.org/download.html), unzip it, and add its `bin` folder to the `PATH` environment variable.

## Check the machine

```powershell
uv run avoc doctor
```

`doctor` lists each item in turn: the operating system, the graphics card, FFmpeg, the voice separation model, the Hugging Face token, and the free disk space.

- "Missing" must be fixed first.
- "Optional" can be left alone; the tool still works.
- "Untested" means a system other than Windows: avoc mostly works there, but it is tested on Windows only.

When you report a problem, include its output.

## Hugging Face token (for automatic timing)

The subtitle offset is how many seconds the subtitle times are off from the sound. The app can measure it for you with a free model from Hugging Face. To allow that, once:

1. Accept the terms on the [model page](https://huggingface.co/pyannote/speaker-diarization-community-1). A Hugging Face account is free.
2. Create a Read token on the [tokens page](https://huggingface.co/settings/tokens).
3. Run `uv run hf auth login` and paste it.

The add form shows these steps when the token is missing. Without a token you can still type the offset yourself. Runtime requirements and model sources are in [TOOLS.md](../TOOLS.md).

## Without an NVIDIA graphics card

Only adding episodes needs the graphics card. [This notebook](https://colab.research.google.com/github/raindrops0/anime-voice-collector/blob/main/scripts/colab/add_episodes.ipynb) adds them on Google Colab's free GPU (a T4) from a folder in your Google Drive; its first cell says what to upload where. Afterwards, download the workspace folder and open it with `avoc app` here. A workspace can be moved to another computer as long as the videos and subtitles are inside it, as the notebook keeps them in `input/`. The notebook runs [add_all.py](../../scripts/colab/add_all.py).
