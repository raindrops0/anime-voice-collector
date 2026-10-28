"""Write an export from a saved selection, without holding the workspace lock."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from avoc.project import free_export_folder
from avoc.stages.export import export, summarize


@dataclass(frozen=True)
class ExportClip:
    id: str
    episode: str
    start: float
    end: float


def run_export(
    plan: dict[str, Any], job: str | None = None, cancelled: Any = None
) -> dict[str, Any]:
    out = Path(plan["out"])
    receipt = out / "export.json"
    if job and receipt.is_file():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved.get("job") == job and all((out / p).is_file() for p in saved["files"]):
            return {**saved["result"], "next": str(free_export_folder(Path(plan["workspace"])))}
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("The export folder is not empty; choose another folder")
    stage = out.parent / f".{out.name}.{job or uuid4().hex}.partial"
    if stage.resolve().parent != out.resolve().parent:
        raise ValueError("The temporary export must stay beside the chosen folder")
    assigned = {name: [ExportClip(**c) for c in clips] for name, clips in plan["assigned"].items()}
    written = export(
        assigned,
        {n: Path(p) for n, p in plan["vocals"].items()},
        stage,
        folders=plan["folders"],
        cancelled=cancelled,
    )
    ids = {(c.episode, c.start, c.end): c.id for clips in assigned.values() for c in clips}
    if plan["form"] == "gpt-sovits":
        lines = []
        for item in written:
            text = plan["texts"][ids[item.episode, item.start, item.end]]
            text = text.replace("|", " ").replace("\n", " ")
            final = out / item.path.relative_to(stage)
            lines.append(
                f"{final}|{plan['folders'][item.name]}|{plan['languages'][item.episode]}|{text}"
            )
        (stage / "train.list").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if plan["rejected"]:
        with (stage / "rejected.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["role", "episode", "start", "end", "reason", "subtitle", "text"])
            for r in plan["rejected"]:
                c = r["clip"]
                writer.writerow(
                    [
                        r["role"],
                        c["episode"],
                        c["start"],
                        c["end"],
                        r["reason"],
                        c["text"],
                        r["text"],
                    ]
                )
    if cancelled is not None and cancelled():
        raise InterruptedError("Export stopped")
    result = {
        "out": str(out),
        **summarize(written),
        "revision": plan["revision"],
        "rejected": dict(Counter(r["reason"] for r in plan["rejected"])),
    }
    (stage / "export.json").write_text(
        json.dumps(
            {
                "job": job,
                "result": result,
                "files": [str(item.path.relative_to(stage)) for item in written],
                "characters": plan["folders"],
                "selection": plan["assigned"],
            }
        ),
        encoding="utf-8",
    )
    # The chosen directory becomes visible only after all of its files are ready.
    if out.exists():
        out.rmdir()
    stage.rename(out)
    return {**result, "next": str(free_export_folder(Path(plan["workspace"])))}
