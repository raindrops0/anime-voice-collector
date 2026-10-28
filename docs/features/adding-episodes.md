# Adding episodes

An episode is added from the app's form or with `avoc add` on the command line. Both run the same steps: extract the audio track, separate the voices from the music, cut one clip per subtitle line, then compute the three voiceprints the app needs. The command and all its options are in [Commands](../reference/commands.md#add).

## Which subtitles to give

- **Main subtitles** are what an episode is cut from. Give subtitles in the spoken language when you have them: each clip's text is then its own subtitle line, and an entry where two people speak is cut into one clip per person.
- **Secondary subtitles** are a translation you read. They are only shown while labeling. If they do not line up with the main subtitles, adding warns and still finishes; `set-display-subtitles` attaches them later ([commands](../reference/commands.md#filling-in-older-episodes)).
- Cutting from a translation also works, but then the episode has no text and can only be exported as sound. To get text later, delete the episode and add it again with subtitles in the spoken language ([why](../HOW_IT_WORKS.md#text-in-the-spoken-language)).

Subtitles can be in any common text encoding. The dialogue [styles](../HOW_IT_WORKS.md#glossary) of an ASS file are picked automatically; the form lists them under the subtitle path with check boxes, and `avoc styles` lists them on the command line. If a warning says some lines still contain marks, see [SUBTITLES.md](../SUBTITLES.md#when-it-warns).

## The add form

Open it from the first page of an empty workspace, or with "+ Add an episode…" at the top of the episode menu.

- **What the voices are for** is chosen once, at the top of the form before the first episode, and kept in the workspace (`labels/purpose.json`). It starts at "Read text aloud (GPT-SoVITS and such)", which keeps both ways open. After that the form and Export only show it; switching later is not supported yet ([roadmap](../ROADMAP.md#labeling-interface)).
- **Video** and **the language the characters speak**: by default the language is taken from the audio track, and the form shows which track and language. Change it only to collect a dub.
- **Main subtitles**, best in that language. The form shows the language of each subtitle file. When the voices are for reading text aloud, the main subtitles must be in the spoken language (a bilingual file counts): with a translation there, Start stays off and the form says to put it under secondary subtitles, or, before the first episode, to choose "Sound only". With "Sound only", a translation is accepted, and the form warns in large type that such an episode can never give text later.
- **Secondary subtitles**, if you like.
- **Episode name**: left empty, it is the next unused `epNN`. A name such as `usagi-s1-ep01` keeps several anime or seasons apart in one workspace.
- **Offset**: filled in with the last episode's offset. Leave it empty to have it measured; that needs the [Hugging Face token](../guide/install.md#hugging-face-token-for-automatic-timing).

"Browse…" next to each box opens the system's file window ([where it opens](../UI_DESIGN.md#typing)); pasting a path also works. If the window cannot open, for example a Linux Python built without Tk or no desktop, the page says so; paste the paths instead.

## While it runs

Start runs the same `avoc add` as the command line, in a separate process. The progress lines show as it goes; library warnings show only if it fails. Separating the voices of one episode took about 12 minutes on an RTX 4060 Laptop GPU; the voiceprints take under a minute.

You can close the dialog and keep labeling. A button at the top shows that it is still running, and the new episode appears in the menu when it is done. Stop ends it. Only one episode is added at a time.

## When it stops or fails

- If it stops or fails **before the clips are cut**, the half-built folder is deleted, and carrying on cuts them again from the start; that step is the slowest.
- **After the clips are cut**, finished steps are kept.

Either way the episode is listed under "Unfinished episodes" with a "Carry on" button, which reruns it with the files it was started with. Those files are noted in `adding.json` in the workspace until the episode is added, so the list stays the same after the server restarts. An episode whose clips were never cut also has a "Give up" button, which deletes its note and any half-built folder.

On the command line, fix the problem (for example, not enough GPU memory) and run the same command again: clips already cut and voiceprints already computed are not computed again.

## Adding a whole season

Pick "Several, one after another" under "How many episodes".

1. Give the folder of the videos, the folder of the main subtitles (it may be the same folder) and, if you like, the folder of the secondary subtitles.
2. The files are paired by the episode number in their names (`S02E03`, `[03]`, ` - 03 `, `第03話` and such; the year, `1080p`, `x265` and `10bit` are not taken for it).
3. Each episode is named from the box after "Names" plus its number, such as `usagi-s2-ep03`. The box starts with the part before the number of the latest episode's name.

Details:

- Episodes already in the workspace, or with no video or no subtitles, are listed but cannot be ticked.
- When an episode has two videos, such as two encodes, a box appears to keep only the files whose name holds some text, such as `x265`.
- The audio track and subtitle styles are shown for the first ticked episode. Left as they are, each episode picks its own styles; once changed, every episode uses the ticked ones.
- The offset box starts empty, so timing is checked separately for each episode.
- Every episode is checked before any starts, and all problems are listed at once.

The queue is saved before the first episode starts, then the episodes are added in order. A failed episode does not hold up the rest. The progress box lists each one as waiting, adding, added, failed or stopped. Stop ends the one running and the rest of the queue; the ones not added are listed under "Unfinished episodes", also after a restart. With two or more there, "Carry on with all, one after another" queues them again. While a queue runs, Start puts more episodes at its end.
