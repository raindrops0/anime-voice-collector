# Dependencies and runtime environment

Python dependencies and their versions are recorded in `pyproject.toml` and `uv.lock`. Web dependencies and their versions are in `web/package.json` and `web/package-lock.json`. For installation commands, see [Set up](guide/install.md).

## Runtime requirements

Python 3.12 and FFmpeg are required. The app uses downloaded model files, so the first run of a processing step may need an internet connection. Check the download messages and keep enough disk space for models and prepared audio. `avoc doctor` reports missing requirements.

On Windows and Linux, the locked torch and torchaudio packages include CUDA 12.8 support. They also run on the CPU without an NVIDIA GPU. macOS uses packages from PyPI and runs on the CPU. See [platform support](ROADMAP.md#platforms) for what has been tested.

Automatic subtitle timing requires accepting the terms of [pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) and signing in with a Hugging Face Read token. See [adding an episode](guide/install.md#hugging-face-token-for-automatic-timing). When you know the correct timing, `--offset` lets you supply it yourself.

## Model sources

The project uses models from [audio-separator](https://github.com/nomadkaraoke/python-audio-separator), [anime_speaker_embedding](https://github.com/litagin02/anime_speaker_embedding), [ReDimNet2](https://github.com/PalabraAI/redimnet2), [pyannote](https://huggingface.co/pyannote/speaker-diarization-community-1) and [torchaudio](https://docs.pytorch.org/audio/stable/). Check each source's license and terms when using or redistributing model files.

## Development tools

The local server uses FastAPI and uvicorn. The web app uses React, TypeScript, Vite, Tailwind CSS and shadcn/ui on Base UI. Built web files are included, so users do not need Node to run the app.

People changing the web app need Node. Ruff, ty and pytest check Python changes; oxlint, Prettier, Vitest and Playwright check web changes. Setup and check commands are in [CONTRIBUTING.md](CONTRIBUTING.md).
