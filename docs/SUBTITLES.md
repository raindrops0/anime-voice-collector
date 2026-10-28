# Subtitle text and warnings

This page explains subtitle cleanup warnings and the plain format that a person, script or AI agent can prepare. Commands for selecting subtitle files and styles are in [Adding episodes](features/adding-episodes.md#which-subtitles-to-give).

## What is cleaned automatically

Exported text should contain the words that are spoken. The app removes recognized speaker labels, sound notes and decorative marks, and leaves out recognized song lyrics. Preview the text while labeling, especially when using subtitles from a new source.

Known limit: a reading in brackets can be removed even when it is spoken. For example, 「Ｇ１(ワン)」 can become 「Ｇ１」. Check such lines before export.

## When it warns

A warning about unrecognized marks includes a count and example lines. Check those examples: exported text may still contain words or signs that were not spoken. Convert the file to the plain format below, or report the recurring subtitle habit with a small example.

## Way 1: convert the file to the plain subtitle format

Anyone can do this with a script, subtitle editor or AI agent. Follow these steps:

1. Save the file as UTF-8 SRT and keep every timestamp unchanged.
2. Put one person's spoken words on each line of an entry.
3. When the speaker is known, put the name first in full-width brackets, such as （テイオー）ねえ. Use brackets for nothing else.
4. Remove sound notes, music notes, arrows, signs and readings, while keeping every spoken word.
5. Run `uv run avoc styles "<new file>"` and check that it prints no warning about marks.

Use the converted file as the main subtitles. A brief that can be handed to an agent:

> Convert `<file>` to the plain subtitle format in docs/SUBTITLES.md of the avoc project. Keep every time unchanged and keep every spoken word. Then run `uv run avoc styles "<new file>"` and check that it prints no warning about marks.

## Way 2: report a recurring subtitle habit

If the same warning appears across files from one source, provide the original example line, the words actually spoken and the expected cleaned text. Keep timestamps and formatting in the example so the problem can be reproduced. Development checks are listed in [CONTRIBUTING.md](CONTRIBUTING.md#python-side).
