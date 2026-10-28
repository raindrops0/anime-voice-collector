"""Saved background jobs. Workers can finish even if the web server restarts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from avoc.exporting import run_export
from avoc.storage import connect


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Jobs:
    def __init__(self, path: Path, adding: Any = None) -> None:
        self.path = path
        self.adding = adding
        self._processes: dict[str, subprocess.Popen[Any]] = {}

    def create(self, kind: str, body: dict[str, Any], db: Any) -> dict[str, Any]:
        job = uuid4().hex
        db.execute(
            "INSERT INTO jobs (id,kind,state,body) VALUES (?,?,'queued',?)",
            (job, kind, json.dumps(body)),
        )
        return {"id": job, "kind": kind, "state": "queued", "result": None, "error": None}

    def launch(self, job: str) -> None:
        db = connect(self.path)
        try:
            kind, body = db.execute("SELECT kind,body FROM jobs WHERE id=?", (job,)).fetchone()
        finally:
            db.close()
        if kind == "add" and self.adding is not None:
            body = json.loads(body)
            try:
                with self.adding._start_lock:
                    if self.adding.job_id == job and self.adding.state == "running":
                        return
                    video, subtitles = Path(body["video"]), Path(body["subtitles"])
                    shown = (
                        Path(body["display_subtitles"]) if body.get("display_subtitles") else None
                    )
                    if self.adding.state == "running":
                        self.adding._remember(
                            body["name"],
                            video,
                            subtitles,
                            body.get("offset"),
                            body.get("styles"),
                            body.get("spoken"),
                            shown,
                            job_id=job,
                        )
                        self.adding._queue([body["name"]])
                    else:
                        if body.get("recover"):
                            self.adding._remember(
                                body["name"],
                                video,
                                subtitles,
                                body.get("offset"),
                                body.get("styles"),
                                body.get("spoken"),
                                shown,
                                job_id=job,
                            )
                            self.adding.carry_on(body["name"])
                            return
                        self.adding.start(
                            video,
                            subtitles,
                            body.get("offset"),
                            name=body["name"],
                            styles=body.get("styles"),
                            spoken=body.get("spoken"),
                            display_subtitles=shown,
                            job_id=job,
                        )
            except ValueError as exc:
                db = connect(self.path)
                try:
                    db.execute("UPDATE jobs SET state='failed',error=? WHERE id=?", (str(exc), job))
                finally:
                    db.close()
                raise
            return
        self._processes = {k: p for k, p in self._processes.items() if p.poll() is None}
        self._processes[job] = subprocess.Popen(
            [sys.executable, "-m", "avoc.jobs", str(self.path.resolve()), job],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    def get(self, job: str) -> dict[str, Any]:
        db = connect(self.path)
        try:
            row = db.execute(
                "SELECT kind,state,result,error,pid FROM jobs WHERE id=?", (job,)
            ).fetchone()
            if row is None:
                raise ValueError("No such job")
            kind, state, result, error, pid = row
            if state in ("running", "cancelling") and not alive(pid):
                changed = db.execute(
                    "UPDATE jobs SET state='interrupted' WHERE id=? AND pid IS ? "
                    "AND state IN ('running','cancelling')",
                    (job, pid),
                ).rowcount
                if changed:
                    state = "interrupted"
                else:
                    kind, state, result, error, pid = db.execute(
                        "SELECT kind,state,result,error,pid FROM jobs WHERE id=?",
                        (job,),
                    ).fetchone()
            return {
                "id": job,
                "kind": kind,
                "state": state,
                "result": json.loads(result) if result else None,
                "error": error,
            }
        finally:
            db.close()

    def cancel(self, job: str) -> dict[str, Any]:
        current = self.get(job)
        if (
            current["kind"] == "add"
            and current["state"] == "running"
            and self.adding is not None
            and self.adding.job_id == job
        ):
            self.adding.stop()
            return self.get(job)
        db = connect(self.path)
        try:
            db.execute(
                "UPDATE jobs SET state=CASE WHEN state='queued' THEN 'stopped' "
                "ELSE 'cancelling' END WHERE id=? AND state IN ('queued','running')",
                (job,),
            )
        finally:
            db.close()
        return self.get(job)

    def resume(self, job: str) -> dict[str, Any]:
        current = self.get(job)
        if current["state"] == "queued":
            self.launch(job)
            return self.get(job)
        db = connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            body = json.loads(db.execute("SELECT body FROM jobs WHERE id=?", (job,)).fetchone()[0])
            body["recover"] = True
            changed = db.execute(
                "UPDATE jobs SET state='queued',error=NULL,pid=NULL,body=? WHERE id=? "
                "AND state IN ('failed','stopped','interrupted')",
                (json.dumps(body), job),
            ).rowcount
            db.commit()
        finally:
            db.close()
        if changed:
            self.launch(job)
        return self.get(job)

    def all(self) -> list[dict[str, Any]]:
        db = connect(self.path)
        try:
            ids = [r[0] for r in db.execute("SELECT id FROM jobs ORDER BY rowid DESC LIMIT 100")]
        finally:
            db.close()
        return [self.get(job) for job in ids]


def work(path: Path, job: str) -> None:
    db = connect(path)
    try:
        while True:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT kind,body FROM jobs WHERE id=? AND state='queued'", (job,)
            ).fetchone()
            if row is None:
                return
            others = db.execute(
                "SELECT pid FROM jobs WHERE kind='add' "
                "AND state IN ('running','cancelling') AND id!=?",
                (job,),
            ).fetchall()
            if row[0] == "add" and any(alive(pid) for (pid,) in others):
                db.rollback()
                time.sleep(0.5)
                continue
            db.execute("UPDATE jobs SET state='running',pid=? WHERE id=?", (os.getpid(), job))
            db.commit()
            break

        def cancelled() -> bool:
            return (
                db.execute("SELECT state FROM jobs WHERE id=?", (job,)).fetchone()[0]
                == "cancelling"
            )

        kind, body = row[0], json.loads(row[1])
        if kind == "export":
            result = run_export(body, job, cancelled)
        elif kind == "add":
            from avoc.pipeline import add_episode
            from avoc.project import validate_name

            folder = path.parent.parent / "episodes" / validate_name(body["name"])
            if body.get("recover") and folder.is_dir() and not (folder / "episode.json").exists():
                from avoc.adding import _remove

                if folder.resolve().parent != (path.parent.parent / "episodes").resolve():
                    raise ValueError("The unfinished episode folder is outside this workspace")
                if not _remove(folder):
                    raise ValueError("Cannot remove the unfinished episode files; try again later")

            def report(line: str) -> None:
                if cancelled():
                    raise InterruptedError("Adding stopped")
                db.execute(
                    "UPDATE jobs SET result=? WHERE id=?", (json.dumps({"progress": line}), job)
                )

            result = add_episode(
                path.parent.parent,
                Path(body["video"]),
                Path(body["subtitles"]),
                name=body["name"],
                offset=body.get("offset"),
                styles=body.get("styles"),
                spoken=body.get("spoken"),
                report=report,
                display_subtitles=Path(body["display_subtitles"])
                if body.get("display_subtitles")
                else None,
            )
            db.execute("UPDATE state SET revision=revision+1 WHERE singleton=1")
        else:
            raise ValueError(f"Unknown job kind: {kind}")
        db.execute(
            "UPDATE jobs SET state='done',result=?,error=NULL WHERE id=?", (json.dumps(result), job)
        )
    except BaseException as exc:
        db.rollback()
        state = "stopped" if isinstance(exc, InterruptedError) else "failed"
        db.execute("UPDATE jobs SET state=?,error=? WHERE id=?", (state, str(exc), job))
    finally:
        db.close()


if __name__ == "__main__":
    work(Path(sys.argv[1]), sys.argv[2])
