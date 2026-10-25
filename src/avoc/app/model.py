"""Train one small classifier on the human labels that picks among the target characters and
"other". Then rank every clip that has a voiceprint.

Users only name the target characters. Everyone else is labeled "other" (see labels.py). The
classifier is a softmax regression (multinomial logistic regression: one score per choice, turned
into chances that add up to 1), so the chances shown for a clip add up to 100%.

**Labels that leave more than one choice.** "Other" means "none of the targets at the time". When a
target is added later, an old "other" label means "this new target, or other": it leaves two
choices. A clip the person said is "not A", and left unlabeled, leaves every choice but A. So each
labeled clip comes with the set of choices it may be (`answers`), and training raises the summed
chance of that set (partial-label likelihood). A set of one choice is an ordinary label. A target
character set up before the first "other" label makes every "other" label a set of one, which tells
the machine the most.

With only one target, this is the same model as the earlier logistic regression for that target
(see `STRENGTH`). The training set is only a few hundred to a few thousand clips, and one training
run takes well under a second. So every label change retrains everything; the last answer is only
used as the starting point.

**The classifier only picks among the characters it knows.** A voice that was never labeled may
still be guessed as some target character, and the confidence can still be fairly high. So there is
an extra similarity check: among the confirmed clips of the character the clip was assigned to,
the most similar one must be similar enough. The bar is not fixed. It is measured
from the current human labels: for each confirmed clip, take its highest similarity to the other
confirmed clips of the same character, and use a low-end value of those (the `FAMILIAR_QUANTILE`
percentile). Clips assigned to "other" skip this check, because a voice never seen is "other"
anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from avoc.app.labels import OTHER

STRENGTH = 100.0
"""Regularization strength, as scikit-learn's `C` of a two-choice logistic regression. The value
picked when episodes 1 and 2 were held out in turn was between 30 and 1000. The middle value was
used. The softmax weights are held back by `sum(W**2) / STRENGTH`: with one target and "other",
that gives exactly the earlier logistic regression with `C=STRENGTH`."""

AUTO_CONFIDENCE = 0.6
"""A confidence at or above this number counts as "confident". The interface then stops asking the
person to confirm each clip one by one.

Measured on episode 3, back when the model chose among all characters: clips with confidence of at
least 0.6 made up 80% of clips, and 97% of those were right. Below 0.6, only a little over 30% were
right. After switching to a separate judgment for each target character, only teo was measured.
Across episodes 1 to 3, each held out in turn, at 0.6 the model missed 13 of 230 teo clips, and no
other character was wrongly accepted as teo.
"""

FAMILIAR_QUANTILE = 0.05
"""The percentile of each character's nearest-clip similarity used as the "similar enough" bar.
95% of confirmed clips pass this bar."""

MIN_GUESS_LABELS = 10
"""The machine starts guessing a target character only once a person has confirmed this many of
their lines (and labeled at least one other line as not them). Replaying the Teio labels of episodes
1 and 2 and scoring on episode 3: with 10 of her lines the guesses were 94% right and found three
quarters of her lines; with fewer they were barely better than calling everyone "Other". See
docs/HOW_IT_WORKS.md#how-many-labels-before-the-guesses-are-good."""

MIN_FAMILIAR_LABELS = 20
"""If there are fewer confirmed clips than this, no reliable bar can be measured. In that case the
machine never counts as confident."""


@dataclass(frozen=True)
class Guess:
    names: tuple[str, ...]
    """All target characters plus "other", sorted from most similar to least similar."""
    probabilities: tuple[float, ...]
    """The chance of each name. They add up to 1; a target the machine does not guess yet gets 0."""
    similarity: float
    """Cosine similarity (a score for how alike two voiceprints are) to the most similar confirmed
    clip of the most similar target character."""
    familiar: bool | None
    """When the top-ranked name is a target character: whether the similarity passed the bar. If it
    did not, this may be a person not seen before. When the top-ranked name is "other", this check
    is skipped and counted as passed. It is None when there are too few labels to measure a bar."""

    @property
    def confidence(self) -> float:
        return self.probabilities[0]

    def p(self, name: str) -> float:
        return self.probabilities[self.names.index(name)] if name in self.names else 0.0


@dataclass(frozen=True)
class Weights:
    """A trained softmax regression: the names of its choices, then the weights and offsets."""

    names: tuple[str, ...]
    weights: Any
    offsets: Any


@dataclass(frozen=True)
class Trained:
    guesses: dict[int, Guess]
    threshold: float | None
    weights: Weights | None = None


def familiar_threshold(features: Any, rows: list[int], names: list[str]) -> float | None:
    """For each confirmed clip, its highest similarity to the other confirmed clips of the same
    character. Then take a low-end percentile of those values."""
    import numpy as np

    if len(rows) < MIN_FAMILIAR_LABELS:
        return None
    labeled = features[rows]
    similarity = labeled @ labeled.T
    np.fill_diagonal(similarity, -np.inf)
    roles = np.array(names)
    best = []
    for i, name in enumerate(names):
        same = roles == name
        same[i] = False
        if same.any():
            best.append(float(similarity[i, same].max()))
    if len(best) < MIN_FAMILIAR_LABELS:
        return None
    return float(np.quantile(best, FAMILIAR_QUANTILE))


def guessed_targets(
    targets: list[str], answers: dict[int, frozenset[str]], min_labels: int = MIN_GUESS_LABELS
) -> list[str]:
    """The targets the machine guesses: at least `min_labels` clips are surely them, and at least
    one labeled clip is surely not them. With fewer of their lines the guesses are barely better
    than calling everyone "other"; with no one known not to be them, every line would come out as
    theirs."""
    return [
        t
        for t in targets
        if sum(s == {t} for s in answers.values()) >= min_labels
        and any(t not in s for s in answers.values())
    ]


def fit(
    features: Any,
    choices: Any,
    device: str = "cpu",
    start: tuple[Any, Any] | None = None,
) -> tuple[Any, Any]:
    """Fit a softmax regression with partial labels. `choices[i, c]` is True when row i may be
    choice c. Training lowers `-log(sum of the chances of the row's choices)`, summed over rows,
    plus `sum(W**2) / STRENGTH`. Computed with L-BFGS in 64-bit floats, on `device` ("cpu" or
    "cuda"). Returns the weights and the offsets as NumPy arrays."""
    import torch

    x = torch.as_tensor(features, dtype=torch.float64, device=device)
    allowed = torch.as_tensor(choices, dtype=torch.bool, device=device)
    width, count = x.shape[1], allowed.shape[1]
    if start is None:
        w = torch.zeros(width, count, dtype=torch.float64, device=device)
        b = torch.zeros(count, dtype=torch.float64, device=device)
    else:
        w, b = (torch.as_tensor(a, dtype=torch.float64, device=device) for a in start)
    w.requires_grad_(True)
    b.requires_grad_(True)
    solver = torch.optim.LBFGS(
        [w, b],
        max_iter=2000,
        tolerance_grad=1e-9,
        tolerance_change=1e-12,
        history_size=20,
        line_search_fn="strong_wolfe",
    )

    def loss() -> Any:
        solver.zero_grad()
        scores = x @ w + b
        kept = torch.logsumexp(scores.masked_fill(~allowed, -torch.inf), dim=1)
        total = (torch.logsumexp(scores, dim=1) - kept).sum() + (w * w).sum() / STRENGTH
        total.backward()
        return total

    solver.step(loss)
    return w.detach().cpu().numpy(), b.detach().cpu().numpy()


def train_and_predict(
    features: Any,
    targets: list[str],
    answers: dict[int, frozenset[str]],
    rejects: dict[int, set[str]],
    min_labels: int = MIN_GUESS_LABELS,
    device: str = "cpu",
    start: Weights | None = None,
) -> Trained:
    """Give a prediction for each row of the voiceprint table.

    `answers` maps each labeled row to the names it may be: target characters and `OTHER`. One
    name is an ordinary label; more than one is what an old "other" label or a "not this
    character" leaves open. `rejects` lists the rows and characters where the person said "not
    this character". On those rows, that character's chance is 0 and the rest are scaled back up
    to 1. Only the targets of `guessed_targets` are choices; a clip that may be a target not
    guessed yet may be "other" in their place. `start` is the last training's answer; it is used
    as the starting point when the choices are the same.
    """
    import numpy as np

    if not targets or len(features) == 0:
        return Trained({}, None)
    positives = {t: [r for r, s in answers.items() if s == {t}] for t in targets}
    threshold = familiar_threshold(
        features,
        [r for t in targets for r in positives[t]],
        [t for t in targets for _ in positives[t]],
    )
    guessed = guessed_targets(targets, answers, min_labels)
    if not guessed:
        return Trained({}, threshold)

    names = (*guessed, OTHER)
    rows, choices = [], []
    for row, may in answers.items():
        allowed = [name in may for name in guessed]
        allowed.append(OTHER in may or any(n not in guessed for n in may))
        if not all(allowed):
            rows.append(row)
            choices.append(allowed)
    begin = (start.weights, start.offsets) if start and start.names == names else None
    w, b = fit(features[rows], np.array(choices), device, begin)
    scores = features @ w + b
    scores -= scores.max(axis=1, keepdims=True)
    chances = np.exp(scores)
    chances /= chances.sum(axis=1, keepdims=True)

    # Similarity of each row to the most similar confirmed clip of each guessed target. A confirmed
    # clip is not compared with itself.
    nearest = np.full((len(features), len(guessed)), -1.0)
    for k, target in enumerate(guessed):
        similarity = features @ features[positives[target]].T
        similarity[positives[target], np.arange(len(positives[target]))] = -np.inf
        nearest[:, k] = np.maximum(similarity.max(axis=1), -1.0)

    guesses = {}
    for row in range(len(features)):
        own = chances[row].copy()
        for name in rejects.get(row, ()):
            if name in guessed:
                own[guessed.index(name)] = 0.0
        own /= own.sum() or 1.0
        best = int(np.argmax(own[:-1]))
        scored = [(name, float(p)) for name, p in zip(names, own, strict=True)]
        scored += [(t, 0.0) for t in targets if t not in guessed]
        scored.sort(key=lambda pair: -pair[1])
        close = float(nearest[row, best])
        familiar = None if threshold is None else (scored[0][0] == OTHER or close >= threshold)
        guesses[row] = Guess(
            names=tuple(name for name, _ in scored),
            probabilities=tuple(round(p, 4) for _, p in scored),
            similarity=round(close, 4),
            familiar=familiar,
        )
    return Trained(guesses, threshold, Weights(names, w, b))
