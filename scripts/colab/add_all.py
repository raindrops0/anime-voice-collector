"""Add every episode in a workspace's `input/` folder, on a cloud GPU (add_episodes.ipynb).

The workspace lives in a synced folder, such as Google Drive, and is copied to a fast local folder
to work in; after each episode the changes are copied back, so a dropped session loses at most the
episode it was on. Run it again to carry on. Videos and main subtitles go in `input/`, matched by
episode number as in the app's "Several, one after another"; subtitles only shown while labeling
can go in `input/display/`. Every file stays inside the workspace, so the whole folder can be
downloaded and opened with `avoc app` on a computer without a GPU. Options after the two folders
are given to every `avoc add`, such as `--offset 0` or `--spoken ja`. Run from the repository root:

    uv run python scripts/colab/add_all.py /content/drive/MyDrive/avoc-workspace /content/work
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from avoc.batch import pair


def mirror(source: Path, target: Path) -> None:
    """Copy the files in `source` that `target` lacks or has in another size or change time.
    Nothing is deleted."""
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        copy = target / path.relative_to(source)
        info = path.stat()
        if copy.is_file():
            known = copy.stat()
            if known.st_size == info.st_size and int(known.st_mtime) == int(info.st_mtime):
                continue
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copy)


def plan(work: Path) -> list[tuple[str, list[str]]]:
    """Each episode to add, as its name and the arguments of `avoc add`. Numbers with more or fewer
    than one video and one main subtitle file are left out, with the reason."""
    inputs, display = work / "input", work / "input" / "display"
    found = pair(str(inputs), str(inputs), str(display) if display.is_dir() else "")
    for path in found["no_number"]:
        print(f"Left out, no episode number in the name: {Path(path).name}")
    episodes = []
    for entry in found["episodes"]:
        name = f"ep{entry['number']:02d}"
        videos, subtitles = entry["videos"], entry["subtitles"]
        extra = entry.get("display_subtitles", [])
        if len(videos) != 1 or len(subtitles) != 1 or len(extra) > 1:
            print(
                f"Left out {name}: {len(videos)} videos, {len(subtitles)} main subtitles and "
                f"{len(extra)} display subtitles; it needs one video and one main subtitle file"
            )
            continue
        arguments = [videos[0], "--subs", subtitles[0], "--name", name]
        if extra:
            arguments += ["--display-subs", extra[0]]
        episodes.append((name, arguments))
    return episodes


def main() -> None:
    kept, work, options = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    if not (kept / "input").is_dir():
        raise SystemExit(f"Put the videos and subtitles in {kept / 'input'} first")
    print(f"Copying {kept} to {work}")
    mirror(kept, work)
    episodes = plan(work)
    failed = []
    for number, (name, arguments) in enumerate(episodes, 1):
        print(f"\n[{number}/{len(episodes)}] {name}", flush=True)
        command = [sys.executable, "-m", "avoc", "add", str(work), *arguments, *options]
        if subprocess.run(command, check=False).returncode != 0:
            failed.append(name)
        mirror(work, kept)
    print(f"\nDone: {len(episodes) - len(failed)} of {len(episodes)} episodes are in {kept}")
    if failed:
        raise SystemExit(f"Failed: {', '.join(failed)}. Run again to carry on with them")


if __name__ == "__main__":
    main()
