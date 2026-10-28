import { expect, test } from "vitest";
import type { Clip } from "./api";
import {
  bestTarget,
  IGNORED,
  maybeListOf,
  missedChanges,
  OTHER,
  otherName,
  partOf,
  pendingOf,
  rolePartOf,
  skippedOf,
  skipReason,
  whoOf,
  withMissed,
} from "./clips";

const clip = (id: string, extra: Partial<Clip> = {}): Clip => ({
  id,
  episode: "ep1",
  start: 0,
  end: 1,
  duration: 1,
  short: false,
  overlap: false,
  text: "",
  scene: 0,
  voiced: true,
  label: null,
  rejects: [],
  unusable: false,
  low: null,
  guess: [],
  familiar: null,
  status: "review",
  spoken: "",
  spoken_problem: null,
  role: null,
  ...extra,
});

test("whoOf takes the person's label before the machine's guess", () => {
  const guess = [{ name: "A", p: 0.9 }];
  expect(whoOf(clip("1", { guess }))).toEqual({ name: "A", human: false, p: 0.9 });
  expect(whoOf(clip("1", { guess, label: "B" }))).toEqual({ name: "B", human: true });
  expect(whoOf(clip("1"))).toBeNull();
});

test("bestTarget skips other", () => {
  const guess = [
    { name: OTHER, p: 0.7 },
    { name: "A", p: 0.2 },
  ];
  expect(bestTarget(clip("1", { guess }))?.name).toBe("A");
});

test("pendingOf lists unconfirmed lines, least sure first, and leaves out maybe missed", () => {
  const sure = clip("sure", { guess: [{ name: "A", p: 0.9 }] });
  const unsure = clip("unsure", { guess: [{ name: "A", p: 0.4 }] });
  const done = clip("done", { label: "A" });
  const maybe = clip("maybe", { maybe: true });
  const list = [sure, unsure, done, maybe];
  expect(pendingOf(list).map((c) => c.id)).toEqual(["unsure", "sure"]);
  expect(maybeListOf(list).map((c) => c.id)).toEqual(["maybe"]);
});

test("the newest maybe missed list replaces the old one, in its own order", () => {
  const todo = clip("todo");
  const kept = clip("kept", { maybe: true });
  const gone = clip("gone", { maybe: true, label: "B" });
  const fresh = [clip("new", { maybe: true }), clip("kept", { maybe: true, text: "newer" })];
  const list = [todo, kept, gone];
  expect(missedChanges(list, fresh)).toEqual(["gone", "new"]);
  const merged = withMissed(list, fresh);
  expect(merged.map((c) => [c.id, !!c.maybe])).toEqual([
    ["todo", false],
    ["gone", false],
    ["new", true],
    ["kept", true],
  ]);
  expect(merged.find((c) => c.id === "kept")?.text).toBe("newer");
});

test("other typed as a name in either language means the other label", () => {
  expect(otherName(" Other ")).toBe(true);
  expect(otherName("其他")).toBe(true);
  expect(otherName("Not a target")).toBe(true);
  expect(otherName("不是目标")).toBe(true);
  expect(otherName("Others")).toBe(false);
});

test("every line is in one part of Scenes", () => {
  expect(partOf(clip("1", { status: "review" }))).toBe("review");
  expect(partOf(clip("1", { status: "unlabeled" }))).toBe("unlabeled");
  expect(partOf(clip("1", { status: "auto" }))).toBe("auto");
  expect(partOf(clip("1", { status: "confirmed", label: "A" }))).toBe("clean");
  expect(partOf(clip("1", { status: "confirmed", label: "A", unusable: true }))).toBe("low");
  expect(partOf(clip("1", { status: "confirmed", label: OTHER }))).toBe("clean");
  expect(partOf(clip("1", { short: true, status: "skipped" }))).toBe("rule");
  /* A labeled short line stays with the short lines, so labeling it does not move it away. */
  expect(partOf(clip("1", { short: true, status: "confirmed", label: "A" }))).toBe("rule");
  /* Set aside, or only hinted: both are Maybe low quality, as in Characters, and not to do. */
  expect(partOf(clip("1", { status: "likely_low", low: 0.95 }))).toBe("aside");
  expect(partOf(clip("1", { status: "review", low: 0.6 }))).toBe("aside");
  expect(partOf(clip("1", { status: "auto", low: 0.6 }))).toBe("aside");
  /* A labeled line with the hint is the person's call. */
  expect(partOf(clip("1", { status: "confirmed", label: "A", low: 0.6 }))).toBe("clean");
  expect(partOf(clip("1", { status: "ignored", label: IGNORED }))).toBe("ignored");
});

test("lines the machine set aside are not given to the character to confirm", () => {
  const sure = clip("sure", { status: "review" });
  const aside = clip("aside", { status: "likely_low", low: 0.95 });
  /* Only the hint, below the set-aside bar: in the same part as the set-aside ones. */
  const hinted = clip("hinted", { status: "auto", low: 0.6 });
  expect(pendingOf([sure, aside, hinted]).map((c) => c.id)).toEqual(["sure"]);
  expect(rolePartOf(hinted, "A")).toBe("aside");
  expect(rolePartOf(sure, "A")).toBe("review");
  expect(rolePartOf(clip("auto", { status: "auto" }), "A")).toBe("auto");
  expect(rolePartOf(aside, "A")).toBe("aside");
});

test("in Characters, skipped lines are their own parts, and a short line labeled as the character is confirmed", () => {
  const short = clip("short", { short: true, status: "skipped" });
  const ignored = clip("ignored", { status: "ignored", label: IGNORED });
  const mine = clip("mine", { short: true, status: "confirmed", label: "A" });
  expect(rolePartOf(short, "A")).toBe("rule");
  expect(rolePartOf(ignored, "A")).toBe("ignored");
  expect(rolePartOf(mine, "A")).toBe("clean");
  expect(pendingOf([short, ignored, mine])).toEqual([]);
  expect(skippedOf([short, ignored, mine]).map((c) => c.id)).toEqual(["short", "ignored"]);
});

test("skipped lines say why: the rule or the person", () => {
  expect(skipReason(clip("1", { short: true, status: "skipped" }))).toBe("rule");
  expect(skipReason(clip("1", { status: "likely_low", low: 0.95 }))).toBeNull();
  expect(skipReason(clip("1", { short: true, label: IGNORED }))).toBe("ignored");
  expect(skipReason(clip("1", { low: 0.6 }))).toBeNull();
});
