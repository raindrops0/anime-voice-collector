# Settled approaches and ruled-out paths

This page lists only the conclusions. Each one has a one-sentence reason. To overturn one of these, bring new data first, then change it here. Approaches that are not settled yet are not listed here.

Contents:

- [Settled](#settled)
  - [Goal and scope](#goal-and-scope)
  - [Cutting clips](#cutting-clips)
  - [Audio](#audio)
  - [Voiceprints](#voiceprints)
  - [Identity and interface](#identity-and-interface)
  - [Low quality](#low-quality)
  - [Export](#export)
- [Ruled out](#ruled-out)

## Settled

### Goal and scope

- The unit of collection is a **character**, not a voice actor. New characters are allowed. Do not force an unknown character into a known name.
- Settle identity classification first. Interjections and noise come later.
- Subtitles give only the time boundaries and the dialogue text. No speech-to-text or text recognition is added.
- Do not fine-tune the voiceprint models. There are only labels for a few episodes, which is not enough. For when to reconsider this, see [ROADMAP.md](ROADMAP.md#direction).

### Cutting clips

- **Always cut along whole subtitle lines.** Cutting by voice detection instead dropped 40% of the dialogue lines.
- **Cut from subtitles in the spoken language when there are any. A translation is attached only to be shown while labeling** (since 2026-10-24). The two files break and time their lines differently. Of 920 Tokai Teio clips cut from Chinese subtitles with Japanese text attached, 146 could not be exported because a Japanese line only partly fell inside the clip: about one line in six. Cutting from the spoken language gives each clip its own line as its text. Cutting from a translation still works, for when no subtitles in the spoken language exist. So the Add form takes only two subtitle files, the main subtitles and the secondary subtitles.
- **Exported text comes only from the main subtitles; there is no separate text file** (since 2026-10-24). Attaching spoken-language subtitles to an episode cut from a translation was removed: it is the path that lost one line in six above, and keeping it meant a second way to get text with its own offset check and warnings. An episode cut from a translation exports sound only; to get text, add it again with spoken-language main subtitles. The voices still work for sound-only training. This is why the add form warns, when "sound only" is picked, that this choice cannot be changed later for episodes cut from a translation.
- **When the main subtitles are in the spoken language, an entry where two people speak is cut into one clip per person.** A line with no mark goes on with the person before, because subtitles wrap long sentences: in the Netflix Japanese subtitles of episodes 1 to 7, 720 entries with several lines carry no mark, most of them one wrapped sentence. Two people with no mark stay one clip, and a person labels it "low quality". In TV captions, which give each main character a color, a change of color also starts a new person (since 2026-10-25); in 57 TV caption files, rows of two colors joined into one clip fell from 852 to 17. How a new person is found is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md#flow).
- **A measured offset may differ between parts of an episode** (since 2026-10-25). kamigami's Japanese subtitles for season 2 of Gochuumon wa Usagi desu ka jump by 0.2 to 0.9 seconds around minute 12 in 7 of 12 episodes, against the Chinese subtitles inside the BD video: they were most likely timed for the TV broadcast, whose break in the middle is another length. With one offset, three episodes fell below the 0.6 overlap and were refused, and in three others half the clips were cut 0.4 to 0.5 seconds off. Split at pauses into at most 4 parts, the overlap against the video's own subtitles rose from 0.70–0.81 to 0.84–0.91 in those episodes, and the 5 episodes without a jump stayed one part. Measuring the parts takes about a second. An offset given by hand is still one value for the whole episode.
- **Voice detection is used only to measure how many seconds the subtitles differ from the audio track.** When `--offset` is given, it does not run at all. No model is used to judge "is someone speaking in this clip" or "is this the character or background voices".
- **Each clip's two ends move inward to its voice, by the loudness of the separated vocals alone; nothing is dropped or split, and ends never move outward** (since 2026-10-24). Subtitles show before the speech starts and stay after it ends, so lines played one after another sounded broken up; the voice almost never runs past the subtitle line. How it is done is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md#flow).
- TV narration and crowd cheers in the subtitles are still put into the clip table. A person labels them "Not a target". Such clips go into training as "Not a target", which teaches the machine that cheers and sound effects are not the target.
- Subtitle lines are not filtered by positioning tags such as `\pos`. Most lines with positioning tags are real dialogue.
- **Subtitle files are read by fixed rules, with no AI model and no editing by hand.** The format is fixed; what varies by subtitle group is the text encoding, the style names and the caption marks. All three are worked out from the file itself. The dialogue styles are picked by how widely their lines are spread through the episode and how many there are, leaving out a style of signs: nearly every line placed on screen, while another spread-out style is mostly not (since 2026-10-25; this is a rule over a whole style, unlike filtering single lines by positioning tags, ruled out below). In 704 sample files from 50 makers it changed 10 choices, each one dropping a sign style; in 4 of them the Japanese dialogue had been left out. Names are not matched against a list of words such as "OP" or "sign", which would differ from group to group and language to language. The person can see the choice and override it.
- **Caption marks are removed by rules kept in one file, and marks the rules do not know are reported, never passed on silently.** No set of rules covers every subtitle maker. The way to handle a file the rules miss is a documented plain subtitle format that any script, editor or AI agent can produce, or a new rule in that one file ([SUBTITLES.md](SUBTITLES.md)). The program does not load code written by the user, which would break when its own code changes.
- Clip IDs depend only on the episode name and the time range of the subtitle line, so labels stay valid until the episode is cut again from other lines ([details](HOW_IT_WORKS.md#data-files)).

### Audio

- All clips go through the same processing, and the voices of all of them are separated. No clip is picked case by case as "this one is clean, use the original track".
- Analysis uses 16 kHz. Export cuts from the vocal track at the original sample rate. It does not upsample to pretend high frequencies were recovered.
- Do not filter clips by a quality ranking or a quality quota. A quality ranking can guarantee neither identity nor cleanliness.

### Voiceprints

- **Clips shorter than 0.5 seconds get no voiceprint.** At that length, telling two characters apart is barely better than a coin toss. Clips of 0.5 to 1 second are still usable, so they are kept.
- **The first groups in the Groups view use the `anime-va` model and average linkage** (merging two groups by the average distance between all their clips). Among the models and merge rules tried, this pair made the fewest wrong merges.
- **Each model has its own similarity scale, so a threshold cannot be copied from one model to another.**

### Identity and interface

- **The interface uses a small classifier to assign clips to character names. Grouping is used only at the start, to give a whole group a name.** The three voiceprint models are joined together and fed into one softmax regression. Grouping compares one noisy clip with another under one shared threshold that drifts as episodes are added; the classifier compares a clip with dozens of clips of one character, each with its own boundary. In real labeling, correcting the classifier's mistakes takes much less work than naming groups, so no numeric comparison with grouping is planned.
- **Only target characters get names. Everyone else is labeled "Not a target". One classifier picks among the target characters and "Not a target" (since 2026-10-25; before, each target had its own "is this the target?" classifier).** Users usually want only one or two characters, and naming every line of every episode is wasted effort. Target characters are added and removed partway through, so each "Not a target" label records the target characters that existed at that time, and to the classifier it means "one of the targets added since, or not a target" ([how](HOW_IT_WORKS.md#target-characters-and-not-a-target)). With one classifier per target the chances did not add up to 100%, which was hard to read. With one target the new classifier is the old one exactly; with several it has not been measured yet.
- **A clip counts as "confident" only if it has a confidence of at least 0.6 and passes the similarity check.** With confidence alone, narration gets forced into a known character.
- **There are no "unclear", "multiple people" or "not speech" labels.** When the only question is whether a clip is the target, these labels cannot say whether it is the target. A target speaking over someone else is labeled "target, low quality".
- **A line no one can tell is set aside with "Ignore line" (X), not labeled "Not a target"** (since 2026-10-25). On usagi, some passers-by are voiced by a target's voice actor: they sound like the target, but cannot be confirmed. Labeled "Not a target", they would teach the machine that the target's voice is not the target. An ignored line is not used for training, not exported, and not work to do; it is listed under Ignored in Scenes. This is not the retired "unclear" label: it says nothing about who it is, and the machine learns nothing from it.
- Train only on labels that a person has confirmed. The machine's predictions are not used for training, and they are not saved as a separate copy to serve as labels.
- **Negative examples are not removed by how easy they are. But clips the machine is confident are "Not a target" do not need line-by-line checks by a person.** Easy negatives do not help accuracy, and keeping them in training costs almost no time. The real effort is a person confirming them, so a person looks only at the hard ones.
- **Clips shorter than 1 second, and clips whose spoken text has at most two syllables, are skipped by default** ([how syllables are counted](HOW_IT_WORKS.md#glossary)). They are almost never the lines people want: mostly interjections, shouts and names called out. A short clip next to other lines is skipped too; keeping those, in case the subtitles had split one long line, kept nearly all short clips. They do not count as work for a person. They are not in the initial grouping, and they are not exported as "confident". In Scenes, and in Characters under the character the machine gives them to (since 2026-10-25), they are listed under "Ignored", which is not ticked at first. If a person labels one anyway, it is used like any other line: for training and on export, with "low quality" still left out.
- Every episode processed must have both video and subtitles. If either is missing, the run is refused. The subtitles decide how to cut, and the video lets a person identify the speaker.
- Labels are made in the interface and stored in the workspace's `labels/` folder.
- **The web app is written in React and TypeScript, and built with Vite** (since 2026-10-24). Preact with htm was enough, but contributors are more willing to work on a stack they already know, and changing it after release is harder.
- **The web app's look is built with Tailwind CSS and shadcn/ui on Base UI** (since 2026-10-24). Tailwind is a set of small ready-made classes written right in the markup, so there is no separate stylesheet to keep in step with the code. shadcn/ui copies each component's source into `web/src/components/ui/`, where it is ours to change. Base UI, under those components, handles the keyboard, focus and screen readers for menus, dialogs and hints. The hand-written stylesheet before it kept growing, and fixing a narrow window meant new rules for each part.
- **The colors are shadcn's default gray theme for now.** Kept open: bring back the earlier purple look by setting the color variables at the top of `web/src/index.css` (`--primary`, `--accent`, `--ring` and the others, the color names every component uses) to the old colors. No component would need to change.
- **Lines play from a whole-episode copy made in the background, as a video player does; per-line cuts are only the fallback until it is ready** (since 2026-10-25). Cuts made ahead of time cover only the lines near the one open, and a line not cut yet took 0.8 to 1.1 seconds to open. The source video cannot be played in the page itself: it is often several GB, in a container or codec (MKV, 10-bit AV1) browsers do not all play, with several audio tracks. The copy is 360p H.264 with a keyframe every second, so a jump to any line starts at once, plus the vocals and the original sound as AAC: about 90 MB for a 24-minute episode. The vocals of a line are still played from its own cut (since 2026-10-25): an audio cut takes a few hundredths of a second, and only a cut sounds exactly like the file that is exported, with nothing of the next voice after it. H.264 is used because every browser plays it. On an NVIDIA GPU it is made with NVENC, about 36 seconds per episode; on the CPU about 70, nearly all of it spent decoding the AV1 source, so a faster encoder or setting would barely help. How it is made and used is under "Picture and sound" in [HOW_IT_WORKS.md](HOW_IT_WORKS.md).
- **The built front-end files are committed to git, and CI checks that they match the source.** Users install with `git clone` and `uv sync`, and must not need Node.
- **Paths are picked with a "Browse…" button: the local server opens the system's file window. Files cannot be dragged into the page.** A browser gives a page the content of a dropped or chosen file but never where it is, and a video of several gigabytes must not be copied just to learn that.

### Low quality

- **The "low quality" hint uses WavLM-large, not a ready-made quality score.** WavLM-large is a general speech model, trained on a large amount of unlabeled speech. The input is the separated vocals. For each clip, the mean and the spread over time of WavLM-large's layers 4, 6 and 8 go into a logistic regression, trained on the person's own "target" and "target, low quality" labels. On Teio's labels it beat every quality-score model and the voiceprints, and torchaudio, which is already a dependency, ships the model. It is only a hint, and the person decides (see "Audio" above).
- **One model for all characters together, not one per character.** On usagi's 7 characters, pooling scored 0.91 ranking accuracy (auc: the chance a random low clip ranks above a random clean one) against 0.82 for one model per character; telling the model which character it is changed nothing. Low quality is about the sound, not the speaker.
- **It starts from weights trained on other anime, downloaded from Hugging Face, and is held back toward them.** Teio's model scored 0.91 on usagi with no usagi labels; usagi's own labels needed about 100 to match it. Training from those weights and holding the weights and the offset back toward them did as well as training on both anime's clips together, without shipping anyone's clips. The weights file is not in git.
- **The hint shows at a chance of 0.5; a line nobody labeled is set aside at 0.9, so it is never exported as a confident guess.** On usagi, 0.9 caught 75% of the low clips and wrongly set aside 4% of the clean ones. Labeling a set-aside line brings it back. Numbers in [quality.py](../src/avoc/quality.py).
- **Every unlabeled line with the hint is listed under "Maybe low quality" and is not work to do, in Scenes and in Characters** (since 2026-10-25). With only the 0.9 lines kept out, a line showing "Maybe low quality 89%" was still listed as work to do while the box of that name was unticked. The cost: about 12% of the clean lines (the share 0.5 wrongly flags) leave the work to do; they are still listed under "Maybe low quality", one tick away.

### Export

- **Exported text is always in the language spoken in the video.** Voice training needs the words that are actually said, so a translation is never written as training text. Where the text comes from is under "Cutting clips" above. Still no speech-to-text.
- **Each episode records the language spoken, and the audio track is chosen to match.** It comes from the language tag of the video's audio tracks, or from the person; with no tag it is taken to be Japanese, and the person is told. A video with a dub as its first track would otherwise give the wrong voice.
- **The language of subtitle text is worked out from its letters by fixed rules.** Two or more kana mean Japanese and two or more Hangul mean Korean; other lines follow the language most common at their place in the file (their style and their line number within the entry), which tells Chinese from kanji-only Japanese and handles bilingual files. No language model is used.
- **Clips are matched to the spoken text when the workspace opens, not on export.** The labeling views then show each clip's text and whether it will be exported, before the person spends time on it.
- **Text in the spoken language is required only for export with text.** GPT-SoVITS export leaves out clips without it; audio-only export does not need it. So `avoc add` only warns when the main subtitles are not in the spoken language, and the add form refuses them only when the voices are for reading text aloud ([how](USAGE.md#adding-an-episode)).
- Clips that cannot get complete dialogue, or that mix in someone else's speech, are not exported. They are recorded in `rejected.tsv`, and half-matched text is not forced into a clip.

## Ruled out

All of these were tried. Do not reopen them.

| What was tried | Result |
| --- | --- |
| Switching to the WeSpeaker model | No setting beat `redimnet2-b6`, let alone `anime-va` |
| Merging groups by the nearest pair, by the farthest pair, or by mutual nearest neighbors | All were worse than average linkage |
| Grouping around a few known example clips per character | The gain was small, and wrong clips already in a group spread further |
| Two-step grouping (group the long clips first, then attach the short clips) | Far more wrong merges |
| Score normalization (rescaling similarities by how close each clip is to everything else) | Almost no gain, and short clips got worse |
| Padding short clips with the neighboring audio | Little gain at 1.5 seconds, clearly worse at 3 seconds |
| Filtering out signs and fansub group names with subtitle positioning tags | Drops real dialogue |
| Cleaning caption marks with an existing tool (Subtitle Edit, subtitle-filter), checked 2026-10 | They only know half-width brackets and English habits, and they throw away speaker names, which export needs |
| Using a model to judge whether anyone is speaking | Dropped 40% of the dialogue lines |
| Keeping the top half by audio quality ranking | Still let through interjections and sound effects, and also dropped usable clips |
| Predicting "low quality" from ready-made speech quality scores (DNSMOS, NISQA, UTMOSv2, SQUIM, Audiobox Aesthetics), checked 2026-10 | They were built for phone calls, noise removal or synthetic speech. Alone or all together, they were clearly weaker than WavLM-large trained on our labels |
| Finding lines with two voices by pyannote's overlapped-speech detection | Barely better than a coin toss on our "low quality" labels |
| Fine-tuning the speech model for "low quality" | With a few hundred labels, it did worse than the model's frozen features |
| Judging quality on the original mix instead of the separated vocals | Clearly worse |
| Holding out one episode for blind labeling as a test | Blind labeling a whole episode takes too much effort. The machine's mistakes are corrected in the interface instead, and those labels are also training data |
