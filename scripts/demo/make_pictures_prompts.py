"""Write the prompts for the demo's pictures (pictures.json) as one Markdown file to work from.

The file starts with where things stand (which pictures exist, found on disk next to it) and how to
work, then has one prompt per picture that is still missing, each complete on its own, with the
official illustrations to attach: only those of the characters in the shot, since extra ones made
the model draw extra people. Names after the file pick episodes; none means all. The demo has
pictures for ep01 only. Run from the repository root, again whenever pictures are added:

    uv run python scripts/demo/make_pictures_prompts.py data/demo-pictures/PROMPTS.md ep01
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def cast_in(text: str, names: dict[str, str]) -> list[str]:
    """The characters named in `text`, in the order of pictures.json; "the girls" means all."""
    if "girls" in text:
        return list(names)
    return [key for key, name in names.items() if name in text]


def main() -> None:
    out = Path(sys.argv[1])
    folder = out.parent
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    pictures = json.loads((HERE / "pictures.json").read_text(encoding="utf-8"))
    wanted = sys.argv[2:] or list(pictures["episodes"])
    characters = pictures["characters"]
    names = {key: text.split(":")[0] for key, text in characters.items()}
    references = sorted((folder / "references").glob("0[1-9]-*.png"))
    if len(references) != len(characters):
        raise SystemExit(f"Expected {len(characters)} pictures in {folder / 'references'}")
    files = {
        key: f"references/{path.name}" for key, path in zip(characters, references, strict=True)
    }

    todo, done, samples = [], [], []
    for episode in wanted:
        for number, shot in enumerate(pictures["episodes"][episode], 1):
            if shot is None:
                continue
            name = f"{episode}/{number:02d}.png"
            if (folder / name).is_file():
                done.append(name)
            else:
                todo.append((episode, number, shot))
                if (folder / "samples" / f"{episode}-{number:02d}.png").is_file():
                    samples.append(name)

    parts = [
        "# Pictures for the online demo\n",
        "## Where things stand\n",
        f"- Wanted: {', '.join(wanted)}. Other episodes keep their waveform video; make no "
        "pictures for them.",
        f"- Finished: {len(done)}. Still to make: {len(todo)}, listed below in order.",
    ]
    if samples:
        parts.append(
            f"- Test pictures already in `samples/` for {', '.join(samples)}. If they pass the "
            "checks below, copy them to those names instead of drawing them again."
        )
    parts += [
        "",
        "## How to work\n",
        "1. For each heading below, attach only the reference pictures it lists, from this "
        "folder, and send its prompt. Make one picture at a time.",
        "2. Check the picture: the exact number of characters; each one matches their reference "
        "(face, hair, eyes, outfit, head accessory); every face, head accessory and raised hand "
        "lies between y=128 and y=896, because the top and bottom are cut off for the 16:9 "
        "video; no written words anywhere.",
        "3. If a check fails, ask for an edit of that picture that fixes only that, such as "
        "zooming the camera out so a head accessory fits.",
        "4. Save it as the file name in the heading (`ep01/01.png`), at 1536x1024. Lines with no "
        "heading need no picture: they keep the one before.",
        "",
        "Who is who:\n",
        *(f"- {text} File: `{files[key]}`." for key, text in characters.items()),
        "",
    ]
    for episode, number, shot in todo:
        voice, style, text = script["episodes"][episode][number - 1]
        speaker = script["voices"][voice.lstrip("+")]
        lines = script["episodes"][episode]
        together = ""
        if number < len(lines) and lines[number][0].startswith("+"):
            other = script["voices"][lines[number][0].lstrip("+")]
            together = f" At the same moment {other} says 「{lines[number][2]}」 too."
        cast = cast_in(f"{speaker} {shot['shot']}", names)
        shown = ", ".join(names[key] for key in cast)
        count = (
            f"This shot has EXACTLY {len(cast)} characters: {shown}. No other people, "
            "silhouettes or reflections."
        )
        parts.append(
            f"### {episode}/{number:02d}.png\n\n"
            f"Attach: {', '.join(f'`{files[key]}`' for key in cast)}\n\n"
            "```text\n"
            "One finished Japanese TV anime frame, not a collage. The attached pictures are the "
            "official designs of the characters, in this order: "
            f"{', '.join(names[key] for key in cast)}. They are design "
            "references, not pictures to edit.\n"
            + "".join(f"{characters[key]}\n" for key in cast)
            + f"{pictures['rules']}\n"
            f"{count}\n"
            f"Style: {pictures['style']}\n"
            f"{pictures['framing']}\n"
            f"Scene: {pictures['scenes'][shot['scene']]}\n"
            f"Shot: {shot['shot']}\n"
            f"The speaker is {speaker}. In this moment they say 「{text}」 ({style} voice)."
            f"{together} Show that mood; do not write the words.\n"
            "```\n"
        )
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Prompts written to {out}: {len(todo)} to make, {len(done)} finished")


if __name__ == "__main__":
    main()
