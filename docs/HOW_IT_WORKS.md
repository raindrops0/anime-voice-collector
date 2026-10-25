# Flow, data and terms

This page explains how things work. For how to type the commands, see [USAGE.md](USAGE.md). For why we chose this way, see [DECISIONS.md](DECISIONS.md).

| Section | What it covers |
| --- | --- |
| [Glossary](#glossary) | What each term in the docs means |
| [Flow](#flow) | From one episode's video and subtitles to clips ready for labeling |
| [Labeling and correction interface](#labeling-and-correction-interface) | How the machine guesses, when it counts as confident, where labels are stored |
| [Data files](#data-files) | What each step writes, and where clip IDs come from |
| [Code layout](#code-layout) | Which file handles which part |

Contents:

- [Glossary](#glossary)
- [Flow](#flow)
- [Labeling and correction interface](#labeling-and-correction-interface)
  - [Target characters and "Not a target"](#target-characters-and-not-a-target)
  - [How the machine guesses](#how-the-machine-guesses)
  - [The low-quality hint](#the-low-quality-hint)
  - [When a clip counts as confident](#when-a-clip-counts-as-confident)
  - [How many labels before the guesses are good](#how-many-labels-before-the-guesses-are-good)
  - [Starting groups](#starting-groups)
  - [Text of a line](#text-of-a-line)
  - [Picture and sound](#picture-and-sound)
  - [Export](#export)
  - [Text in the spoken language](#text-in-the-spoken-language)
- [Data files](#data-files)
- [Code layout](#code-layout)

## Glossary

| Term | Meaning |
| --- | --- |
| Clip | The short piece of audio for one subtitle line, with the silence at its two ends cut off. It is the smallest unit for labeling. |
| Two at once | A clip whose voice overlaps another clip's by more than 0.1 seconds: two lines spoken at the same time, so most likely two voices in it. The interface marks it, and a person decides ([how such a line is labeled](DECISIONS.md#identity-and-interface)). |
| Offset | How many seconds the subtitle times differ from the audio track. Subtitles made for another release of the video (a TV broadcast, say) can have a different offset after the break in the middle of an episode; each part of the episode then has its own. |
| Style | In an ASS subtitle file, every line belongs to a named style, such as "Default" or "OP", which sets its font and place on screen. Subtitle groups often put dialogue, song lyrics and on-screen text in different styles. SRT files have no styles, so all their lines count as one style, "Default". |
| Voiceprint | A set of numbers that describes a voice. It is used to check whether two clips may come from the same person. |
| Distance | The cosine distance between two voiceprints. 0 means the same direction exactly. A larger number means less alike. It is not "the chance that these are the same person". |
| Distance threshold | In the Groups view, two groups merge only if their distance is smaller than this value. |
| Average linkage | A merge rule for hierarchical clustering: two groups merge only if the average distance between all their clips is within the threshold. |
| Too short line | A clip shorter than 1 second, or whose text in the spoken language has at most two syllables, such as あっ or うおーっ, however long. Ignored by default (the code calls it "skipped"): it is listed under "Ignored", which is not ticked at first, and is not work to do. Syllables are counted by fixed rules, without looking words up: each kana is one, except small kana (きょ is one sound, "kyo") and っ; ー and punctuation are none; a Japanese kanji counts as two; a Chinese character, a Hangul block, a digit or a run of Latin vowels is one. |
| Low-quality hint | The machine's chance that a line is too noisy for a clean dataset, learned from the lines marked "low quality". A line nobody labeled that has the hint is listed under "Maybe low quality", not work to do. |
| Target character | A character the user wants to collect. Only target characters get names. Everyone else is labeled "Not a target". |
| Small classifier | A softmax regression (multinomial logistic regression: one score per choice, turned into chances that add up to 1) trained on the manual labels, with voiceprints as input. Its choices are the target characters and "Not a target", and its output is the probability of each. |
| Confidence | The small classifier's probability for the top-ranked character. |
| Similarity check | Checks whether a clip is similar enough to the closest confirmed clip of the top-ranked character. If it is not, the speaker may be someone who has not been labeled yet. |
| Spoken language | The language the voices in an episode speak, such as Japanese. Exported text must be in it, because a voice model learns which sounds go with which words. |
| Main subtitles (主字幕) | The subtitle file an episode is cut from (`--subs`): each line becomes one clip, at its times. Best in the spoken language, so each clip's text is its own line. |
| Secondary subtitles (辅助字幕) | An optional subtitle file in a language the person reads, usually a translation (`--display-subs`; "display subtitles" in the code). While labeling, its line is shown in small gray type under each clip's main subtitle line, so the person understands what is said. It changes nothing in how clips are cut or who the machine thinks is speaking, and nothing is exported from it. |
| Workspace | The folder that the interface opens. Inside it are `episodes/` (one folder per episode), `labels/` (the labels made in the interface) and, unless another folder is picked, `exports/` (the exported datasets). |

## Flow

**Video and subtitles → separate voices → cut clips along subtitle lines → compute voiceprints → label and correct in the interface → export.**

`add` does the first steps in one command:

1. **Reading the subtitles**: The file is read whatever its text encoding: UTF-8 and UTF-16 directly, and older Chinese, Japanese, Korean and Western encodings by trying each and keeping the reading that looks most like real text. ASS, SRT, WebVTT and a few rarer formats are told apart by their content, not by the file extension. Then the dialogue [styles](#glossary) are picked: the main one is the style with the most lines among those whose lines appear across the whole episode (an opening song has many lines, but all at the start). A style whose lines are nearly all placed, turned or given their own font on screen holds signs, and is left out when another spread-out style is mostly not placed: in some fansub files the signs outnumber the dialogue twenty to one. TV captions place every line, but in their one style, which stays. Styles named after it, such as "Default - Top", and other spread-out styles with at least a quarter as many lines (the second language of bilingual subtitles) are dialogue too. Of a bilingual file that keeps each language in its own style, clips are cut only from the style in the [spoken language](#glossary), so the file counts as being in the spoken language alone (see the next step); the add form ticks only that style when the voices are collected to read text aloud. Comment lines, vector drawings, lines over 20 seconds and song lyrics timed for karaoke (lit up one syllable at a time) are dropped; in 705 sample files only one karaoke-timed line was dialogue. `add` prints which styles it used and which it left out, `avoc styles <file>` shows each style with sample lines, and `--styles` overrides the choice.
2. **`prepare`**: Takes the audio from the video (or from a separate audio file given with `--audio` on the same timeline). When the video has several audio tracks (an original and a dub), it takes the one in the [spoken language](#glossary): the language given with `--spoken`, or else a Japanese track if there is one, else the track marked default, else the first. The spoken language comes from that track's language tag; with no tag, Japanese is taken and `add` says so. Separates the voices for the whole episode and keeps the original sample rate. Also makes a 16 kHz copy for analysis. Then adds this episode's offset to the subtitles, so **each subtitle line becomes one clip**. If `--offset` is not given, the offset is measured with speech detection: the subtitle timeline is slid against the speech timeline, and the shift with the most overlap is taken. Then the episode may be split into parts with offsets of their own, at pauses of 1.5 seconds or more between lines. Each part may move up to 1.5 seconds from the whole-episode offset, spans at least 60 seconds of subtitles, and must add at least 2% of the subtitle time to the overlap; at most 4 parts. An episode with no jump stays one part ([why](DECISIONS.md#cutting-clips)). If the alignment is too weak, it stops with an error and does not quietly switch to another method. When the subtitles are in the spoken language alone (not bilingual), each entry is cut **one person at a time**: a line opened by a dash, or with a name other than the person before, starts a new clip, and a line with no mark goes on with the person before. The entry's time is shared among them by character count. Entries with the same text that follow each other with no gap (some subtitles break one line into several entries wherever another entry starts) count as one. Entries with exactly the same times are one entry, in file order: TV captions keep each row on screen as its own entry, so a wrapped sentence comes as two. In such an entry a change of text color starts a new person, as TV captions give each main character a color, and a row of kana drawn smaller than full size is the reading of the words under it and is dropped. `episode.json` records this as `"segmentation": "speaker_turns"`. Last, **each clip's two ends move inward to its voice**: on the 16 kHz copy of the separated vocals, 10 ms frames more than 30 dB quieter than the loud part of the clip (its 95th percentile frame), or quieter than -50 dBFS, count as silence. 0.15 seconds are kept before the first frame with voice and 0.2 seconds after the last. A burst at either end shorter than 0.1 seconds, more than 10 dB quieter than the loud part and further than that from the rest of the voice, such as a click or a breath, does not count as voice. Ends never move outward, and a clip with no voice keeps the subtitle's time. Nothing is dropped.
3. **Secondary subtitles** (`--display-subs`): when given, their dialogue styles are picked as above, except that of a bilingual file only the styles not in the spoken language are shown, since that language already shows from the main subtitles. Their offset is measured against the main subtitles: the display times of both files are drawn as timelines with 10 ms cells, one is slid against the other, and the shift with the most overlap is taken, split into parts the same way. If the overlap is below 0.6 they are not attached, and `add` warns but still finishes.
4. **`embed`**: Computes a unit-length voiceprint for every clip that is at least 0.5 seconds long, once for each of the three models the interface uses. Shorter clips stay in the clip table, but they have no voiceprint.

Labeling and export then happen in the [interface](#labeling-and-correction-interface).

"Only one person speaks in a clip" is a working assumption, not a detection result.

## Labeling and correction interface

`avoc app` starts a web server that only listens on this machine. The front end's source is in `web/`. The server sends the built files in `src/avoc/app/static/`, which are committed, so running the app needs no Node. How to change the front end is in [CONTRIBUTING.md](CONTRIBUTING.md).

### Target characters and "Not a target"
The user names only the characters they want to collect. These are the target characters. Everyone else is labeled "Not a target", using the Q key. A workspace can have several target characters, and you can add or remove them while labeling:
- Each "Not a target" label records which target characters existed at that moment. It counts as "not this target" only for those characters. Setting up every target character before the first "Not a target" label tells the machine the most.
- When you add a new target character, old "Not a target" labels do not count against it: to the machine they mean "this new target, or not a target". Its Characters view has a section called "Maybe missed". It lists the clips that the machine did not assign to it but whose probability of being it is at least 5%, whatever their rank among the choices. A clip counts if nobody labeled it yet, or if it was labeled "Not a target" before this character was a target. Clips marked "not this character" for it, and unlabeled skipped lines, are left out. The list starts with the most likely clips and holds at most 100. They are labeled like any other clip. Labeling such a clip "Not a target" again records the new target too, so it leaves the list. "Not a target" itself has no such list: a clip the machine did not give to it was given to some target, and is checked there.
- When you remove a target character, its labels stay as they are, and the machine stops guessing it. A clip that is the target cannot be any other target, so those labels are still used as negative examples. Adding the character back again loses nothing.
- New characters are target characters by default.
- "Low quality": in the interface this is one more choice. Each target character has two options, "target" and "target, low quality". "Not a target" has no such option, because it is never exported. When saving, "who it is" and "low quality" are stored separately. The name is still the target, and the two are decided together in every label. Choose "low quality" for clips with heavy background sound, overlapping voices, or anything else that does not belong in a clean dataset. These clips are not used for training and are skipped on export. They are not used as examples of the target, and they are not used as negatives either, because the target's voice really is in them. When several people speak and none of them is a target, label the clip "Not a target" directly.
- Only ask "is this the target?" If you are sure it is none of the targets, label it "Not a target". If you cannot tell, for example a passer-by who sounds like a target because the same voice actor plays both, press X ("Ignore line"): the line is set aside, not used for training and not exported ([why](DECISIONS.md#identity-and-interface)).

### How the machine guesses
The three voiceprint models (`anime-va`, `anime-char`, `redimnet2-b6`) are each scaled to unit length, joined together, and then scaled to unit length once more. One softmax regression is trained, whose choices are the target characters the machine guesses and "Not a target". Each labeled clip comes with the set of choices it may be:
- A clip labeled as a target is that target. A clip labeled as a character who is not a target is "Not a target".
- A clip labeled "Not a target" is "Not a target" or one of the targets added after it was labeled.
- "Not this character" takes that character out of the set. An unlabeled clip with "not this character" may be any choice but that one.
- Training raises the summed chance of each clip's set (this is called partial-label likelihood: a label that only says "one of these"). A set of one choice is an ordinary label. A wrong guess is simply corrected to the right person or to "Not a target".
- The weights are held back as a logistic regression with regularization strength 100 would be: with one target, the model is exactly that logistic regression, so the [measurements below](#how-many-labels-before-the-guesses-are-good) still hold. With several targets it has not been measured yet.
- Clips labeled "low quality" are not used for training. We have not measured whether noisy clips help the machine find the target inside the noise, or whether they teach it the wrong thing. For now they are kept out.

The probabilities of a clip add up to 1. On a clip marked "not this character", that character gets 0 and the rest are scaled back up to 1. A training set has a few hundred to a few thousand clips. Training runs on the CPU by default (`avoc app --device cuda` uses the GPU). With 2,000 labels it takes about 1 second, and about 0.5 seconds when it starts from the last answer, as it does after each label; on an NVIDIA GPU it took 15 and 0.25 seconds, because so small a problem waits on each step more than it computes. So every label change retrains everything. A target character gets no guess at all until 10 of their lines are confirmed and at least one line is labeled as someone else: with fewer, the guesses are barely better than calling everyone "Not a target" ([measured](#how-many-labels-before-the-guesses-are-good)), and with no one to compare against, every line would come out as theirs. Until then the page says how many lines each target has, and asks for a few "Not a target" labels if there are none.

### The low-quality hint
A second, separate logistic regression answers only whether a line can go into a clean dataset, not who speaks it. Its input is WavLM-large features of the separated vocals, computed once per episode when it is added (`avoc quality` computes them for episodes added before the hint existed). Lines labeled as a character are its examples: "clean", or "low" when marked low quality. Lines labeled "Not a target" or ignored are left out. It is one model for all characters, started from weights trained on other anime (downloaded once from Hugging Face) and held back toward them, so it gives hints from the first label; offline, it waits for 10 clean and 10 low lines. A line nobody labeled shows "Maybe low quality" at a chance of 0.5 or more; it is then listed under "Maybe low quality" in Scenes and Characters, is not work to do, and is not counted on their tabs. At 0.9 or more it is also set aside: never exported as a confident guess. Labeling it brings it back. Why these choices: [DECISIONS.md](DECISIONS.md#low-quality).

### When a clip counts as confident
A clip skips the line-by-line check by a person only when both of these hold:

1. Its confidence is at least 0.6.
2. It passes the similarity check: its similarity (1 minus the [distance](#glossary)) to the most similar confirmed clip of the top-ranked character is at or above a cutoff. The cutoff is measured from the confirmed clips of all target characters together, and one cutoff is shared by all of them. For each confirmed clip, take its highest similarity to the other confirmed clips of the same character. Then take the 5th percentile of those values, so 95% of confirmed clips pass. A clip that fails is shown as "Maybe someone new", with no percentage, and always waits for a person, however high its confidence. If there are fewer than 20 confirmed clips of target characters in all, no cutoff can be measured. In that case no clip counts as confident, and the interface does not show "Maybe someone new". It only says that the machine can only pick among the characters it already knows. The similarity check is skipped when the top-ranked choice is "Not a target", because an unseen voice is labeled "Not a target" anyway.

The small classifier only picks among the characters it already knows, so the second condition is required.

### How many labels before the guesses are good

Measured once, for one character (Tokai Teio, `teo`). The confirmed labels of episodes 1 and 2 (636 lines, 159 of them Teio, the rest "Not a target"; "low quality" left out) were replayed one at a time, as a person labels them in Scenes from the start of episode 1. After each step the machine was retrained the way the interface does it, and its guesses were scored on episode 3, which it never trained on: 310 lines, 57 of them Teio. Saying "Not a target" for every line there is already right 82% of the time, so that is the number to beat.

The chance gap measures whether the probabilities can be taken at their word: lines the machine gives 80% should turn out to be Teio about 80% of the time. It is the average distance between the two, so 0 is perfect and 0.05 means about 5 points off. "Found" is the share of Teio's 57 lines that the machine named as Teio with confidence 0.6 or more.

| Lines labeled | Of them Teio | Right | Right when confident | Found | Chance gap |
| --- | --- | --- | --- | --- | --- |
| 1–29 | 0 | no guess yet | | | |
| 30 | 1 | 82% | 82% | 0% | 0.17 |
| 50 | 6 | 93% | 95% | 58% | 0.06 |
| 60 | 10 | 94% | 97% | 77% | 0.05 |
| 150 | 25 | 96% | 97% | 81% | 0.03 |
| 200 | 43 | 98% | 98% | 89% | 0.025 |
| 636 | 159 | 99% | 99% | 95% | 0.014 |

- The guesses become useful at about 10 Teio lines and 50 "Not a target": 94% right, and three quarters of her lines found.
- The probabilities can be trusted, to within about 3 points, from about 25 Teio lines (150 labeled).
- What counts is the number of Teio lines, not the total. Labeled in random order, Teio turns up sooner: 20 lines (about 6 Teio) give 94% right, and the chance gap drops under 0.03 by about 80 lines.
- So the interface starts guessing a target at 10 confirmed lines of them (see above), and counts no line as confident before 20.

Not measured: other characters, episodes from another season, and labeling in Groups. To repeat it on a workspace: `uv run python scripts/replay_labels.py workspace teo --train ep01,ep02 --test ep03` ([script](../scripts/replay_labels.py)).

### Starting groups
Only clips still to do are grouped: not labeled yet, not skipped, with a voiceprint, and without a guess the machine is confident about. These are the lines "Only to do" lists in Scenes (so lines with the "maybe low quality" hint are left out), apart from the rare long line with no voiceprint (silent, or missing from a cache). They are grouped with `anime-va`, average linkage and a threshold of 0.70. A person then names each whole group.

### Text of a line
A subtitle line counts as the text of a clip when their times overlap by at least half of the shorter of the two. Text is always matched by the time of the subtitle line the clip was cut from, not by its tightened time, so cutting off silence never costs a clip its words; everything else (picture, sound, voiceprints, export, scenes, "Two at once") uses the tightened time. Two clips that are more than 3 seconds apart start a new scene.

### Picture and sound
The page plays lines from a copy of the whole episode, made by the server in the background: the picture alone as 360p H.264 with a keyframe every second, and the vocals and the original sound (the audio track the voices were taken from) as AAC. It is kept in `app_media/episode/` with `copy.json`, which records the size and change time of the files it was made from; when one of them changes, the copy counts as missing and is made again. The server makes one copy at a time: first the episode of the line open, then the episode after it. On an NVIDIA GPU, ffmpeg decodes, scales and encodes the picture there; if that fails, on the CPU. The page keeps the copy loaded while moving from line to line in the same episode, and each line is a jump to its start: the picture and the chosen sound both go there, and the line starts once both can play. The sound leads and is never moved while playing, as a jump in the sound is heard as a click; the muted picture pauses while the sound waits for data, and is moved to the sound when they drift more than 0.3 seconds apart (at double speed the sound's reported time trails by about 0.2 seconds). The vocals of a line come from its own cut (`app_media/audio/`, made in a few hundredths of a second), so what is heard is exactly the file of that line, with any extra context, and it ends by itself; the picture still comes from the copy and follows it. Each line's cut is a new player, so the chosen speed is set on it again: a sound slower than the picture lets the picture run ahead and be pulled back every 0.3 seconds. The original sound, and the vocals when `PICTURE_PAD` is above 0, come from the copy: each line plays from its start to its end, and timers stop it at the exact moment, as a frame comes only every 16 ms or so and the sound's time updates every quarter second. A player's time is the moment heard now, while sound already sent to the speakers (about 0.07 seconds on a desktop, more over Bluetooth) still plays after a pause; so stopping and muting come that much early, measured once the person clicks or presses a key (`outputLag` in `web/src/playback.ts`). Stopping at the line's end without it played the start of the next voice. `PICTURE_PAD` in `src/avoc/app/video.py` is a switch for comparing two ways: 0 plays only the line, and a value such as 0.5 shows that many seconds of picture, with the original sound, before and after it, so the face is on screen before the voice starts. The vocals still play through that time, since the picture follows their clock, but muted, and the same timers mute them at the exact moment: the half second around a line is often someone else talking. The page reads the switch from the server, so changing it takes a restart and no rebuild. With `localStorage.setItem("avoc-debug-playback", "1")` in the browser's console and a reload, the page writes there when the sound starts, turns on, is muted and stops, and how far that was from the aimed time. Until the copy is ready, or if it will not play in the browser, each line plays its own cut, as below; a line already playing keeps its way of playing until another line is opened.

Each cut is made by ffmpeg, one clip at a time. The picture is 360p H.264, with `PICTURE_PAD` seconds more before and after; its file name ends in `.line`, then `.pad500` for half a second, so each setting keeps its own cuts. The sound is the line alone from the vocal track, and the page starts it when the picture reaches the line. Both are cached in each episode's `app_media/`. Cutting one picture takes more than half a second. So while the episode's copy is not ready, when a person looks at a line, the server first cuts, in the background, the lines within 60 seconds before and after it in the same episode. Nearer lines go first, and the cutting then continues forward in time to the end of the episode. Two threads run in parallel. When the person moves to another line, the whole queue is replaced. Measured on episode 3: a line that was not cut in advance takes 0.8 to 1.1 seconds to open. A line cut in advance takes about 0.1 seconds. When More context is on, a separate copy with 5 or 15 seconds of extra time on each side is cut. Their file names carry `.ctx5` or `.ctx15`. The server's background queue does not cut these; only the page asks for the next three lines ahead. The first time, they take about 0.6 and 1.1 seconds. Each cut is written to a temporary file whose name carries the process number, then moved into place, so two apps open on the same project cannot write into one file.

### Export
Cuts from the vocal track at the original sample rate, and evens out the loudness without clipping peaks. The formats are GPT-SoVITS `train.list` (each line is `path|character|language|text`, with the language as `ja`, `zh`, `en` or `ko`), or just one folder per character. For GPT-SoVITS, the text is always in the episode's spoken language, cleaned of caption marks ([what is removed](SUBTITLES.md#what-is-cleaned-automatically)). Clips without such text are left out. The audio-only format needs no text.

### Text in the spoken language
Each clip's text is matched when the workspace opens, so the Scenes and Characters views show it under the subtitle line, and mark a target character's clip that would be left out with "No text to export" and the reason. The text comes only from the main subtitles, so they must be in the spoken language. Bilingual subtitles count: only their lines in the spoken language are used. An episode cut one person at a time ([flow](#flow)) uses the same pieces as its clips, so each clip's text is exactly its own line. An episode cut from a translation has no text at all and can only be exported as sound; to get text, delete it and add it again with subtitles in the spoken language as the main subtitles.

Each clip shows its own main subtitle line in large type. With [secondary subtitles](#glossary), the line of theirs that overlaps it (by the same rule as under "Text of a line") is shown in small gray type under it. The spoken text is shown under that only when it differs from the main line and the text is exported at all: with "Sound only", nothing about exported text is shown.

The language of each line is worked out from its letters. Two or more kana mean Japanese and two or more Hangul mean Korean. Any other line (Chinese characters only, Latin letters, digits) takes the language most common at its place in the file: the same style and the same line number within the entry. So in a file with Chinese on the first line and Japanese on the second, the Japanese line ６連勝 still counts as Japanese. A file has a language when at least 30% of its lines are in it. The interface's add form and the Export view show the language of each file.

How the text is matched to clips. The clips themselves do not change:

- When subtitles are read, the lines inside one entry are split apart, and the entry's time is shared among the lines by character count. Speaker names, sound notes and other caption marks are removed, and a speaker name is kept apart ([what is removed](SUBTITLES.md#what-is-cleaned-automatically)). Two names count as the same person when one ends with the other, such as トウカイテイオー and テイオー.
- For a clip, every line that overlaps it by more than 0.1 seconds must mostly fall inside the clip: 70% or more of it, or extending less than 0.8 seconds past each end. Together the lines must cover more than half of the clip. Only then is the text counted as complete.
- A character's name in the subtitles is the most common name among the named lines that overlap the character's clips. It must make up more than half of them. A line with a different name that overlaps a clip by more than 0.2 seconds marks that clip as mixed with someone else's speech. When the character's name cannot be found, two or more different names touching a clip also count as mixed. So one subtitle entry with two speakers is left out.
- Clips whose text is incomplete, or that are mixed with someone else's speech, are not exported. They are written to `rejected.tsv` in the export folder, with the character, episode, start and end times, the reason, the main subtitle line and the text found.

## Data files

Each episode has a folder `workspace/episodes/<episode>/`:

- `episode.json` records the paths of the source and the audio tracks, and `subtitle_styles`, the styles the clips were cut from (episodes cut before this was recorded pick them again, which gives the same lines). It also records `audio_track` (which audio track of the video, from 0), `spoken_language` (`ja`, `zh`, `en` or `ko`) and `spoken_from` (`track` for the track's tag, `person`, or `assumed`); episodes added before these were recorded count as Japanese, assumed. `segments.json` records the clip IDs, the episode name, the start and end times of the voice (`start`, `end`), and the times of the subtitle line it was cut from (`line_start`, `line_end`). Clips cut before ends were tightened have no `line_start` and `line_end`; their own times are the line's. `segmentation` is `speaker_turns` for an episode cut one person at a time, and `subtitle_lines` otherwise. With secondary subtitles, it also has `display_subtitles`, `display_subtitle_styles`, `display_subtitle_offset` and `display_subtitle_agreement`. `subtitle_offset` is the offset of the first part. When there are several, `subtitle_offsets` lists them as `[subtitle time the part starts at, offset]`, and `display_subtitle_offsets` the same for the secondary subtitles; a line takes the offset of the part its start falls in.
- Voiceprints are stored in `embeddings/<model name>/`. The matrix and its metadata line up row by row. The cache is tied to the content of the clip files, the content of the analysis audio, the model name and the minimum length. If any of these changes, the cache must be recomputed. An old cache raises an error. It is never used silently.
- `app_media/` holds the picture and sound pieces the interface cuts, and in `app_media/episode/` the whole-episode copy.

The interface's labels are stored in the workspace folder `labels/`:

- `events.jsonl` is append-only. Each line is one batch of changes, and it records each clip's value before and after the change. An undo is also a batch, and `undo_of` records which batches it takes back (one number, or a list when several were taken back at once). A batch is in effect unless a later batch that is itself in effect takes it back, so taking back an undo puts its batches back. Taking back an older batch alone changes a clip back only if the clip still has the value that batch gave it. The cast table `cast.json` is stored separately. When a batch also creates, renames or merges characters, the batch's `cast` field records it, and an undo restores the cast table as well. A new character that has no clips left after an undo is deleted. An undo records what it did to the cast table under `cast.steps` (renamed back, split off a merged character, deleted a character), so it can be taken back in turn. Undos written before 2026-10-25 lack `steps`, and when they changed the cast table they cannot be taken back. Replaying all the lines gives the current labels.
- `cast.json` is the cast table. It holds the name, whether a person gave the name (`named`), the color, the pattern number (`pattern`), the avatar file, and whether the character takes part in training. A character without a name is shown as "Character N". Giving it a name is a rename. Pattern numbers only grow and are never reused. When no avatar has been cropped, the default picture is drawn from the pattern number. Avatar images are stored in the `avatars/` folder next to it.
- `purpose.json` records what the voices are for, `{"purpose": "tts"}` (reading text aloud) or `"audio"` (sound only). It is written once, when the add form starts the first episode, and never changed ([how](USAGE.md#the-views)).

**Clip IDs are a hash of the episode name plus the start and end times of the subtitle line. They do not depend on neighboring clips or on where the ends were tightened to.** Re-cutting an episode from other subtitles, or with another offset, makes its labels invalid; changing only how ends are tightened does not.

## Code layout

```text
src/avoc/
  cli.py                   command entry point (also run by `python -m avoc`)
  doctor.py                machine checks, shown by `avoc doctor`; problems also show in the "Add an episode" form
  project.py               data format for an episode and its clips, content fingerprints, cache folders
  pipeline.py              prepare and add episodes, attach video and subtitles, voiceprint cache
  audio.py                 audio tracks, voice separation, the analysis copy, the speech timeline used to measure subtitle offset
  language.py              picks Chinese or English for messages the web page shows
  quality.py               the low-quality hint: WavLM-large features, starter weights, the 0.5 and 0.9 bars
  embeddings/extract.py    four voiceprint models and the minimum clip length
  stages/subtitle.py       read subtitles, pick dialogue styles, measure offset
  stages/captions.py       every rule for caption marks: take the spoken words and speaker out of a line
  stages/text_subtitle.py  text in the spoken language: split lines, give clips their text
  stages/text_language.py  the language of subtitle lines and of audio track tags
  stages/trim.py           move each clip's two ends inward to its voice
  stages/export.py         export at the original sample rate
  app/workspace.py         read the workspace: episodes, clips, text, scenes, assembled voiceprints
  app/labels.py            label records in the interface, undo, cast table
  app/model.py             small classifier and similarity check
  app/video.py             cut each line's picture and sound, and make the whole-episode copy
  app/ports.py             pick the port for `avoc app`, or find the server already showing this workspace
  app/adding.py            add an episode from the interface: runs `avoc add` in a separate process; several wait in a queue
  app/batch.py             pair the videos and subtitles in two folders by episode number
  app/picker.py            the "Browse…" buttons: opens the system's file window
  app/server.py            web server endpoints, starting groups, picture cutting, export
  app/static/              built front-end files, made from web/ (do not edit by hand)
web/src/
  main.tsx                 starts the page
  App.tsx                  views, shortcuts, saving labels in order, undo
  api.ts                   calls to the server and the shapes of its answers
  language.ts              Chinese or English: tr(Chinese, English)
  clips.ts                 who a line belongs to, the lists of the Characters view, the parts both lists filter by
  looks.ts                 the colors and outlines of pills, shared with the tick boxes that filter lists
  held.ts                  what "Update list" would change after the machine guesses again
  playback.ts              speeds, more context, and the speakers' lag that stopping and muting allow for
  batch.ts                 adding several episodes: naming them and finding what stops each one
  index.css                Tailwind, and the theme's colors and fonts
  components/              the top and bottom bars, the stage and the whole-episode player, one line, avatars,
                           the avatar cropper, the history next to Undo, help, the tick-box filter, and small
                           shared parts (chips, pills, hints, rows of joined buttons)
  components/ui/           shadcn/ui components, copied in by its command
  views/                   Groups, Scenes, Characters, Export, adding an episode, the first page of an empty workspace
web/e2e/                   browser tests, and the script that serves a small made-up workspace for them
scripts/replay_labels.py   replays a workspace's labels to measure how fast the guesses become good
```
