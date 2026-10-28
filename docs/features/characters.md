# Characters (O)

Characters covers every episode: switching the episode does not change it. Here you check what the machine gave each character, fix the wrong ones and confirm the rest. Rules shared by every view are in [Labeling basics](labeling.md).

## The list of characters

On the left, from the top:

1. the target characters;
2. characters that are no longer targets but still have labels;
3. "Not a target".

Each row shows how many lines have been confirmed, how many the machine assigned to it (in orange), and the total length of the confirmed dialogue.

The buttons beside a character's avatar, under the name, rename or merge it and set or unset it as a target ([names and avatars](labeling.md#names-and-avatars)). Clicking the avatar crops a new one from the picture.

## Checking a character

Open a character. The lines the machine assigned to it come first, starting with the least confident.

1. Press **P** ("Play all to check"), in the bar above them, to play them one after another.
2. When you hear a wrong one, label it as the right person, or press Q for "Not a target". It leaves this list.
3. After listening to the rest, press **Shift+Enter** ("Confirm the other N lines") to confirm them.

"Confirm the other N lines" confirms only the "To do" lines that are ticked and whose newest guess is still this character.

## Which lines are listed

Tick boxes under the name choose which parts are listed, each with its number of lines, in the same order as in [Scenes](scenes.md#which-lines-are-listed):

| Kind | Parts |
| --- | --- |
| Confirmed | Clean, Low quality ("Not a target" has one "Confirmed" box) |
| To do | Not confident, Confident (the lines counted in orange on the left) |
| Optional (labeling them makes the next guesses better) | Maybe missed; Maybe low quality |
| Ignored | Too short, Ignored by you |

- **Maybe low quality**: every line the machine gave this character that nobody labeled and that has the "maybe low quality" hint, including those the machine set aside. They are never confirmed at once. The least likely to be low quality come first, as those are the clean lines the hint most likely got wrong.
- **Too short**: lines the machine gave this character that the rule skips and nobody labeled. One labeled as this character is under "Confirmed".
- **Ignored by you**: ignored lines the machine would give this character.

Only "To do" is ticked at first, and the ticks are remembered in the browser. Each box looks like the pill on its lines. On a line given by the machine, the pill shows only the machine's chance, orange when it is not confident.

## Maybe missed

Below the assigned lines is "Maybe missed": lines the machine did not give to this character but that might be it. They are labeled like any other line.

- A line is listed when the machine gives it at least a 5% chance of being this character, whatever its rank among the choices, and either nobody labeled it yet, or it was labeled "Not a target" before this character was a target.
- Lines marked "not this character" for it, and unlabeled too-short lines, are left out.
- The most likely come first, and at most 100 are listed.
- Labeling such a line "Not a target" again records the new target too, so it leaves the list.
- Each time the list is updated ([when](labeling.md#when-the-machine-guesses-again)), these rules are applied again: lines that now qualify join; lines labeled as another character, or whose chance fell below 5%, leave; and a line the machine now gives to this character moves to its "To do".

"Not a target" has no such list: a line the machine did not give to it was given to some target, and is checked there.

## Checking "Not a target"

"Not a target" can be opened too. Each line there shows which target character the machine thinks is closest, and with what chance. Confirmed lines are sorted starting from those closest to a target, so wrong labels show up first.
