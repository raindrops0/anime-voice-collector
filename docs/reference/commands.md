# Commands

Every `avoc` command is listed here. `uv run avoc --help` lists the commands, and `uv run avoc <command> --help` lists the options of one command. In the Windows download, run them in the window `terminal.bat` opens ([Install](../guide/install.md)). For the meaning of terms such as offset and style, see the [glossary](../HOW_IT_WORKS.md#glossary).

| Command | What it does |
| --- | --- |
| [`doctor`](#doctor) | Check the machine |
| [`app`](#app) | Open the labeling app |
| [`add`](#add) | Add one episode |
| [`styles`](#styles) | Show the styles in a subtitle file |
| [`prepare`, `embed`, `quality`](#one-step-at-a-time) | The steps of `add`, one at a time |
| [`set-video`, `set-subtitles`, `set-display-subtitles`, `set-spoken-language`](#filling-in-older-episodes) | Fill in or correct an episode |
| `workspace` | Read and change a workspace with JSON; see [Scripts and agents](agents.md) |

## doctor

```powershell
uv run avoc doctor
```

Checks the operating system, the graphics card, FFmpeg, the voice separation model, the Hugging Face token and the free disk space ([what the results mean](../guide/install.md#check-the-machine)).

## app

```powershell
uv run avoc app workspace
```

Opens the app on a workspace folder at `http://127.0.0.1:8765`. The workspace's `episodes/` subfolder holds the episodes, and labels are saved automatically in `labels/` ([data files](../HOW_IT_WORKS.md#data-files)).

- If port 8765 is in use, the next free port is taken and printed. `--port` sets the port; then only that port is tried.
- If the same workspace is already open, nothing new is started: the command prints that server's address, process ID, start command and start time, opens its page and ends.
- `--no-open` stops the browser from opening by itself.
- `--model` can be repeated, to use only the named voiceprint models.
- `--reload` is for development: it restarts the server when a Python file of avoc changes ([CONTRIBUTING.md](../CONTRIBUTING.md#web-app)).

Episodes whose voiceprints are not all computed, usually because `add` was interrupted, are not loaded. They are listed on the command line at startup, and the other episodes work as usual.

## add

```powershell
uv run avoc add workspace "Episode 08.mkv" --subs "Episode 08.ja.srt" --display-subs "Episode 08.zh.ass" --offset -0.95
```

Adds one episode: extracts the audio track, separates the voices, cuts one clip per subtitle line, and computes the three voiceprints the app needs. The app's add form runs the same command ([adding episodes](../features/adding-episodes.md), which also says which subtitles to give).

| Option | Meaning |
| --- | --- |
| `--subs` | Main subtitles, which the episode is cut from. Required, with the video. Best in the spoken language |
| `--display-subs` | Secondary subtitles, only shown while labeling |
| `--name` | Episode name. Left out, it is the next unused `epNN` |
| `--offset` | One timing offset for the whole episode, in seconds. Left out, it is measured, which needs the [Hugging Face token](../guide/install.md#hugging-face-token-for-automatic-timing); without one, `add` reports the error before processing starts |
| `--styles` | The dialogue styles, such as `"Default,Default - Top"`. Left out, they are picked automatically, and `add` prints the ones it used and left out |
| `--spoken` | The language the voices speak: `ja`, `zh`, `en` or `ko`. The voices are taken from the audio track tagged with it, and exported text must be in it. Left out, a Japanese track is used if the video has one, else the default track; the language comes from the track's tag, and with no tag Japanese is assumed. `add` prints which track it used and lists the others |
| `--audio` | A lossless audio track on the same timeline as the video. Refused if its length differs from the video by more than 0.5 seconds |
| `--device` | `auto` (default) uses the NVIDIA GPU if there is one, and otherwise the CPU. On the CPU, voice separation switches to full precision |

Give `--offset` only when you know it: subtitles from another release can differ between episodes or change timing partway through one. Automatic timing reports the offsets it found.

When the main subtitles are not in the spoken language, `add` still finishes but warns that the episode can only be exported as sound. If the run stops halfway, fix the problem and run the same command again: clips already cut and voiceprints already computed are not computed again. If the clip-cutting step itself fails, the half-built folder is deleted.

## styles

```powershell
uv run avoc styles "subtitles.ass"
```

Lists each style with its line count, time range and sample lines, and marks with `*` the ones that would be picked as dialogue. It also prints the warning about marks left in the text, if any ([SUBTITLES.md](../SUBTITLES.md#when-it-warns)).

## One step at a time

`add` is equal to these commands:

```powershell
uv run avoc prepare "video" --subs "subtitles" --name ep08 --out workspace/episodes/ep08 --offset -0.95
uv run avoc embed workspace/episodes/ep08 --model anime-va
uv run avoc embed workspace/episodes/ep08 --model anime-char
uv run avoc embed workspace/episodes/ep08 --model redimnet2-b6
uv run avoc quality workspace
```

- `prepare` extracts the audio, separates the vocals, aligns the subtitles and makes one clip per line.
- `embed` computes one kind of voiceprint for all clips. Its saved results are reused when the input has not changed.
- `quality` computes the features of the [low-quality hint](../HOW_IT_WORKS.md#glossary) for every episode of the workspace that lacks them, such as episodes added before the hint existed. It can take several GB of memory.

The `--device` option of `prepare`, `embed` and `quality` works as for `add`.

## Filling in older episodes

```powershell
uv run avoc set-video workspace/episodes/ep01 "Episode 01.mkv"
uv run avoc set-subtitles workspace/episodes/ep01 "Episode 01.zh.ass"
uv run avoc set-display-subtitles workspace/episodes/ep08 "Episode 08.zh.ass"
uv run avoc set-spoken-language workspace/episodes/ep01 ja
```

- `set-video` records the video for an episode processed before `prepare` required it. Refused if its length does not match the audio track.
- `set-subtitles` adds subtitles to an episode that has none recorded. The offset is worked out from the existing clips, and the dialogue text is found by matching the times that overlap.
- `set-display-subtitles` attaches subtitles in a language you read to an episode cut from subtitles you don't. The offset is measured automatically; if they do not line up with the main subtitles, it is refused.
- `set-spoken-language` corrects the language an episode speaks when the audio track's tag was wrong or missing. The voices already cut stay as they are; to cut from another audio track, add the episode again with `--spoken`.
