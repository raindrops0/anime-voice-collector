# Roadmap

This page covers who the tool is for, the direction it takes, and what is planned next. Settled choices are in [DECISIONS.md](DECISIONS.md). How things work now is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## Who it is for

- Mainly, people who want to train a voice model for one character (GPT-SoVITS, RVC and so on), and who need clean audio of that character speaking alone, with the line in the language spoken.
- Second, people who want to find all of a character's lines.

## Direction

The current approach (cut along subtitle lines, name a few lines, let a small classifier sort the rest and retrain after every correction) is settled in [DECISIONS.md](DECISIONS.md#settled). Beyond it:

- Use the order of neighboring lines, the subtitle text, and the lip movement in the picture to tell people apart.
- Once labels reach several thousand, consider fine-tuning the voiceprint model. At that point, the "do not fine-tune the models" item in [DECISIONS.md](DECISIONS.md#goal-and-scope) must be changed first.

## Labeling interface

The first version is done, with four views: Groups, Scenes, Characters and Export. How to use each view and its shortcuts are in [USAGE.md](USAGE.md#the-views). How the machine guesses and where the labels are stored is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md#labeling-and-correction-interface). The design rules that must be kept are in [UI_DESIGN.md](UI_DESIGN.md).

Planned:

- **Switch what the voices are for midway.** It is chosen once, before the first episode ([USAGE.md](USAGE.md#the-views)). Going from reading text aloud to sound only loses nothing, since Export can already write sound only. The other way needs every episode cut from subtitles in the spoken language; episodes cut from a translation would have to be added again.

- **Regroup by itself, without a refresh.** Groups are worked out only when the view loads, and stay put while labeling. But each label retrains the machine, so lines it is now confident about, and lines left alone in their group, would no longer be in Groups. Today they go away only on a refresh, and then the groups change all at once. Proposed way:
  - Regroup after a set amount of work, not on a timer. The groups can only change when labels do, and a timer could fire while the person is ticking lines. Regroup once 20 lines have been labeled since the last time, or once the machine has taken over 10 lines (the `ripple` count each label already returns), whichever comes first. A target character just reaching 10 confirmed lines, when guessing starts, sets this off at once.
  - Fetch the new groups in the background, and swap them in only at a calm moment: nothing is ticked, and the group with the selected line has just been finished. Otherwise wait for that moment.
  - Keep the screen steady: a new group that shares most of its lines with an old one takes that one's place and number. Groups that are all labeled leave. A short note says how many lines the machine took over, and that they are now in Characters.
  - Undo after a regroup gives the label back, but the line comes back into a group only at the next regroup.

- **Go from a step in the history to its lines.** The history next to Undo ([USAGE.md](USAGE.md#undo-shortcuts-and-page-settings)) names each step's first line, but clicking it does nothing yet. Proposed way: open the step's episode in Scenes with that line selected, and tick the parts of the list that hold it, so it is not hidden by the filter.

- **A panel to switch workspaces and see them all at once.** Today each workspace is opened by its own `avoc app` ([USAGE.md](USAGE.md#starting-the-app)). The panel lists every known workspace with a short summary (episodes, clips, confirmed lines per target character, last opened) and opens one with a click. Proposed way:
  - The running server closes its workspace and loads the chosen one, so one process still shows one workspace at a time, on one port. Serving several workspaces from one process was weighed and not chosen: they would all stop together, `--reload` would restart them all, and a second `avoc app` from another code folder or with other `--model` choices would silently run with the first one's.
  - Workspaces become known when they are opened, kept in a list outside any workspace. A folder that is gone is shown as missing, not dropped by itself.
  - Not decided yet: whether switching waits for, or stops, an episode being added; and which browser settings stay per workspace (today they are kept per port, such as whether the guide was seen).

## Platforms

Only Windows has been tested. Linux and macOS already have first support in the install setup ([TOOLS.md](TOOLS.md)), and testing them is planned. A one-click Windows package may come later.
