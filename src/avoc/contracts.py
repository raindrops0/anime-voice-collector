"""Requests and answers shared by the command line, web app and agent tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LabelChange(Input):
    clip: str
    label: str | None


class RejectChange(Input):
    clip: str
    reject: str
    on: StrictBool


class QualityChange(Input):
    clip: str
    unusable: StrictBool

    @model_validator(mode="before")
    @classmethod
    def old_name(cls, value: Any) -> Any:
        if isinstance(value, dict) and "overlap" in value and "unusable" not in value:
            return {("unusable" if k == "overlap" else k): v for k, v in value.items()}
        return value


class LabelBody(Input):
    clips: list[str] = Field(min_length=1)
    label: str | None = None
    """Character name, or "other". Empty means clear the label."""
    new_role: bool = False
    """Label as a newly made character that has no name yet. In that case `label` is not needed."""
    unusable: bool = False
    """Also mark as "low quality". Only works for target characters. When labeling as something
    else, or clearing the label, this is always turned off."""


class PrefetchBody(Input):
    clip: str


class ChangesBody(Input):
    changes: list[LabelChange | RejectChange | QualityChange]

    @model_validator(mode="after")
    def one_value_per_field(self) -> ChangesBody:
        seen = set()
        for change in self.changes:
            field = (
                f"reject:{change.reject}"
                if isinstance(change, RejectChange)
                else "label"
                if isinstance(change, LabelChange)
                else "unusable"
            )
            key = (change.clip, field)
            if key in seen:
                raise ValueError("A batch cannot change the same clip field twice")
            seen.add(key)
        return self


class RevertBody(Input):
    batches: list[int]
    """The steps to take back, by number, as the history list shows them."""


class RoleBody(Input):
    name: str
    new_name: str | None = None
    color: str | None = None
    target: bool | None = None


class AvatarBody(Input):
    name: str
    image: str
    """JPEG or PNG, as a data URL."""


class ExportBody(Input):
    roles: list[str]
    include_auto: bool = False
    form: str = "gpt-sovits"
    out: str


class AddBody(Input):
    video: str = ""
    subtitles: str = ""
    display_subtitles: str = ""
    offset: float | None = None
    styles: list[str] | None = None
    """The subtitle styles that hold the dialogue. None picks them automatically."""
    spoken: str | None = None
    """The language spoken. None takes it from the video's audio track."""
    name: str = ""
    """The episode's name, such as usagi-s1-ep01. Empty takes the next free `epNN`."""
    resume: str | None = None
    """Carry on with an episode that was not finished, using the files recorded for it."""


class QueuedEpisode(Input):
    name: str
    video: str
    subtitles: str
    display_subtitles: str = ""


class QueueBody(Input):
    """Several episodes, added one after another. The choices other than the files and the name
    are the same for all, as in AddBody."""

    episodes: list[QueuedEpisode] = []
    offset: float | None = None
    styles: list[str] | None = None
    spoken: str | None = None
    resume: list[str] = []
    """Carry on with these unfinished episodes instead, using the files recorded for each."""


class PairsBody(Input):
    videos: str
    subtitles: str
    display_subtitles: str = ""


class ForgetBody(Input):
    episode: str


class SubtitleStylesBody(Input):
    path: str


class PickBody(Input):
    kind: str
    """video, subtitles or folder"""
    current: str = ""
    """What the box holds now; the window opens in its folder."""


class PurposeBody(Input):
    purpose: str


class SpokenBody(Input):
    episode: str
    language: str


class CommandBody(Input):
    operation: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: int | None = Field(default=None, ge=0)


class SuggestionBody(ChangesBody):
    actor: str = Field(min_length=1, max_length=200)
    changes: list[LabelChange | RejectChange | QualityChange] = Field(min_length=1)


class AcceptBody(Input):
    suggestion: str


Status = Literal["confirmed", "auto", "review", "unlabeled", "skipped", "ignored", "likely_low"]


class GuessView(BaseModel):
    name: str
    p: float


class ClipView(BaseModel):
    id: str
    episode: str
    start: float
    end: float
    duration: float
    short: bool
    overlap: bool
    text: str
    display: str = ""
    scene: int
    voiced: bool
    label: str | None
    rejects: list[str]
    unusable: bool
    low: float | None
    guess: list[GuessView]
    familiar: bool | None
    status: Status
    maybe: bool = False
    spoken: str
    spoken_problem: str | None
    role: str | None


class CountsView(BaseModel):
    confirmed: int
    predicted: int
    to_check: int
    seconds: float
    low_seconds: float


class RoleView(CountsView):
    id: str
    name: str
    named: bool
    pattern: int
    target: bool
    color: str | None = None
    avatar: str | None = None


class SpokenView(BaseModel):
    language: str
    assumed: bool
    source: Literal["cut"] | None
    problem: str | None
    blocked: int


class EpisodeView(BaseModel):
    name: str
    video: bool
    offset: float | None
    offset_parts: int
    counts: dict[Status, int]
    work: int
    player: bool
    spoken: SpokenView


class WaitingView(BaseModel):
    lines: int
    others: int


class ModelView(BaseModel):
    labels: int
    roles: int
    seconds: float
    device: str
    familiar_threshold: float | None
    min_labels: int
    waiting: dict[str, WaitingView]
    auto_confidence: float


class SummaryView(BaseModel):
    revision: int
    workspace: str
    export_folder: str
    episodes: list[EpisodeView]
    skipped: dict[str, str]
    not_cut: list[str]
    roles: list[RoleView]
    other: CountsView
    model: ModelView
    quality: dict[str, Any]
    picture_pad: float
    can_undo: bool
    outdated: bool
    purpose: Literal["tts", "audio"] | None


class SkippedView(BaseModel):
    batch: int
    name: str


class ChangeView(BaseModel):
    batch: int | None
    undo: bool = False
    updated: list[ClipView]
    ripple: int
    state: SummaryView
    role: str | None = None
    skipped: list[SkippedView] = Field(default_factory=list)
    kept: int = 0


class JobView(BaseModel):
    id: str
    kind: str
    state: Literal["queued", "running", "cancelling", "done", "failed", "stopped", "interrupted"]
    result: dict[str, Any] | None
    error: str | None


class SnapshotView(BaseModel):
    state: SummaryView
    clips: list[ClipView]


class PageView(BaseModel):
    revision: int
    items: list[ClipView]
    next: str | None
