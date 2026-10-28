"""Write the prompts for the demo's pictures (pictures.json) as one Markdown file to paste from.

The file starts with a message to send once, with the five official illustrations attached, then
has one prompt per picture, each complete on its own so a long chat does not drift. Run from the
repository root:

    uv run python scripts/demo/make_pictures_prompts.py data/demo-pictures/PROMPTS.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    out = Path(sys.argv[1])
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    pictures = json.loads((HERE / "pictures.json").read_text(encoding="utf-8"))
    names = script["voices"]
    cast = "\n".join(f"- {text}" for text in pictures["characters"].values())
    parts = [
        "# Pictures for the online demo\n",
        "Save each picture as the file name in its heading, under one folder per episode "
        "(`ep01/01.png`). Pictures with no heading are not needed: that line keeps the picture "
        "before it.\n",
        "## Send this first, with the five official illustrations attached in this order\n",
        "```text\n"
        "I will ask you for a series of pictures for a short anime about a school festival "
        "café. Attached are the official illustrations of the five characters, in this order:\n"
        f"{cast}\n\n"
        f"{pictures['rules']}\n\n"
        f"Style for every picture: {pictures['style']}\n\n"
        f"Picture size: {pictures['size']}. Reply only with the picture each time.\n"
        "```\n",
    ]
    for episode, shots in pictures["episodes"].items():
        lines = script["episodes"][episode]
        parts.append(f"## {episode}\n")
        for number, (shot, (voice, style, text)) in enumerate(zip(shots, lines, strict=True), 1):
            if shot is None:
                continue
            speaker = names[voice.lstrip("+")]
            after = lines[number] if number < len(lines) else None
            together = ""
            if after and after[0].startswith("+"):
                other = names[after[0].lstrip("+")]
                together = f" At the same moment {other} says 「{after[2]}」 too."
            parts.append(
                f"### {episode}/{number:02d}.png\n\n"
                "```text\n"
                f"Picture {episode}-{number:02d}. Same five characters, same style as before.\n"
                f"Scene: {pictures['scenes'][shot['scene']]}\n"
                f"Shot: {shot['shot']}\n"
                f"In this moment {speaker} says 「{text}」 ({style} voice).{together} "
                "Show that mood; do not write the words.\n"
                "```\n"
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Prompts written to {out}")


if __name__ == "__main__":
    main()
