# Roadmap

This page describes who the tool is for and planned user-facing improvements. Current commands and features are documented in [the docs index](index.md#features). These plans may change.

## Who it is for

The tool is mainly for people collecting clean lines of one character to train a voice model, such as GPT-SoVITS or RVC. It also helps people find a character's dialogue across episodes.

## Direction

Make collecting and checking a character's lines take less manual work while keeping the person in control of the dataset.

## Labeling interface

The app has four views: Groups, Scenes, Characters and Export. See [the feature pages](index.md#features) for their controls and [UI_DESIGN.md](UI_DESIGN.md) for interface conventions.

Planned improvements:

- Allow changing what the voices are for after episodes have been added.
- Update groups at a suitable moment without interrupting the current selection.
- Open the lines belonging to a step directly from the history panel.
- Provide a panel for finding and switching workspaces.

## Platforms

Only Windows has been tested. Linux and macOS have installation support, and testing them is planned. Runtime requirements are in [TOOLS.md](TOOLS.md#runtime-requirements).
