"""Media cuts and the workers that prepare picture and sound for playback."""

from __future__ import annotations

import contextlib
import os
import re
import threading
from pathlib import Path
from typing import Any

from avoc.language import say
from avoc.project import resolve_device
from avoc.video import PICTURE_PAD, copy_ready, cut_video, make_copy, media_name

SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")

CONTEXT_SECONDS = (5, 15)
"""When it is hard to tell who is speaking, the clip can be temporarily extended by this many
seconds before and after. Press L to step through the options. Only cut when the person asks."""
PREFETCH_SECONDS = 60.0
"""When one line is shown, first cut the dialogue clips within this many seconds before and after it
in the background, so jumping nearby does not wait. Then keep cutting the later ones."""
PREFETCH_WORKERS = 2
"""How many clips to cut at the same time in the background. Cutting one picture takes half a second
or more. With two running in parallel, about thirty lines before and after, within one minute, get
cut in about ten seconds."""


class Playback:
    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.stopped = threading.Event()
        self._cutting: dict[str, threading.Lock] = {}
        self._prefetch: list[tuple[str, str]] = []
        """The (kind, clip) pairs waiting to be cut in the background, nearest first. Each time the
        person moves to another line, the whole list is replaced."""
        self._prefetch_ready = threading.Condition()
        self._prefetchers: list[threading.Thread] = []
        self._copy_wanted: list[str] = []
        """Episodes whose whole-episode copy should be made, the one open first."""
        self._copy_ready = threading.Condition()
        self.copying: str | None = None
        self.copy_failed: dict[str, str] = {}
        """Episode name to why its copy could not be made; it then keeps the per-line cuts."""
        if owner.background:
            threading.Thread(target=self._copy_loop, daemon=True).start()

    @property
    def workspace(self) -> Any:
        return self.owner.workspace

    @property
    def lock(self) -> Any:
        return self.owner.lock

    @property
    def background(self) -> bool:
        return self.owner.background

    def close(self) -> None:
        self.stopped.set()
        with self._copy_ready:
            self._copy_ready.notify_all()
        with self._prefetch_ready:
            self._prefetch_ready.notify_all()

    def media(self, kind: str, clip_id: str, context: int = 0, fresh: bool = False) -> Path:
        """Cut and return the picture or vocals of one line. When `context` is not 0, this many
        seconds are added before and after (only a value from `CONTEXT_SECONDS`). The picture has
        `PICTURE_PAD` more at each end; the vocals do not. They are saved as a separate copy, and
        the normal copy is left alone. `fresh` throws away the saved cut first, for when it will
        not play."""
        clip = self.workspace.by_id.get(clip_id)
        if clip is None or not SAFE_ID.fullmatch(clip_id) or context not in (0, *CONTEXT_SECONDS):
            raise KeyError(clip_id)
        episode = self.workspace.episodes[clip.episode]
        name = media_name(kind, clip_id, context, PICTURE_PAD)
        target = Path(episode["directory"]) / "app_media" / name
        if target.exists() and not fresh:
            return target
        with self.lock:
            lock = self._cutting.setdefault(name, threading.Lock())
        with lock:
            if fresh:
                target.unlink(missing_ok=True)
            if target.exists():
                return target
            # The episode was loaded when the server started, but its folder may have been moved
            # or deleted since. Making the folders again would leave a stray episode folder
            # holding only these cuts, which takes the episode's name from the next one added.
            if not (Path(episode["directory"]) / "episode.json").is_file():
                raise FileNotFoundError(
                    say(
                        f"{clip.episode} 的文件夹不见了：{episode['directory']}。重启界面",
                        f"the folder of {clip.episode} is gone: {episode['directory']}. "
                        "Restart the interface",
                    )
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            start = max(0.0, clip.start - context)
            if kind == "audio":
                _cut_audio(Path(episode["vocals"]), start, clip.end + context, target)
            else:
                video = episode.get("video")
                if not video:
                    raise FileNotFoundError(say("这一集没有视频", "this episode has no video"))
                end = clip.end + context + PICTURE_PAD
                cut_video(Path(video), max(0.0, start - PICTURE_PAD), end, target)
        return target

    def prefetch(self, clip_id: str, seconds: float = PREFETCH_SECONDS) -> int:
        """Queue the dialogue lines of the same episode for background cutting, both video and
        vocals. First cut the ones within `seconds` of this line, nearest first. Then keep cutting
        forward in time to the end of the episode. Lines already cut are not queued. Each time the
        person moves to another line, the whole queue is replaced, so lines flipped past quickly do
        not waste time. Also asks for the episode's whole copy (`want_copy`); once it is ready,
        nothing is cut. Returns how many jobs were queued."""
        clip = self.workspace.by_id.get(clip_id)
        if clip is None:
            raise KeyError(clip_id)
        self.want_copy(clip.episode)
        episode = self.workspace.episodes[clip.episode]
        if self.player(clip.episode)["ready"]:
            # The page plays the whole-episode copy, so no line needs cutting.
            with self._prefetch_ready:
                self._prefetch = []
            return 0
        kinds = ("video", "audio") if episode.get("video") else ("audio",)
        folder = Path(episode["directory"]) / "app_media"
        same = [c for c in self.workspace.clips if c.episode == clip.episode]
        near = [c for c in same if c.end >= clip.start - seconds and c.start <= clip.end + seconds]
        near.sort(key=lambda c: abs(c.start - clip.start))
        taken = {c.id for c in near}
        later = sorted(
            (c for c in same if c.start > clip.start and c.id not in taken), key=lambda c: c.start
        )
        jobs = [
            (kind, c.id)
            for c in near + later
            for kind in kinds
            if not (folder / media_name(kind, c.id, pad=PICTURE_PAD)).exists()
        ]
        with self._prefetch_ready:
            self._prefetch = jobs
            while len(self._prefetchers) < PREFETCH_WORKERS:
                worker = threading.Thread(target=self._prefetch_loop, daemon=True)
                worker.start()
                self._prefetchers.append(worker)
            self._prefetch_ready.notify_all()
        return len(jobs)

    # Whole-episode copy

    def player(self, name: str) -> dict[str, Any]:
        """Whether the page can play this episode from its whole-episode copy (see
        `video.make_copy`), and whether it is being made now."""
        episode = self.workspace.episodes.get(name)
        ready = episode is not None and copy_ready(Path(episode["directory"]), episode)
        return {
            "ready": ready,
            "making": self.copying == name,
            "failed": self.copy_failed.get(name),
        }

    def want_copy(self, name: str) -> None:
        """Make the copy of the episode the person has open, then of the episode after it. Asking
        for another episode puts it first. Nothing happens without `background`."""
        if not self.background:
            return
        names = list(self.workspace.episodes)
        wanted = [name, *names[names.index(name) + 1 :][:1]] if name in names else []
        wanted = [
            n
            for n in wanted
            if n not in self.copy_failed and n != self.copying and not self.player(n)["ready"]
        ]
        with self._copy_ready:
            self._copy_wanted = wanted + [n for n in self._copy_wanted if n not in wanted]
            self._copy_ready.notify_all()

    def _copy_loop(self) -> None:
        """One copy at a time: each takes the whole CPU, or the GPU, for half a minute or more."""
        device = resolve_device("auto")
        while not self.stopped.is_set():
            with self._copy_ready:
                self._copy_ready.wait_for(lambda: self.stopped.is_set() or self._copy_wanted)
                if self.stopped.is_set():
                    return
                name = self._copy_wanted.pop(0)
            episode = self.workspace.episodes.get(name)
            if episode is None or copy_ready(Path(episode["directory"]), episode):
                continue
            self.copying = name
            try:
                make_copy(Path(episode["directory"]), episode, device)
            except Exception as exc:
                # Any error: it is shown for that episode, and the thread lives on for the next.
                self.copy_failed[name] = str(exc)
            finally:
                self.copying = None

    def _prefetch_loop(self) -> None:
        while not self.stopped.is_set():
            with self._prefetch_ready:
                self._prefetch_ready.wait_for(lambda: self.stopped.is_set() or self._prefetch)
                if self.stopped.is_set():
                    return
                kind, clip_id = self._prefetch.pop(0)
            # If a clip cannot be cut, report the error only when the person clicks that line.
            with contextlib.suppress(KeyError, FileNotFoundError, ValueError):
                self.media(kind, clip_id)


def _cut_audio(vocals: Path, start: float, end: float, target: Path) -> None:
    import soundfile as sf

    rate = sf.info(str(vocals)).samplerate
    wave, _ = sf.read(str(vocals), start=int(start * rate), stop=int(end * rate), always_2d=True)
    # The process number keeps two apps open on the same project from writing into one file.
    temporary = target.with_suffix(f".{os.getpid()}.part.wav")
    sf.write(str(temporary), wave, rate, subtype="PCM_16")
    temporary.replace(target)
