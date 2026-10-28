# Your first dataset

**English** · [简体中文](first-dataset.zh.md)

This page walks you from an empty folder to an exported dataset of one character. It assumes the app is installed ([Install](install.md)). Each step links to the page with every detail.

## What you need

For each episode:

- **the video** (`.mkv`, `.mp4`, …);
- **main subtitles** whose lines match the dialogue (`.ass` or `.srt`). Each line becomes one clip, the short piece of audio you label. They are best in the language spoken, such as Japanese subtitles for a Japanese anime, because the exported text comes from them;
- if you like, **secondary subtitles** you can read, such as a translation. They are shown under each line while labeling and change nothing else.

## 1. Start the app

Double-click `start.bat` in the Windows download, or run:

```powershell
uv run avoc app workspace
```

`workspace` is a folder of your choice; it holds the episodes, the labels and the exports. The app opens in your browser at `http://127.0.0.1:8765` ([options](../reference/commands.md#app)).

## 2. Add the first episode

A workspace with no episodes opens on the "Add an episode" form.

1. At the top, choose **What the voices are for**. "Read text aloud (GPT-SoVITS and such)" keeps both ways open; "Sound only (RVC and such)" also accepts a translation as the main subtitles, but such episodes can never give text. This is chosen once per workspace.
2. Pick the video, the main subtitles and, if you like, the secondary subtitles with "Browse…", or paste their paths.
3. Leave the offset empty to have it measured (needs the [Hugging Face token](install.md#hugging-face-token-for-automatic-timing)), or type it.
4. Press **Start**.

It separates the voices from the music, cuts one clip per subtitle line and computes voiceprints, which describe each voice so clips can be compared. One episode took about 12 minutes on an RTX 4060 Laptop GPU. You can close the dialog and keep working while it runs. To add a whole season in one go, pick "Several, one after another" ([adding episodes](../features/adding-episodes.md)).

## 3. Label the first lines in Groups

Press **G**. The machine puts lines that sound alike into groups.

1. Tick the lines of one person, or press "Select all" when the group is one person.
2. Pick who they are in the bottom bar: a target character (number key), **"Not a target"** (Q), or **"New target"** (N) to make a new target character. The name can be filled in later.

A target character is a character whose lines you want to collect. Label everyone else "Not a target", including anyone you are not sure about ([labeling basics](../features/labeling.md)).

## 4. Go through Scenes

Press **S**. Every line of the episode is listed in order, with the video playing.

- **Enter** accepts the machine's top guess; a number key picks a target; **Q** labels "Not a target".
- **Shift** + number marks the line as that target but low quality, for heavy background sound or two people at once. Such lines are never exported.
- **X** sets aside a line nobody can tell; **L** plays more of the scene around it.

Once a target has 10 confirmed lines and a few others are labeled "Not a target", the machine starts guessing. Each label retrains it in a moment ([Scenes](../features/scenes.md)).

## 5. Check each character in Characters

Press **O** and open your character. The lines the machine gave it come first, least sure first.

1. Press **P** ("Play all to check") to hear them one after another.
2. When one is wrong, label it as the right person, or press Q.
3. When the rest sound right, press **Shift+Enter** to confirm them.

Then look at "Maybe missed": lines the machine did not give to this character but that might be it ([Characters](../features/characters.md)).

## 6. Export

Press **E**. Tick the characters, choose the format (one folder per character with sound only, or GPT-SoVITS with each line's text) and the output folder, and start the export. "Open the folder" shows the result ([Export](../features/export.md)).

## If something goes wrong

- **Z** undoes the last step; the clock button next to Undo takes back any earlier one ([undo and history](../features/labeling.md#undo-and-history)).
- If adding an episode stopped halfway, for example out of graphics memory, use "Carry on" under "Unfinished episodes", or add it again on the command line; it continues where it stopped.
- `uv run avoc doctor` checks the machine ([Install](install.md#check-the-machine)).
- Press **?** in the app for every key, or see [Shortcuts](../reference/shortcuts.md).
