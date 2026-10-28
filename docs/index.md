# Documentation index

These pages cover what users and contributors need to run, use and change the app. New here? Start with the guide.

## Guide

Step by step, in English and Simplified Chinese.

- [Install](guide/install.md) ([简体中文](guide/install.zh.md)) owns the Windows download, setup with git, FFmpeg, `avoc doctor` and the Hugging Face token.
- [Your first dataset](guide/first-dataset.md) ([简体中文](guide/first-dataset.zh.md)) walks from an empty folder to an export. It owns no details: each step links to the page that does.

## Features

What each part of the app does, and every option in it.

- [Adding episodes](features/adding-episodes.md) owns the add form, which subtitles to give, what happens when adding stops, and adding a whole season.
- [Labeling basics](features/labeling.md) owns target characters, low quality, ignored lines, retraining and "Update list", names and avatars, undo and history, and page settings.
- [Groups](features/groups.md), [Scenes](features/scenes.md), [Characters](features/characters.md) and [Export](features/export.md) own their view's controls and which lines they list. Characters also owns the "Maybe missed" rules; Export owns the output files.

## Reference

- [Commands](reference/commands.md) owns every `avoc` command and option.
- [Shortcuts](reference/shortcuts.md) owns the keyboard shortcuts.
- [Scripts and agents](reference/agents.md) owns `avoc workspace` and the HTTP interface for scripts and AI agents.
- [HOW_IT_WORKS.md](HOW_IT_WORKS.md) owns terms (the glossary), how labels of new targets are treated, text in the spoken language, and [the data files and backups](HOW_IT_WORKS.md#data-files).
- [SUBTITLES.md](SUBTITLES.md) owns subtitle warnings and the plain subtitle format.
- [TOOLS.md](TOOLS.md) owns runtime requirements, model source links and the development tool list.

## Plans and contributing

- [ROADMAP.md](ROADMAP.md) owns planned user-facing features and platform support.
- [CONTRIBUTING.md](CONTRIBUTING.md) owns development setup, checks, web builds and releases.
- [UI_DESIGN.md](UI_DESIGN.md) owns interface conventions for appearance and interaction.

[USAGE.md](USAGE.md) only says where its old sections moved.

## Maintaining these pages

Keep each fact in one owning page and link to it elsewhere. Public docs contain usage, interface contracts and contributor instructions. Keep core implementation ideas, algorithm details, technical decisions, experiments and measurement records in the maintainer's ignored `private/` folder. Public docs must remain usable without that folder and must not link to its contents.

When adding a public page, list it here and define its scope. When one topic grows past eight files, give it a separate index. The guide pages have a Chinese copy (`.zh.md`); change both in the same commit. After changing docs, run `lychee --offline --include-fragments --no-progress AGENTS.md docs` and fix broken local links. Dropping `--offline` also checks web links.

## How to write

Use plain, easy English. Do not invent abbreviations or use jargon. Explain a borrowed metric name the first time it appears. User-facing terms belong in the [glossary](HOW_IT_WORKS.md#glossary). Feature pages use short sections, lists and tables, not long paragraphs; the guide uses numbered steps.
