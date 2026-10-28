# Scenes (S)

Scenes lists all the lines of the picked episode, by scene and in order. The left side shows the picture and the machine's ranking of its guesses. Rules shared by every view are in [Labeling basics](labeling.md).

## Playing a line

- **Vocals only** is on by default: the picture plays, but the sound is the separated vocals. Click "Original sound" to hear the original.
- **Speed**: 1x, 1.25x, 1.5x or 2x; the reference audio plays at the same speed. Clicking a speed, even the one already picked, plays the line again from the start at that speed.
- Both settings are remembered after a refresh.
- **Space**, or clicking the selected line again, replays it. Clicking the picture pauses or plays; the icon in its bottom-right corner shows which.
- **More context** below the line plays "None", "±5 s" or "±15 s" of extra time on each side. L steps through the three. The choice stays when you move to another line and after a refresh.
- **R** plays a reference line of the machine's top guess. Each target character has a reference sound.
- If a line cannot play, the picture says why, and "Cut again" throws away the saved clip and cuts it again.

## Labeling

- **Enter** accepts the first guess.
- **Number keys** pick a target character from the bottom bar; Shift + number marks it low quality.
- **Q** labels "Not a target"; **X** ignores the line ([lines nobody can tell](labeling.md#lines-nobody-can-tell)).

A line the machine finds maybe low quality shows a red dashed "Maybe low quality" tag with its chance. It is only a hint, learned from your "low quality" labels.

## Which lines are listed

Each line of the episode is in exactly one part. The tick boxes at the top choose which parts are listed, each with its number of lines:

| Kind | Parts |
| --- | --- |
| Confirmed | Clean, Low quality |
| To do | Not guessed yet, Not confident (the only ones ticked at first) |
| | Confident, past a divider line; the "To do" box does not tick it |
| Optional (labeling them helps the machine learn) | Maybe low quality: every unlabeled line with the hint, including those the machine set aside; labeling one moves it out |
| Ignored | Too short (a short line stays there after it is labeled), Ignored by you |

- The box in front of a kind ticks or clears all its parts, and shows a dash when only some are ticked.
- The ticks are remembered in the browser.
- A line you label stays in the list, even when its label moves it to a part not ticked, until the list is updated ([when](labeling.md#when-the-machine-guesses-again)) or the ticks or the episode change.
- **F**, or the "Only to do" button, lists only "To do"; pressing it again goes back to the parts ticked before.
