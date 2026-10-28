"""Backend of the labeling interface: label records, dialogue text, retraining, and the API."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from avoc.app.server import AppState, create_app
from avoc.labels import OTHER, LabelStore
from avoc.model import train_and_predict
from avoc.stages.text_language import syllables
from avoc.workspace import Clip, text_for
from tests.fixtures import episode


@pytest.fixture(autouse=True)
def guess_from_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workspaces here have a handful of lines, so the app guesses a target from one of them."""
    monkeypatch.setattr("avoc.service.MIN_GUESS_LABELS", 1)


def test_store_keeps_every_step_and_undoes_whole_batches(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}, {"clip": "b", "label": "A"}], source="import:x")
    assert not store.can_undo()
    store.apply([{"clip": "a", "label": "B"}, {"clip": "c", "reject": "A", "on": True}])
    assert store.labels == {"a": "B", "b": "A"}
    assert store.rejects["c"] == {"A"}
    assert store.apply([{"clip": "a", "label": "B"}]) is None
    store.undo()
    assert store.labels == {"a": "A", "b": "A"}
    assert store.rejects["c"] == set()
    assert not store.can_undo()

    again = LabelStore(tmp_path / "labels")
    assert again.labels == store.labels
    # B was created by the batch that was undone. After the undo it has no clips,
    # so it is removed too.
    assert [r["name"] for r in again.roles] == ["A"]


def test_rename_into_an_existing_role_merges_them(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "红毛"}, {"clip": "b", "label": "Nice Nature"}])
    store.rename_role("红毛", "Nice Nature")
    assert set(store.labels.values()) == {"Nice Nature"}
    assert [r["name"] for r in LabelStore(tmp_path / "labels").roles] == ["Nice Nature"]
    with pytest.raises(ValueError, match="cannot be empty"):
        store.rename_role("Nice Nature", "__unclear__")


def test_renaming_a_role_with_no_clips_can_be_undone(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.apply([{"clip": "a", "label": "B"}])
    assert store.rename_role("A", "C") is not None
    store.undo()
    assert {r["name"] for r in store.roles} == {"A", "B"}
    assert store.labels == {"a": "B"}


def test_retired_labels_count_as_unlabeled(tmp_path: Path) -> None:
    """A retired old label (such as an unsure one) counts as no label when replayed, imported, or
    undone. Undo also does not get stuck."""
    folder = tmp_path / "labels"
    folder.mkdir()
    lines = [
        {"batch": 1, "time": "t", "source": "human", "undo_of": None,
         "changes": [{"clip": "b", "before": None, "after": "teo"}]},
        {"batch": 2, "time": "t", "source": "human", "undo_of": None,
         "changes": [{"clip": "a", "before": None, "after": "__multiple__"}]},
    ]  # fmt: skip
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    store = LabelStore(folder)
    assert store.labels == {"b": "teo"}
    assert [r["name"] for r in store.roles] == ["teo"]
    assert store.apply([{"clip": "c", "label": "__unclear__"}]) is None
    # Undoing the batch that only touched retired labels: no real change, but it is still recorded
    # as undone, so earlier batches can be undone next.
    store.undo()
    assert store.labels == {"b": "teo"}
    store.undo()
    assert store.labels == {}


def test_a_role_can_start_without_a_name_and_keeps_its_pattern(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    first = store.new_role()
    second = store.new_role()
    assert (first, second) == ("Character 1", "Character 2")
    assert [r["named"] for r in store.roles] == [True, False, False]
    patterns = [r["pattern"] for r in store.roles]
    assert patterns == [0, 1, 2]

    store.apply([{"clip": "b", "label": first}])
    store.rename_role(first, "麦昆")
    renamed = store.role("麦昆")
    assert renamed is not None and renamed["named"] is True and renamed["pattern"] == 1

    # A character that was merged away does not have its pattern number reused by the next new one.
    store.rename_role("麦昆", "A")
    assert store.role(store.new_role())["pattern"] == 3  # type: ignore[index]


def test_undo_puts_the_role_list_back_too(tmp_path: Path) -> None:
    """When undoing a batch, the characters that batch also created, renamed, or merged are changed
    back too, so no empty character is left."""
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.update_role("A", target=False)

    # A character created by typing a new name is also removed once undo leaves it with no clips.
    store.apply([{"clip": "b", "label": "B"}])
    store.undo()
    assert [r["name"] for r in store.roles] == ["A"]

    # The same goes for an unnamed character made with the N key.
    fresh = store.new_role()
    store.apply([{"clip": "b", "label": fresh}], cast={"unnamed": [fresh]})
    store.rename_role(fresh, "麦昆")
    store.undo()
    role = store.role(fresh)
    assert role is not None and role["named"] is False and store.role("麦昆") is None
    assert store.labels["b"] == fresh
    store.undo()
    assert [r["name"] for r in store.roles] == ["A"]

    # After undoing a merge, the character that was merged away comes back unchanged. The one that
    # was kept also gets its original target status back.
    store.apply([{"clip": "c", "label": "C"}])
    store.rename_role("C", "A")
    assert store.role("A")["target"] is True  # type: ignore[index]
    store.undo()
    assert [r["name"] for r in store.roles] == ["A", "C"]
    assert store.role("A")["target"] is False  # type: ignore[index]
    assert store.labels == {"a": "A", "c": "C"}
    assert [r["name"] for r in LabelStore(tmp_path / "labels").roles] == ["A", "C"]


def test_an_old_cast_without_patterns_gets_them_in_order(tmp_path: Path) -> None:
    folder = tmp_path / "labels"
    folder.mkdir()
    (folder / "cast.json").write_text(
        '{"schema": "cast.v1", "roles": [{"name": "A", "color": "#000", "trainable": true,'
        ' "avatar": null}, {"name": "B", "color": "#111", "trainable": true, "avatar": null}]}',
        encoding="utf-8",
    )
    store = LabelStore(folder)
    assert [(r["named"], r["pattern"]) for r in store.roles] == [(True, 0), (True, 1)]
    assert store.targets() == ["A", "B"]


def test_other_remembers_the_targets_it_was_judged_against(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.apply([{"clip": "o", "label": OTHER}])
    assert store.against["o"] == {"A"}

    store.apply([{"clip": "b", "label": "B"}])
    store.update_role("A", target=False)
    store.apply([{"clip": "o", "label": OTHER}])
    assert store.against["o"] == {"B"}
    store.undo()
    assert store.against["o"] == {"A"}
    assert LabelStore(tmp_path / "labels").against["o"] == {"A"}

    store.update_role("A", target=True)
    store.rename_role("A", "teo")
    assert store.against["o"] == {"teo"}


def test_an_older_step_can_be_taken_back_alone_and_later_changes_win(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}, {"clip": "b", "label": "A"}])
    store.apply([{"clip": "c", "label": "B"}])
    store.apply([{"clip": "a", "label": "B"}])
    batch, report = store.revert([1])
    assert batch is not None and batch["undo_of"] == 1
    # Line a was labeled again by step 3, so it keeps that.
    assert store.labels == {"a": "B", "c": "B"}
    assert report == {"skipped": [], "kept": 1}
    first = next(e for e in store.history() if e["batch"] == 1)
    assert first["undone_by"] == 4 and first["why_not"] is not None

    # Taking back the take-back puts step 1 back; it is a step of its own, which Z takes back.
    store.revert([4])
    assert store.labels == {"a": "B", "b": "A", "c": "B"}
    assert next(e for e in store.history() if e["batch"] == 1)["undone_by"] is None
    assert store.undo_target() == 5
    store.undo()
    assert store.labels == {"a": "B", "c": "B"}
    # Z skips the undo it wrote itself. Step 4 is in effect again, so Z takes it back next.
    store.undo()
    assert store.labels == {"a": "B", "b": "A", "c": "B"}
    store.undo()
    assert store.labels == {"a": "A", "b": "A", "c": "B"}
    assert LabelStore(tmp_path / "labels").labels == store.labels


def test_going_back_to_a_step_takes_back_the_ones_after_it_as_one(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.apply([{"clip": "b", "label": "B"}])
    store.rename_role("B", "Bee")
    store.apply([{"clip": "c", "label": "Bee"}])
    batch, _ = store.revert([2, 3, 4])
    assert batch is not None and batch["undo_of"] == [4, 3, 2]
    assert store.labels == {"a": "A"}
    assert [r["name"] for r in store.roles] == ["A"]

    # Taking that back brings all three back, the character included, with its own pattern.
    store.revert([batch["batch"]])
    assert store.labels == {"a": "A", "b": "Bee", "c": "Bee"}
    bee = store.role("Bee")
    assert bee is not None and bee["pattern"] == 1
    again = LabelStore(tmp_path / "labels")
    assert again.labels == store.labels and [r["name"] for r in again.roles] == ["A", "Bee"]


def test_undoing_a_rename_alone_takes_later_lines_along(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.rename_role("A", "teo")
    store.apply([{"clip": "b", "label": "teo"}])
    store.revert([2])
    assert store.labels == {"a": "A", "b": "A"}
    assert [r["name"] for r in store.roles] == ["A"]


def test_a_step_whose_name_is_taken_now_is_left_out(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "label": "A"}])
    store.apply([{"clip": "b", "label": "B"}])
    store.undo()  # B had only this line, so it is removed.
    store.apply([{"clip": "c", "label": "B"}])  # A new B.
    batch, report = store.revert([3])
    assert batch is None and report["skipped"] == [{"batch": 3, "name": "B"}]
    assert store.labels == {"a": "A", "c": "B"}
    with pytest.raises(ValueError, match="already taken back"):
        store.revert([2])


def test_an_undo_from_an_older_version_cannot_be_taken_back(tmp_path: Path) -> None:
    folder = tmp_path / "labels"
    folder.mkdir()
    lines = [
        {"batch": 1, "time": "t", "source": "human", "undo_of": None,
         "changes": [{"clip": "a", "before": None, "after": "A"}], "cast": {"created": ["A"]}},
        {"batch": 2, "time": "t", "source": "undo", "undo_of": 1,
         "changes": [{"clip": "a", "before": "A", "after": None}]},
    ]  # fmt: skip
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    store = LabelStore(folder)
    assert store.history()[0]["why_not"] is not None
    assert not store.can_undo()


def test_text_is_found_by_overlap_not_exact_time() -> None:
    lines = [(1.0, 3.0, "你好"), (1.0, 3.0, "こんにちは"), (5.0, 6.0, "再见")]
    starts = [line[0] for line in lines]
    assert text_for(lines, starts, 1.2, 2.9) == "你好 / こんにちは"
    assert text_for(lines, starts, 4.0, 4.5) == ""
    assert text_for(lines, starts, 5.8, 7.0) == ""


def test_short_clips_and_clips_of_few_syllables_are_skipped() -> None:
    def clip(end: float, syllables: int | None) -> Clip:
        return Clip("x", "ep1", 0.0, end, "", 0, None, syllables=syllables)

    assert clip(0.8, 10).skipped
    assert clip(0.8, None).skipped
    assert clip(2.0, 2).skipped
    assert not clip(2.0, 3).skipped
    assert not clip(1.0, None).skipped


def test_syllables_are_counted_by_sound_not_by_letter() -> None:
    assert syllables("きょう", "ja") == 2  # kyo, u
    assert syllables("うおーっ！", "ja") == 2
    assert syllables("テイオー？", "ja") == 3
    assert syllables("えっ 僕？", "ja") == 3  # A kanji counts as two.
    assert syllables("我知道", "zh") == 3
    assert syllables("no fear", "en") == 2


def _answers(**names: list[int]) -> dict[int, frozenset[str]]:
    """Rows surely labeled each name; `other=` for "other"."""
    return {r: frozenset({OTHER if n == "other" else n}) for n, rows in names.items() for r in rows}


def test_a_voice_unlike_any_known_role_is_not_trusted() -> None:
    rng = np.random.default_rng(0)
    centers = np.eye(3)
    rows = [centers[i % 2] + rng.normal(0, 0.05, 3) for i in range(40)]
    features = np.array([*rows, centers[2] + rng.normal(0, 0.05, 3)])
    features /= np.linalg.norm(features, axis=1, keepdims=True)

    def answers(n: int) -> dict[int, frozenset[str]]:
        return _answers(A=list(range(0, n, 2)), B=list(range(1, n, 2)))

    few = train_and_predict(features, ["A", "B"], answers(4), {}, min_labels=1)
    assert few.threshold is None
    assert few.guesses[40].familiar is None

    trained = train_and_predict(features, ["A", "B"], answers(40), {})
    assert trained.threshold is not None
    assert trained.guesses[39].names[0] == "B"
    assert trained.guesses[39].familiar is True
    assert trained.guesses[40].familiar is False


def test_no_guess_before_anyone_is_known_not_to_be_the_target() -> None:
    # Only one character labeled and no "other" yet: nothing to compare against, so no line is
    # called theirs at 100%.
    features = np.eye(3)[[0, 0, 1, 2]]
    assert train_and_predict(features, ["A"], _answers(A=[0, 1]), {}, min_labels=1).guesses == {}
    assert train_and_predict(
        features, ["A"], _answers(A=[0, 1], other=[2]), {}, min_labels=1
    ).guesses


def test_no_guess_before_enough_of_the_targets_lines_are_confirmed() -> None:
    features = np.eye(2)[[0] * 12 + [1] * 3]
    few = _answers(A=list(range(9)), other=[12, 13, 14])
    assert train_and_predict(features, ["A"], few, {}).guesses == {}
    enough = _answers(A=list(range(10)), other=[13, 14])
    assert train_and_predict(features, ["A"], enough, {}).guesses[11].names[0] == "A"
    # A target still waiting does not stop another from being guessed.
    guesses = train_and_predict(features, ["A", "B"], enough | _answers(B=[12]), {}).guesses
    assert guesses[11].names[0] == "A"
    assert guesses[11].p("B") == 0.0


def test_chances_add_up_to_one_and_a_rejected_name_gets_none() -> None:
    rng = np.random.default_rng(2)
    features = np.array([np.eye(3)[i // 10] + rng.normal(0, 0.1, 3) for i in range(30)])
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    answers = _answers(A=list(range(10)), B=list(range(10, 20)), other=list(range(20, 30)))
    trained = train_and_predict(features, ["A", "B"], answers, {5: {"A"}})
    for guess in trained.guesses.values():
        assert sum(guess.probabilities) == pytest.approx(1, abs=1e-3)
    assert trained.guesses[5].p("A") == 0.0
    assert trained.guesses[5].names[0] in ("B", OTHER)


def test_with_one_target_it_is_the_old_logistic_regression() -> None:
    from sklearn.linear_model import LogisticRegression

    from avoc.model import STRENGTH

    rng = np.random.default_rng(3)
    features = rng.normal(0, 1, (60, 5))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    target = features[:, 0] + rng.normal(0, 0.3, 60) > 0
    pos, neg = list(np.flatnonzero(target)), list(np.flatnonzero(~target))
    trained = train_and_predict(features, ["A"], _answers(A=pos, other=neg), {}, min_labels=1)
    old = LogisticRegression(C=STRENGTH, max_iter=3000, tol=1e-10)
    old.fit(features, target)
    expected = old.predict_proba(features)[:, 1]
    got = np.array([trained.guesses[r].p("A") for r in range(60)])
    assert np.abs(got - expected).max() < 2e-3


def test_other_only_counts_against_the_targets_of_its_time() -> None:
    # A and C have different voices. C's clips were labeled "other" while C was not yet a target.
    # C was made a target later, so those labels mean "C or other", not "not C".
    rng = np.random.default_rng(1)
    centers = np.eye(3)
    features = np.array([centers[i // 10] + rng.normal(0, 0.05, 3) for i in range(30)])
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    a, b, c = list(range(10)), list(range(10, 20)), list(range(20, 30))
    only_a = train_and_predict(features, ["A"], _answers(A=a, other=b + c), {})
    assert only_a.guesses[25].names[0] == "__other__"
    old_other = {r: frozenset({OTHER, "C"}) for r in c[2:]}
    answers = _answers(A=a, other=b, C=c[:2]) | old_other
    with_c = train_and_predict(features, ["A", "C"], answers, {}, min_labels=1)
    assert with_c.guesses[25].names[0] == "C"
    # Had they counted as surely "other", C would lose its own clips.
    as_other = _answers(A=a, other=b + c[2:], C=c[:2])
    assert (
        train_and_predict(features, ["A", "C"], as_other, {}, min_labels=1).guesses[25].names[0]
        == OTHER
    )


@pytest.mark.skipif("not __import__('torch').cuda.is_available()", reason="no NVIDIA GPU")
def test_the_gpu_gives_the_same_chances_as_the_cpu() -> None:
    rng = np.random.default_rng(4)
    features = np.array([np.eye(3)[i // 10] + rng.normal(0, 0.2, 3) for i in range(30)])
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    answers = _answers(A=list(range(10)), B=list(range(10, 15)), other=list(range(20, 30)))
    answers |= {r: frozenset({"B", OTHER}) for r in range(15, 20)}
    cpu = train_and_predict(features, ["A", "B"], answers, {}, min_labels=1, device="cpu")
    gpu = train_and_predict(features, ["A", "B"], answers, {}, min_labels=1, device="cuda")
    for row in range(30):
        for name in ("A", "B", OTHER):
            assert gpu.guesses[row].p(name) == pytest.approx(cpu.guesses[row].p(name), abs=1e-3)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "episodes").mkdir(parents=True)
    a, b = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]
    # Just long enough not to be skipped.
    spans = [{"start": 2.0 * i, "end": 2.0 * i + 1.0} for i in range(6)]
    episode(root / "episodes", "ep1", np.array([a, a, a, b, b, b], dtype=float), spans)
    return root


def test_text_follows_the_line_and_overlap_follows_the_voice(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "episodes").mkdir(parents=True)
    subtitles = tmp_path / "ja.srt"
    subtitles.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nこんにちは\n\n"
        "2\n00:00:05,000 --> 00:00:07,000\nはい\n\n"
        "3\n00:00:06,500 --> 00:00:08,000\nうん\n",
        encoding="utf-8",
    )
    spans = [
        # The line shows 1 to 4 s, the voice is only 2.6 to 3.4 s: by its own time, too little of
        # the line falls inside the clip for the text to count.
        {"start": 2.6, "end": 3.4, "line_start": 1.0, "line_end": 4.0},
        # Lines 2 and 3 share 0.5 s on screen, but their voices only touch.
        {"start": 5.2, "end": 6.5, "line_start": 5.0, "line_end": 7.0},
        {"start": 6.5, "end": 7.8, "line_start": 6.5, "line_end": 8.0},
    ]
    episode(
        root / "episodes",
        "ep1",
        np.eye(3),
        spans,
        {
            "subtitles": str(subtitles),
            "subtitle_offset": 0.0,
            "segmentation": "speaker_turns",
            "spoken_language": "ja",
        },
    )
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    first, second, third = state.workspace.clips
    assert (first.start, first.end, first.line) == (2.6, 3.4, (1.0, 4.0))
    assert first.text == "こんにちは"
    assert state.text_of(first, None) == ("こんにちは", None)
    assert not second.overlap and not third.overlap


def test_clips_whose_voices_overlap_are_marked() -> None:
    from avoc.workspace import overlapping

    spans = [(0.0, 2.0), (1.5, 3.0), (3.05, 4.0), (5.0, 6.0), (5.95, 7.0)]
    assert overlapping(spans) == {(0.0, 2.0), (1.5, 3.0)}


def test_a_clip_must_lie_inside_its_line() -> None:
    from avoc.project import segment_rows

    with pytest.raises(ValueError):
        segment_rows("ep1", [{"start": 0.5, "end": 2.5, "line_start": 1.0, "line_end": 2.0}])


def test_an_episode_without_voiceprints_is_skipped_not_fatal(tmp_path: Path) -> None:
    import shutil

    root = _workspace(tmp_path)
    half = episode(root / "episodes", "ep2", np.array([[1.0, 0.0, 0.0]] * 6, dtype=float))
    shutil.rmtree(half / "embeddings")
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    summary = TestClient(create_app(state)).get("/api/state").json()
    assert [e["name"] for e in summary["episodes"]] == ["ep1"]
    assert "avoc add" in summary["skipped"]["ep2"]
    assert {c.episode for c in state.workspace.clips} == {"ep1"}


FINISH_VOICEPRINTS = """
import sys
from pathlib import Path
import numpy as np
from avoc.project import cache_signature, read_json, write_json
args = sys.argv[1:]
folder = Path(args[1]) / "episodes" / args[args.index("--name") + 1]
rows = read_json(folder / "segments.json")
cache = folder / "embeddings/redimnet2-b6"
cache.mkdir(parents=True)
np.save(cache / "vectors.npy", np.tile(np.float32([1, 0, 0]), (len(rows), 1)))
write_json(cache / "metadata.json", rows)
write_json(cache / "cache.json", cache_signature(folder, "redimnet2-b6"))
"""


def test_an_unfinished_episode_can_be_carried_on_from_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page's "carry on" button reruns avoc add with the files the episode recorded, and the
    workspace is reloaded once it is done. A small script stands in for avoc add."""
    import shutil
    import sys

    monkeypatch.setattr("avoc.adding.shutil.which", lambda _: "found")
    root = _workspace(tmp_path)
    half = episode(root / "episodes", "ep2", np.array([[1.0, 0.0, 0.0]] * 6, dtype=float))
    shutil.rmtree(half / "embeddings")
    (tmp_path / "ep2.mkv").write_text("x", encoding="utf-8")
    (tmp_path / "ep2.ass").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    meta = json.loads((half / "episode.json").read_text(encoding="utf-8"))
    meta.update(video=str(tmp_path / "ep2.mkv"), subtitles=str(tmp_path / "ep2.ass"))
    meta["subtitle_offset"] = -0.95
    (half / "episode.json").write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / "finish.py").write_text(FINISH_VOICEPRINTS, encoding="utf-8")

    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    state.adding.program = [sys.executable, str(tmp_path / "finish.py")]
    client = TestClient(create_app(state))
    english = {"X-Language": "en"}
    missing = client.post("/api/add", json={"video": "x.mkv"}, headers=english)
    assert missing.status_code == 400 and "subtitles" in missing.json()["detail"]
    assert client.post("/api/add", json={"resume": "ep2"}).json()["episode"] == "ep2"
    state.adding.ended.wait(timeout=60)
    assert client.get("/api/add").json()["state"] == "done", state.adding.lines
    summary = client.get("/api/state").json()
    assert [e["name"] for e in summary["episodes"]] == ["ep1", "ep2"]
    assert summary["skipped"] == {}


def test_an_episode_never_cut_is_listed_from_the_record_and_can_be_given_up(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    record = {"video": str(tmp_path / "x.mkv"), "subtitles": str(tmp_path / "x.ass")}
    (root / "adding.json").write_text(json.dumps({"ep9": record, "ep1": record}))
    client = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    summary = client.get("/api/state", headers={"X-Language": "en"}).json()
    # ep1 loads in full, so its record is dropped.
    assert summary["not_cut"] == ["ep9"]
    assert "never cut" in summary["skipped"]["ep9"]
    after = client.post("/api/add/forget", json={"episode": "ep9"}).json()
    assert after["not_cut"] == [] and after["skipped"] == {}
    assert not (root / "adding.json").exists()


def test_messages_follow_the_page_language(tmp_path: Path) -> None:
    import shutil

    root = _workspace(tmp_path)
    half = episode(root / "episodes", "ep2", np.array([[1.0, 0.0, 0.0]] * 6, dtype=float))
    shutil.rmtree(half / "embeddings")
    client = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    english = {"X-Language": "en"}
    assert "voiceprints" in client.get("/api/state", headers=english).json()["skipped"]["ep2"]
    assert "声纹" in client.get("/api/state").json()["skipped"]["ep2"]
    wrong = client.post("/api/label", json={"clips": ["nope"], "label": "A"}, headers=english)
    assert wrong.json()["detail"] == "no such clip"
    first = client.get("/api/clips").json()[0]["id"]
    named = client.post("/api/label", json={"clips": [first], "new_role": True}, headers=english)
    assert named.json()["role"] == "Character 1"


def test_an_ignored_line_is_set_aside(tmp_path: Path) -> None:
    from avoc.labels import IGNORED

    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = client.get("/api/clips", params={"episode": "ep1"}).json()
    client.post("/api/label", json={"clips": [clips[0]["id"]], "label": IGNORED})
    seen = client.get("/api/clips", params={"episode": "ep1"}).json()[0]
    assert seen["status"] == "ignored"
    assert state.trained["labels"] == 0
    assert IGNORED not in [r["name"] for r in client.get("/api/state").json()["roles"]]
    client.post("/api/undo")
    assert client.get("/api/clips", params={"episode": "ep1"}).json()[0]["label"] is None


def test_the_history_lists_steps_and_takes_back_chosen_ones(tmp_path: Path) -> None:
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = state.workspace.clips
    client.post("/api/label", json={"clips": [clips[0].id, clips[1].id], "label": "A"})
    client.post("/api/label", json={"clips": [clips[2].id], "label": OTHER})
    history = client.get("/api/history", params={"limit": 1}).json()
    assert history["more"] is True
    (newest,) = history["entries"]
    assert newest["batch"] == 2 and newest["text"] == clips[2].text
    assert newest["to"] == [{"name": OTHER, "count": 1}]
    first = client.get("/api/history", params={"before": 2}).json()["entries"][0]
    assert first["lines"] == 2 and first["created"] == ["A"] and first["why_not"] is None

    taken = client.post("/api/revert", json={"batches": [1]}).json()
    assert taken["undo"] is True and taken["kept"] == 0
    assert state.store.labels == {clips[2].id: OTHER}
    assert client.post("/api/revert", json={"batches": [1]}).status_code == 400
    assert client.post("/api/revert", json={"batches": [99]}).status_code == 400


def test_the_low_quality_hint_shows_and_sets_lines_aside(tmp_path: Path) -> None:
    from avoc.quality import Starter

    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    ws = state.workspace
    ids = [c.id for c in ws.clips if c.row is not None and not c.skipped]
    ws.quality = np.zeros((len(ids), 2), np.float16)
    ws.quality[0, 0], ws.quality[1, 0] = 1.0, 0.6
    ws.quality_rows = {clip_id: k for k, clip_id in enumerate(ids)}
    # Score 10 * first feature - 5: chances 0.99, 0.73, and 0.007 for the rest.
    state._starter = Starter(np.zeros(2), np.ones(2), np.array([10.0, 0.0]), -5.0)
    state.retrain()
    client = TestClient(create_app(state))
    seen = {c["id"]: c for c in client.get("/api/clips", params={"episode": "ep1"}).json()}
    assert seen[ids[0]]["status"] == "likely_low"
    assert seen[ids[1]]["status"] != "likely_low" and seen[ids[1]]["low"] == pytest.approx(0.731)
    assert seen[ids[2]]["low"] is None
    client.post("/api/label", json={"clips": [ids[0]], "label": "A", "unusable": True})
    client.post("/api/label", json={"clips": [ids[2]], "label": OTHER})
    info = client.get("/api/state").json()["quality"]
    assert (info["low"], info["clean"], info["ready"]) == (1, 0, True)
    assert client.get("/api/clips", params={"episode": "ep1"}).json()[0]["status"] == "confirmed"


def test_lines_with_the_low_quality_hint_are_not_counted_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("avoc.service.MIN_GUESS_LABELS", 1)
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = client.get("/api/clips", params={"episode": "ep1"}).json()
    client.post("/api/label", json={"clips": [clips[0]["id"]], "label": "A"})
    client.post("/api/label", json={"clips": [clips[1]["id"]], "label": OTHER})
    guessed = next(
        c
        for c in client.get("/api/clips", params={"episode": "ep1"}).json()
        if c["status"] in ("auto", "review")
    )
    name = guessed["guess"][0]["name"]

    def counts() -> dict[str, int]:
        summary = client.get("/api/state").json()
        return next(
            r for r in [*summary["roles"], summary["other"] | {"name": OTHER}] if r["name"] == name
        )

    before = counts()
    assert before["to_check"] == before["predicted"]
    state.low[guessed["id"]] = 0.6
    after = counts()
    assert after["predicted"] == before["predicted"]
    assert after["to_check"] == before["to_check"] - 1


def test_lines_with_the_low_quality_hint_are_not_work_to_do(tmp_path: Path) -> None:
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = client.get("/api/clips", params={"episode": "ep1"}).json()
    todo = [c for c in clips if c["status"] in ("review", "unlabeled")]

    def work() -> int:
        return next(e for e in client.get("/api/state").json()["episodes"] if e["name"] == "ep1")[
            "work"
        ]

    assert work() == len(todo)
    state.low[todo[0]["id"]] = 0.6
    assert work() == len(todo) - 1


def test_api_says_which_targets_wait_for_more_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("avoc.service.MIN_GUESS_LABELS", 2)
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = client.get("/api/clips", params={"episode": "ep1"}).json()
    client.post("/api/label", json={"clips": [clips[0]["id"]], "label": "A"})
    client.post("/api/label", json={"clips": [clips[3]["id"]], "label": OTHER})
    model = client.get("/api/state").json()["model"]
    assert model["min_labels"] == 2
    assert model["waiting"] == {"A": {"lines": 1, "others": 1}}
    assert all(not c["guess"] for c in client.get("/api/clips", params={"episode": "ep1"}).json())

    client.post("/api/label", json={"clips": [clips[1]["id"]], "label": "A"})
    assert client.get("/api/state").json()["model"]["waiting"] == {}
    after = client.get("/api/clips", params={"episode": "ep1"}).json()
    assert after[2]["guess"][0]["name"] == "A"


def test_what_the_voices_are_for_is_chosen_once(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    client = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    assert client.get("/api/state").json()["purpose"] is None
    assert client.post("/api/purpose", json={"purpose": "tts"}).json()["purpose"] == "tts"
    assert client.post("/api/purpose", json={"purpose": "tts"}).status_code == 200
    switched = client.post("/api/purpose", json={"purpose": "audio"})
    assert switched.status_code == 400 and "中途" in switched.json()["detail"]
    assert client.post("/api/purpose", json={"purpose": "rvc"}).status_code == 400
    # Kept in the workspace, so another browser or a restart sees the same choice.
    reopened = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    assert reopened.get("/api/state").json()["purpose"] == "tts"


def test_api_labels_retrains_and_undoes(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = client.get("/api/clips", params={"episode": "ep1"}).json()
    assert len(clips) == 6
    assert all(c["status"] == "unlabeled" for c in clips)

    groups = client.get("/api/groups", params={"episode": "ep1"}).json()
    assert sorted(g["size"] for g in groups) == [3, 3]

    result = client.post("/api/label", json={"clips": [clips[0]["id"]], "label": "A"}).json()
    result = client.post("/api/label", json={"clips": [clips[3]["id"]], "label": "B"}).json()
    assert result["ripple"] > 0
    after = {c["id"]: c for c in client.get("/api/clips", params={"episode": "ep1"}).json()}
    assert after[clips[1]["id"]]["guess"][0]["name"] == "A"
    assert after[clips[4]["id"]]["guess"][0]["name"] == "B"
    assert after[clips[0]["id"]]["status"] == "confirmed"

    rejected = client.post(
        "/api/changes", json={"changes": [{"clip": clips[1]["id"], "reject": "A", "on": True}]}
    ).json()
    moved = {c["id"]: c for c in rejected["updated"]}
    assert moved[clips[1]["id"]]["guess"][0]["name"] != "A"

    undone = client.post("/api/undo").json()
    assert undone["undo"] is True
    state_now = client.get("/api/state").json()
    assert {r["name"] for r in state_now["roles"]} == {"A", "B"}
    assert client.post("/api/label", json={"clips": ["nope"], "label": "A"}).status_code == 400

    fresh = client.post("/api/label", json={"clips": [clips[2]["id"]], "new_role": True}).json()
    assert fresh["role"] == "角色 1"
    listed = {r["name"]: r for r in fresh["state"]["roles"]}
    assert listed["角色 1"]["named"] is False and listed["A"]["named"] is True

    png = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
        "hQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    saved = client.post("/api/roles/avatar", json={"name": "角色 1", "image": png}).json()
    avatar = next(r["avatar"] for r in saved["roles"] if r["name"] == "角色 1")
    assert client.get(f"/media/avatar/{avatar}").status_code == 200


def test_groups_hold_only_lines_still_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = [c["id"] for c in client.get("/api/clips", params={"episode": "ep1"}).json()]
    client.post("/api/label", json={"clips": [clips[0]], "label": "A"})

    def grouped() -> set[str]:
        return {c["id"] for g in client.get("/api/groups").json() for c in g["clips"]}

    assert grouped() == set(clips[1:])
    # The test set is too small for the machine to be confident, so make one guess confident. Its
    # partner is then alone, and a group of one is not shown.
    status = state.status
    monkeypatch.setattr(state, "status", lambda c: "auto" if c.id == clips[1] else status(c))
    assert grouped() == set(clips[3:])


def test_skipped_clips_stay_out_of_the_work_lists_until_someone_labels_them(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    import soundfile as sf

    root = _workspace(tmp_path)
    # Export cuts from the vocals at their own rate; the test set's file is 16 kHz and too short.
    sf.write(root / "episodes/ep1/ep1.wav", np.zeros(44100 * 60), 44100)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    # The test set's clips are 1 second long, so all need a person to label them. Make the last
    # one too short.
    assert not any(c.skipped for c in state.workspace.clips)
    lonely = replace(state.workspace.clips[-1], end=state.workspace.clips[-1].start + 0.8)
    state.workspace.clips[-1] = lonely
    state.workspace.by_id[lonely.id] = lonely
    client = TestClient(create_app(state))

    client.post("/api/label", json={"clips": [state.workspace.clips[0].id], "label": "A"})
    client.post("/api/label", json={"clips": [state.workspace.clips[3].id], "label": "B"})
    clips = {c["id"]: c for c in client.get("/api/clips", params={"episode": "ep1"}).json()}
    assert clips[lonely.id]["status"] == "skipped"
    # In Characters it is listed under Skipped (marked short), not counted as to check.
    b = {c["id"]: c for c in client.get("/api/clips", params={"role": "B"}).json()}
    assert b[lonely.id]["short"] and not b[lonely.id].get("maybe")
    roles = client.get("/api/state").json()["roles"]
    work = [c for c in b.values() if not (c["label"] or c["short"] or c.get("maybe"))]
    assert next(r for r in roles if r["name"] == "B")["to_check"] == len(work)
    grouped = {c["id"] for g in client.get("/api/groups").json() for c in g["clips"]}
    assert lonely.id not in grouped
    assert client.get("/api/state").json()["episodes"][0]["counts"]["skipped"] == 1

    trained = state.trained["labels"]
    client.post("/api/label", json={"clips": [lonely.id], "label": "B"})
    clips = {c["id"]: c for c in client.get("/api/clips", params={"episode": "ep1"}).json()}
    assert clips[lonely.id]["status"] == "confirmed"
    # Still short, so the page keeps it under "short lines"; but labeled, it is used like any
    # other line: for training and on export.
    assert clips[lonely.id]["short"] and not clips[state.workspace.clips[0].id]["short"]
    assert state.trained["labels"] == trained + 1
    body = {"roles": ["B"], "form": "folder"}
    assert (
        client.post("/api/export", json={**body, "out": str(tmp_path / "a")}).json()["files"] == 2
    )
    # Low quality is still left out, as for any line.
    client.post("/api/changes", json={"changes": [{"clip": lonely.id, "unusable": True}]})
    result = client.post("/api/export", json={**body, "out": str(tmp_path / "b")}).json()
    assert result["files"] == 1 and sum(result["rejected"].values()) == 1


def test_an_added_target_lists_old_others_that_may_be_it(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    ids = [c.id for c in state.workspace.clips]
    client.post("/api/label", json={"clips": [ids[0]], "label": "A"})
    client.post("/api/label", json={"clips": [ids[3]], "label": OTHER})
    summary = client.get("/api/state").json()
    assert summary["other"]["confirmed"] == 1
    listed = {c["id"]: c for c in client.get("/api/clips", params={"episode": "ep1"}).json()}
    assert {listed[i]["guess"][0]["name"] for i in (ids[4], ids[5])} == {OTHER}

    # Later B was made a target too. When ids[3] was labeled "other", B was not yet a target, so
    # ids[3] should appear in the "possibly missed" list.
    client.post("/api/label", json={"clips": [ids[4]], "label": "B"})
    listed = {c["id"]: c for c in client.get("/api/clips", params={"role": "B"}).json()}
    assert listed[ids[3]].get("maybe") is True
    assert ids[5] in listed and not listed[ids[5]].get("maybe")
    # Only the possibly missed clips, as the web app fetches them after each change.
    missed = client.get("/api/clips", params={"role": "B", "maybe": True}).json()
    assert [c["id"] for c in missed] == [c["id"] for c in listed.values() if c.get("maybe")]
    # Labeled "other" again: now judged against B too, so it is no longer possibly missed.
    client.post("/api/label", json={"clips": [ids[3]], "label": OTHER})
    missed = client.get("/api/clips", params={"role": "B", "maybe": True}).json()
    assert ids[3] not in {c["id"] for c in missed}

    # Remove A as a target: A's labels stay, but the machine no longer guesses A.
    client.post("/api/roles", json={"name": "A", "target": False})
    guesses = {
        c["id"]: c["guess"] for c in client.get("/api/clips", params={"episode": "ep1"}).json()
    }
    assert all(g["name"] != "A" for g in guesses[ids[1]])
    assert state.store.labels[ids[0]] == "A"


def test_roles_report_total_length_and_other_can_be_listed(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = state.workspace.clips
    client.post("/api/label", json={"clips": [clips[0].id], "label": "A", "unusable": True})
    client.post("/api/label", json={"clips": [clips[1].id], "label": "A"})
    client.post("/api/label", json={"clips": [clips[2].id, clips[3].id], "label": OTHER})
    summary = client.get("/api/state").json()
    a = next(r for r in summary["roles"] if r["name"] == "A")
    assert a["seconds"] == round(clips[0].duration + clips[1].duration, 1)
    assert a["low_seconds"] == round(clips[0].duration, 1)
    assert summary["other"]["seconds"] == round(clips[2].duration + clips[3].duration, 1)

    # "Other" can also be opened. Confirmed clips are sorted from the ones closest to a target
    # character, and there is no "possibly missed" list.
    listed = client.get("/api/clips", params={"role": OTHER}).json()
    assert not any(c.get("maybe") for c in listed)
    mine = [c for c in listed if c["label"] == OTHER]
    assert {c["id"] for c in mine} == {clips[2].id, clips[3].id}
    best = [max(g["p"] for g in c["guess"] if g["name"] != OTHER) for c in mine]
    assert best == sorted(best, reverse=True)


def test_an_ignored_line_is_listed_under_the_character_the_machine_gives_it(
    tmp_path: Path,
) -> None:
    from avoc.labels import IGNORED

    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clips = state.workspace.clips
    client.post("/api/label", json={"clips": [clips[0].id, clips[1].id], "label": "A"})
    client.post("/api/label", json={"clips": [clips[2].id, clips[3].id], "label": OTHER})
    line = next(c for c in clips[4:] if c.row is not None and not c.skipped)
    client.post("/api/label", json={"clips": [line.id], "label": IGNORED})
    top = state.guesses[line.row].names[0]
    listed = client.get("/api/clips", params={"role": top}).json()
    assert [c["label"] for c in listed if c["id"] == line.id] == [IGNORED]


def test_unusable_keeps_the_name_but_stays_out_of_training_and_export(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels")
    store.apply([{"clip": "a", "unusable": True}])
    assert store.unusable == {"a"}
    assert store.apply([{"clip": "a", "unusable": True}]) is None
    store.undo()
    assert store.unusable == set()
    store.apply([{"clip": "a", "unusable": True}])
    assert LabelStore(tmp_path / "labels").unusable == {"a"}

    import soundfile as sf

    root = _workspace(tmp_path)
    # Export must cut from the vocals track at its original sample rate. The test set's own file is
    # 16 kHz and 1 second long, so use a longer one.
    sf.write(root / "episodes/ep1/ep1.wav", np.zeros(44100 * 10), 44100)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    first, second = (c.id for c in state.workspace.clips[:2])
    client.post("/api/label", json={"clips": [first, second], "label": "A"})
    assert state.trained["labels"] == 2
    marked = client.post("/api/changes", json={"changes": [{"clip": first, "unusable": True}]})
    view = marked.json()["updated"][0]
    assert view["unusable"] is True and view["label"] == "A"
    assert state.trained["labels"] == 1

    body = {"roles": ["A"], "form": "folder"}
    part = client.post("/api/export", json={**body, "out": str(tmp_path / "part")}).json()
    assert part["files"] == 1 and part["rejected"] == {"人标了质量低": 1}
    assert "人标了质量低" in (tmp_path / "part" / "rejected.tsv").read_text("utf-8")

    client.post("/api/changes", json={"changes": [{"clip": second, "unusable": True}]})
    none = client.post("/api/export", json={**body, "out": str(tmp_path / "none")})
    assert none.status_code == 400 and "2 条都标了质量低" in none.json()["detail"]


def test_default_export_folder_moves_on_once_used(tmp_path: Path) -> None:
    from avoc.app.server import free_export_folder

    first = free_export_folder(tmp_path)
    assert first.parent == tmp_path.resolve() / "exports"
    first.mkdir(parents=True)
    assert free_export_folder(tmp_path) == first, "an empty folder can still take an export"
    (first / "train.list").write_text("", encoding="utf-8")
    assert free_export_folder(tmp_path).name == f"{first.name}-2"


def test_one_choice_sets_who_and_quality_together(tmp_path: Path) -> None:
    """One choice: labeling "target, low quality" sets both at once. Changing it to clean target,
    to "other", or clearing it also turns "low quality" off."""
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clip = state.workspace.clips[0].id

    def label(name: str | None, unusable: bool = False) -> dict:
        body = {"clips": [clip], "label": name, "unusable": unusable}
        return client.post("/api/label", json=body).json()["updated"][0]

    view = label("A", unusable=True)
    assert view["label"] == "A" and view["unusable"] is True
    assert label("A")["unusable"] is False
    label("A", unusable=True)
    assert label(OTHER, unusable=True)["unusable"] is False
    label("A", unusable=True)
    assert label(None)["unusable"] is False
    client.post("/api/undo")
    assert state.store.labels[clip] == "A" and state.store.unusable == {clip}

    # A name of only spaces counts as clearing the label, and it must not leave
    # "low quality" behind.
    assert label("  ", unusable=True)["unusable"] is False
    assert clip not in state.store.labels


def test_changes_api_rejects_unknown_entries_and_reads_old_flag_names(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clip = state.workspace.clips[0].id
    client.post("/api/label", json={"clips": [clip], "label": "A"})
    # The old "multiple people" switch name is still recognized as "low quality", and is not taken
    # as clearing the label.
    client.post("/api/changes", json={"changes": [{"clip": clip, "overlap": True}]})
    assert state.store.labels[clip] == "A" and state.store.unusable == {clip}
    bad = client.post("/api/changes", json={"changes": [{"clip": clip}]})
    assert bad.status_code == 422
    assert state.store.labels[clip] == "A"


def test_page_files_are_checked_on_every_load(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    client = TestClient(create_app(AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")))
    for path in ("/", "/static/assets/index.js", "/static/assets/index.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"


def test_prefetch_cuts_nearby_and_later_clips_in_the_background(tmp_path: Path) -> None:
    import time

    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    first = state.workspace.clips[0]
    near = [
        c for c in state.workspace.clips
        if c.episode == first.episode and (c.start >= first.start or c.end >= first.start - 60)
    ]  # fmt: skip
    episode = state.workspace.episodes[first.episode]
    assert not episode.get("video")
    queued = client.post("/api/prefetch", json={"clip": first.id}).json()["queued"]
    assert queued == len(near)
    folder = Path(episode["directory"]) / "app_media" / "audio"
    deadline = time.time() + 30
    while time.time() < deadline and not all((folder / f"{c.id}.wav").exists() for c in near):
        time.sleep(0.1)
    assert state.prefetch(first.id) == 0
    assert client.post("/api/prefetch", json={"clip": "nope"}).status_code == 404


def test_longer_context_is_cut_separately_on_request(tmp_path: Path) -> None:
    import soundfile as sf

    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clip = state.workspace.clips[0]
    plain = client.get(f"/media/audio/{clip.id}.wav")
    wide = client.get(f"/media/audio/{clip.id}.wav?context=5")
    assert plain.status_code == wide.status_code == 200
    plain_path, wide_path = state.media("audio", clip.id), state.media("audio", clip.id, 5)
    assert plain_path != wide_path
    total = sf.info(str(state.workspace.episodes[clip.episode]["vocals"])).duration
    expected = min(clip.end + 5, total) - max(0, clip.start - 5)
    assert sf.info(str(wide_path)).duration == pytest.approx(expected, abs=0.01)
    assert client.get(f"/media/audio/{clip.id}.wav?context=7").status_code == 404


def test_old_overlap_records_count_as_unusable(tmp_path: Path) -> None:
    """The old separate "multiple people" switch was merged into "low quality". Old records, when
    replayed or undone, count as "low quality"."""
    folder = tmp_path / "labels"
    folder.mkdir()
    old = {
        "batch": 1, "time": "2026-01-01T00:00:00+00:00", "source": "human", "undo_of": None,
        "changes": [{"clip": "a", "overlap": True, "before": False, "after": True}],
    }  # fmt: skip
    (folder / "events.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
    store = LabelStore(folder)
    assert store.unusable == {"a"}
    assert store.apply([{"clip": "a", "unusable": True}]) is None
    store.undo()
    assert store.unusable == set()
    assert LabelStore(folder).unusable == set()


def test_audio_cut_does_not_share_its_unfinished_file_with_another_app(tmp_path: Path) -> None:
    import soundfile as sf

    from avoc.app.server import _cut_audio

    vocals = tmp_path / "vocals.wav"
    sf.write(str(vocals), np.zeros(16000, dtype=np.float32), 16000)
    target = tmp_path / "cut.wav"
    # An unfinished file left by another app open on the same project.
    other = target.with_suffix(".1.part.wav")
    other.write_bytes(b"half")
    _cut_audio(vocals, 0.25, 0.75, target)
    assert sf.info(str(target)).frames == 8000
    assert other.read_bytes() == b"half"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cut.1.part.wav", "cut.wav", "vocals.wav"]


def test_a_broken_cut_is_cut_again_on_request(tmp_path: Path) -> None:
    import soundfile as sf

    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clip = state.workspace.clips[0]
    path = state.media("audio", clip.id)
    path.write_bytes(b"broken")
    assert client.get(f"/media/audio/{clip.id}.wav").content == b"broken"
    assert client.get(f"/media/audio/{clip.id}.wav?fresh=1").status_code == 200
    assert sf.info(str(path)).duration == pytest.approx(clip.end - clip.start, abs=0.01)


def test_no_folder_is_made_for_an_episode_moved_away(tmp_path: Path) -> None:
    """A server still running on a workspace that was renamed must not leave a stray episode
    folder behind, which would take the name of the next episode added."""
    root = _workspace(tmp_path)
    state = AppState(root, ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    clip = state.workspace.clips[0]
    directory = Path(state.workspace.episodes[clip.episode]["directory"])
    directory.rename(tmp_path / "moved")
    answer = client.get(f"/media/audio/{clip.id}.wav", headers={"X-Language": "en"})
    assert answer.status_code == 404
    assert "is gone" in answer.json()["detail"]
    assert not directory.exists()


def test_the_add_form_can_name_the_episode(tmp_path: Path) -> None:
    """A name such as usagi-s1-ep01 keeps several anime apart in one workspace. A name already
    used, or one the folder rules do not allow, is refused before anything starts."""
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    video, subtitles = tmp_path / "a.mkv", tmp_path / "a.srt"
    video.write_bytes(b"video")
    subtitles.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    body = {"video": str(video), "subtitles": str(subtitles), "offset": 0}
    english = {"X-Language": "en"}
    taken = state.workspace.clips[0].episode
    used = client.post("/api/add", json={**body, "name": taken}, headers=english)
    assert used.status_code == 400 and "already an episode named" in used.json()["detail"]
    bad = client.post("/api/add", json={**body, "name": "usagi s1"}, headers=english)
    assert bad.status_code == 400 and "may only contain" in bad.json()["detail"]


def test_the_add_form_can_queue_several_episodes(tmp_path: Path) -> None:
    """Folders are paired by episode number, and a queue with a name already used is refused
    before anything starts."""
    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    folder = tmp_path / "show"
    folder.mkdir()
    for n in (1, 2):
        (folder / f"Show S01E0{n}.mkv").write_bytes(b"video")
        (folder / f"[G] Show - 0{n}.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
    english = {"X-Language": "en"}
    pairs = client.post("/api/add/pairs", json={"videos": str(folder), "subtitles": str(folder)})
    found = pairs.json()["episodes"]
    assert [(e["number"], len(e["videos"]), len(e["subtitles"])) for e in found] == [
        (1, 1, 1),
        (2, 1, 1),
    ]
    taken = state.workspace.clips[0].episode
    episodes = [
        {"name": name, "video": e["videos"][0], "subtitles": e["subtitles"][0]}
        for name, e in zip([taken, "show-ep02"], found, strict=True)
    ]
    used = client.post("/api/add/queue", json={"episodes": episodes, "offset": 0}, headers=english)
    assert used.status_code == 400 and f"taken already: {taken}" in used.json()["detail"]
    assert state.adding.status()["state"] == "idle"


def test_the_episode_copy_is_used_only_while_its_sources_are_unchanged(tmp_path: Path) -> None:
    """The page plays an episode from its whole copy only when the copy was made from the files as
    they are now; until then each line plays its own cut. Tests make no copies themselves."""
    from avoc.video import COPY_FOLDER, copy_signature

    state = AppState(_workspace(tmp_path), ("redimnet2-b6",), grouping="redimnet2-b6")
    client = TestClient(create_app(state))
    meta = state.workspace.episodes["ep1"]
    assert not client.get("/api/state").json()["episodes"][0]["player"]
    assert client.get("/episode-media/ep1/vocals").status_code == 404
    state.want_copy("ep1")
    assert state.playback._copy_wanted == []

    folder = Path(meta["directory"]) / "app_media" / COPY_FOLDER
    folder.mkdir(parents=True)
    (folder / "vocals.m4a").write_bytes(b"sound")
    (folder / "copy.json").write_text(json.dumps(copy_signature(meta)), encoding="utf-8")
    assert client.get("/api/state").json()["episodes"][0]["player"]
    assert client.get("/episode-media/ep1/vocals").content == b"sound"
    assert client.get("/episode-media/ep1/other").status_code == 404
    assert client.post("/api/prefetch", json={"clip": state.workspace.clips[0].id}).json()[
        "player"
    ] == {"ready": True, "making": False, "failed": None}

    vocals = Path(meta["vocals"])
    vocals.write_bytes(vocals.read_bytes() + b"\0")
    assert not state.player("ep1")["ready"]


def test_each_picture_pad_keeps_its_own_cuts() -> None:
    from avoc.video import media_name

    assert media_name("video", "a") == "video/a.line.mp4"
    assert media_name("video", "a", 5, 0.5) == "video/a.ctx5.pad500.mp4"
    assert media_name("audio", "a", 5, 0.5) == "audio/a.ctx5.wav"


def test_a_connection_the_browser_closed_is_not_printed() -> None:
    import asyncio

    from avoc.app.server import _ignore_closed_connection

    shown: list[dict] = []
    loop = asyncio.new_event_loop()
    loop.default_exception_handler = shown.append  # type: ignore[method-assign]
    try:
        _ignore_closed_connection(loop, {"message": "reset", "exception": ConnectionResetError()})
        assert shown == []
        _ignore_closed_connection(loop, {"message": "other", "exception": ValueError()})
        assert [c["message"] for c in shown] == ["other"]
    finally:
        loop.close()
