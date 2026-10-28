# Labeling basics

These rules hold in every view. Each view has its own page: [Groups](groups.md), [Scenes](scenes.md), [Characters](characters.md) and [Export](export.md). Every key is listed in [Shortcuts](../reference/shortcuts.md).

## Target characters and "Not a target"

Give names only to the people you want to collect, the target characters. Label everyone else "Not a target" with Q, including:

- anyone you are not sure is a target;
- clips where several people speak and none of them is a target;
- clips that are not speech, such as cheers and sound effects.

A target character's own laughs and sighs count as their voice, so label them as the target.

There can be several target characters. Add or remove them at any time in [Characters](characters.md); existing labels stay ([what happens to them](../HOW_IT_WORKS.md#target-characters-and-not-a-target)).

## Clean or low quality

Each target character has two choices, picked in one go:

- the number key gives the clean target;
- Shift plus the same number gives "target, low quality".

Use low quality for clips with heavy background sound or with several people talking at once. These clips are not used to recognize the character, and they are skipped on export and written to `rejected.tsv`. With two target characters, the bottom bar has five choices in all: clean and low quality for each, plus "Not a target". Next to each target's guess on the left there is also a "Low quality" button. Changing a clip to the clean target or to "Not a target" removes "Low quality".

## Lines nobody can tell

When you cannot tell who a line is, for example a passer-by voiced by a target's voice actor, press X ("Ignore line"). It moves to "Ignored", is not used for training and is not exported. Backspace or Z takes it back.

Lines shorter than 1 second, and lines of only one or two syllables such as あっ, are marked "Too short, ignored" ([terms](../HOW_IT_WORKS.md#glossary)) and do not count as work to do. You can still label them: a labeled short line is exported and used for training like any other, and one marked low quality is still left out.

## When the machine guesses again

Each label is saved to disk and retrains the machine right away, and its guesses change on other lines too. Those lines show their new guess at once, but Scenes and Characters do not add, take out or reorder lines by themselves, so nothing moves under your hand.

- The message at the bottom says what would change, for example "3 lines to take out".
- "Update list", in that message or next to Undo in the bottom bar, applies it. Switching the episode, view or character also does.
- Updating also takes out the lines you labeled into a part not ticked, and brings "Maybe missed" up to date ([which lines](characters.md#maybe-missed)).
- Tick "Auto" next to "Update list" to have the list update by itself each time; the choice is remembered in the browser.

## Names and avatars

People are told apart mainly by avatar, so names can be left blank.

- **N** labels the current line as a new target character. A dialog asks for its name; left blank, it gets a temporary name such as "Character 1". "Cancel" (Esc) takes the new character back, and the lines return to how they were.
- In the New target dialog, a name another character already has is refused. In "Name" or "Rename or merge" in Characters, typing another character's name merges the two; the dialog says so before you save, and Z undoes it. "Not a target" is never a name.
- A character with no avatar shows a picture made from its number. Background color, shape and pattern all change together, so characters are easy to tell apart at a glance.
- **Cropping an avatar**: when a new character is made and the line has a picture, the same dialog crops an avatar ("No avatar" keeps only the name). Later, click the avatar, on the confirmed lines on the left or at the top of Characters. Drag the box to move it; drag the bottom-right corner or use the scroll wheel to zoom; use the slider to change the frame; Enter saves.

## Undo and history

- **Backspace** (or Delete) clears the label of the current line and returns it to the machine's guess. Confirmed lines also have a "Clear label" button on the left.
- **Z** undoes the last step; keep pressing it to go further back. Making, renaming and merging characters are undone too. Avatars and setting or unsetting a target are not part of undo; just change them back.
- **The clock button next to Undo** opens the history, newest step first. Point at a step to take back just that step ("Take back"), or every step after it ("Back to here"). Tick several steps to take them back together.

Taking back is a step of its own, so the history only grows, and a take-back can itself be taken back. A line that a later step changed again keeps the later change. Undoing a rename takes every line of that character back to the old name, including lines labeled after the rename. A step is left out, with a message, when a name it needs back is now used by another character. Imported labels, and every step before them, cannot be taken back.

## Page settings

- The line between the picture side and the list can be dragged to change their widths. The width is remembered in the browser; double-clicking the line puts it back.
- The tabs at the top come in two boxes. The first holds the episode menu with Groups and Scenes, which show only that episode. The second holds Characters, which covers every episode. Export, on the right of the bar, also covers every episode.
- The page is light by default; switch to dark mode at the top right. Next to it, EN / 中文 switches the page language; the first time, it follows the browser's language. Messages from the server follow the page language. Both choices are remembered in the browser.
- The part of the address after `#` records the view, episode, character and selected line, so a refresh returns to the same spot.
- The first time a workspace with episodes but no labels is opened, a getting-started guide opens. Open it again with "Guide" in the top bar, or from the shortcuts dialog (`?`).
