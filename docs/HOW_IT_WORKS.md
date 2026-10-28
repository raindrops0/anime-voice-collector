# Workspace and terms

This page explains the app's terms, what to expect while collecting lines, and which folders to back up. Commands and options are in [Commands](reference/commands.md).

## Glossary

- A clip is the short piece of audio for a subtitle line. It is the smallest unit you label.
- A target character is a character whose lines you want to collect. Everyone else can be labeled "Not a target".
- Main subtitles are the file an episode is cut from (`--subs`). Use subtitles in the spoken language when you want to export text.
- Secondary subtitles are an optional translation shown while labeling (`--display-subs`). They are not exported.
- The spoken language is the language heard in the selected audio track, such as Japanese.
- An offset is how many seconds subtitle times differ from the audio. Different parts of an episode can need different offsets.
- A style is a named group of lines in an ASS subtitle file. Check the chosen styles if dialogue is missing or signs were included.
- A voiceprint describes a voice so clips can be compared.
- Distance describes how different two voiceprints are. A smaller value means more alike; it is not a probability.
- The distance threshold controls how readily clips are grouped in Groups.
- Confidence is the machine's estimated chance for its first choice. It is a guide for review, not a confirmed label.
- A similarity check can flag a line as "Maybe someone new" when it does not sound enough like confirmed examples.
- A too short line is a brief clip or a line with very little spoken text. It starts under "Ignored"; you can still label it.
- "Two at once" marks overlapping lines. Listen before deciding whether the target's line is clean enough to export.
- A low-quality hint suggests that a line may contain noise or overlapping voices. The person makes the final choice.
- A workspace is the folder containing episodes, labels and exported datasets.

## Flow

Add an episode with its video and main subtitles, review and label its clips, then export the characters you want. The app prepares the audio and guesses while you work. Main subtitles provide the clip boundaries and, when they are in the spoken language, the exported text. Secondary subtitles help you understand the dialogue.

Check the subtitle styles, selected audio track and timing before spending time labeling. See [adding an episode](features/adding-episodes.md) and [subtitle warnings](SUBTITLES.md#when-it-warns).

## Labeling and correction interface

The app opens in a browser on this machine. Groups helps you name several lines together; Scenes follows the episode; Characters helps you check a character's lines; Export writes the dataset. See [the feature pages](index.md#features) for controls and shortcuts.

### Target characters and "Not a target"

You can add and remove target characters without erasing existing labels. Check ["Maybe missed"](features/characters.md#maybe-missed) after adding a target: earlier "Not a target" labels do not confirm that the new character was absent. Removing a target stops its guesses; adding it back retains its labels.

The machine learns from confirmed labels. Suggestions from an agent await a person's acceptance. A guess or an unaccepted suggestion is not a confirmed label; see [scripts and agents](reference/agents.md).

### Text in the spoken language

Exported text comes from the main subtitles and must match the spoken language. An episode cut from a translation supports sound-only export. To get spoken text for it, add the episode again with main subtitles in the spoken language.

The app shows "No text to export" with a reason before export. Review these lines and the subtitle warnings. GPT-SoVITS export leaves out clips without usable text and records the reasons in `rejected.tsv`; sound-only export needs no text.

## Data files

Keep the whole workspace when moving between machines. `episodes/` contains the prepared episodes and their source references. Keep the source video and subtitle files available at the recorded paths. `exports/` contains completed datasets unless you chose another output folder.

The current labels, characters, history, suggestions and jobs are in `labels/workspace.sqlite3`. Character pictures are in `labels/avatars/`, and `labels/purpose.json` records what the voices are for. Older `events.jsonl` and `cast.json` files are retained after import, but they are no longer the current labels.

Stop the app and any command-line jobs before backing up the whole `labels/` folder. Copying only the old JSON files does not back up current work. Re-cutting an episode from different subtitles or timing can invalidate its labels; make a backup before replacing prepared episodes.
