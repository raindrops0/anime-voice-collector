# Export (E)

Export writes the dataset of the characters you pick, from every episode. The same can be started from a script ([scripts and agents](../reference/agents.md)).

## Choices

- **Characters**: the target characters start ticked.
- **Format**: one folder per character with sound only (for RVC and such), or GPT-SoVITS with each line's text.
- **Which lines**: only the lines a person has confirmed, or also the lines the machine is confident about.
- **Output folder**: starts as `exports/<today's date>` inside the workspace, shown in full, or `<date>-2` and so on once that one holds an export. Change it, or pick another with "Browse…". A relative path typed there starts from where `avoc app` was started, as in every path box.

When it is done, "Open the folder" shows the export in the file manager.

## What you get

```text
exports/2026-10-24/
├── Mio/
│   ├── ep01_00083.120000_00085.430000.wav
│   └── ...
├── train.list      (GPT-SoVITS only: path|character|language|text)
└── rejected.tsv    (lines left out, and why)
```

Each clip is one line of one character: voice only, mono, at the sample rate of the video, with even loudness. Lines marked low quality are never exported.

## Text for GPT-SoVITS

The text is in each episode's spoken language ([how](../HOW_IT_WORKS.md#text-in-the-spoken-language)).

- The list under "Text of each line" shows, for each episode, the language spoken, where the text comes from, and how many target lines have no matching text. Change the language there if the audio track's tag was wrong; "assumed" means there was no tag.
- An episode cut from a translation has no text and can only be exported as sound.
- Clips without text are not exported; the details are in `rejected.tsv` in the export folder. While labeling, such clips already show "No text to export" with the reason.

## What the voices are for

This is chosen once, in the add form before the first episode ([adding episodes](adding-episodes.md#the-add-form)), and Export only shows it.

- With **"Sound only (RVC and such)"**, the labeling views leave out everything about exported text ("No text to export" and its reasons), the add form accepts a translation as the main subtitles, and Export has only the sound-only format.
- With **reading text aloud**, Export can still write sound only, for RVC, without changing the choice.
- A workspace made with `avoc add` alone has no choice recorded and works as reading text aloud until the add form records one.
