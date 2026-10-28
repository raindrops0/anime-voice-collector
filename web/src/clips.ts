import type { Clip, Status } from "./api";
import { tr } from "./language";

/* "Not a target": not any of the target characters. It is a human judgment, labeled with Q. Unsure whether it is a
   target, several people talking with no target among them, cheering and sound effects: all get "other". */
export const OTHER = "__other__";

/* "Ignored": the person cannot tell who it is, such as a passer-by voiced by a target's voice actor. Labeled
   with X. Set aside: not used for training, not exported, not work to do, and listed under Ignored. */
export const IGNORED = "__ignored__";

/* "Not a target" typed as a name, in either language, means the "other" label, not a new character that looks the
   same. "Other", the button's old name, counts too. */
export const otherName = (s: string) =>
  ["不是目标", "not a target", "其他", "other"].includes(s.trim().toLowerCase());

/* How labels that are not character names are shown; for now only "other". */
export type LabelText = Record<string, string>;

export const statusText = (status: Status) =>
  ({
    confirmed: tr("已确认", "Confirmed"),
    auto: tr("机器有把握", "Confident"),
    review: tr("没把握", "Not confident"),
    unlabeled: tr("机器还没猜", "Not guessed yet"),
    skipped: tr("太短，已忽略", "Too short, ignored"),
    ignored: tr("已忽略", "Ignored"),
    likely_low: tr("可能质量低，先放一边", "Maybe low quality, set aside"),
  })[status];

/* The labels stay plain; the exact rules are in the hints, for those who want them. */
export const noVoiceprintTip = () =>
  tr(
    "短于 0.5 秒的台词算不出声纹（机器用来认声音的一组数字），所以机器不猜",
    "A line shorter than 0.5 seconds has no voiceprint (the numbers the machine uses to recognize a voice), so the machine makes no guess",
  );
export const skippedTip = () =>
  tr(
    "规则：短于 1 秒，或者台词不超过 2 个音节（比如「あっ」「うおーっ」），一般对训练用处不大，默认忽略，不算要处理的。想要的话也可以标：标了就和别的台词一样导出、用来训练，标成质量低的照样不导出",
    "Rule: shorter than 1 second, or at most 2 syllables of text (such as あっ or うおーっ): usually of little use for training, so ignored by default and not work to do. You can still label one: then it is exported and used for training like any other line, and low quality is still left out",
  );

export const ignoredTip = () =>
  tr(
    "听不出是谁（比如路人由目标角色的声优配音），就先放一边：不拿来训练，不导出，也不算要处理的。按 Backspace 可以取消",
    "When you cannot tell who it is (such as a passer-by voiced by a target's voice actor), set it aside: not used for training, not exported, and not work to do. Backspace takes it back",
  );

export const likelyLowTip = () =>
  tr(
    "机器判断这句很可能质量低（背景音重、几个人同时说话之类），先放一边，不算要处理的，也不会被当成机器有把握的导出。机器判错了的话，照常标人就行",
    "The machine finds this line very likely low quality (loud background, several people at once and so on), so it is set aside: not work to do, and not exported as a confident guess. If the machine is wrong, just label the character as usual",
  );

export const lowHintTip = (p: number) =>
  tr(
    `机器估计有 ${Math.round(p * 100)}% 的可能质量低。它是从你标的「质量低」学的，只是提醒，要不要标由你定`,
    `The machine puts the chance of low quality at ${Math.round(p * 100)}%. It learns from the lines you marked low quality; it is only a hint, and the call is yours`,
  );

export const optionalTip = () =>
  tr(
    "可选，能帮机器学：不算在橙色数字里。标了这些，机器下次猜人、猜质量会更准",
    "Optional, helps the machine learn: not in the orange count. Labeling them makes the machine's next guesses of who it is, and of low quality, better",
  );

export const maybeLowTip = () =>
  tr(
    "没人标过、机器估计可能质量低的台词（背景音重、几个人同时说话之类），包括它已经先放一边的。不算要处理的，不会被一键确认；判错了的话照常标人就行",
    "Lines nobody labeled that the machine thinks may be low quality (loud background, several people at once and so on), including the ones it set aside. Not work to do, and never confirmed at once; if it is wrong, just label the character as usual",
  );

/* Under "Ignored" are the short lines the rule leaves out and the lines a person ignored. Labeling a short line does
   not take it out of Scenes' "Ignored"; ignoring a line moves it there. */
export type SkipReason = "rule" | "ignored";

export const skipReason = (clip: Clip): SkipReason | null =>
  clip.label === IGNORED ? "ignored" : clip.short ? "rule" : null;

export const NEEDS_WORK = new Set<Status>(["review", "unlabeled"]);

/* A line nobody labeled that shows the "maybe low quality" hint, or that the machine set aside for it. In both views
   they are one part, "Maybe low quality", so the box and the hint on the lines agree. */
const lowFlagged = (c: Clip) => c.status === "likely_low" || c.low != null;

/* The parts Scenes can show, each with its own tick box. Every line is in exactly one part, so the ticked parts
   show exactly the lines they count: still to do in two kinds (the machine isn't sure, not guessed yet), the
   machine is confident, maybe low quality, labeled by a person (clean or low quality), or skipped for one of two
   reasons. */
export type Part = "review" | "unlabeled" | "auto" | "aside" | "clean" | "low" | SkipReason;

export const WORK_PARTS: Part[] = ["review", "unlabeled"];

export const DONE_PARTS: Part[] = ["clean", "low"];

export const SKIP_PARTS: Part[] = ["rule", "ignored"];

export const PARTS: Part[] = [...WORK_PARTS, "auto", "aside", ...DONE_PARTS, ...SKIP_PARTS];

export const partOf = (clip: Clip): Part =>
  skipReason(clip) ??
  (!clip.label && lowFlagged(clip)
    ? "aside"
    : NEEDS_WORK.has(clip.status)
      ? (clip.status as Part)
      : clip.status === "auto"
        ? "auto"
        : clip.unusable
          ? "low"
          : "clean");

/* Each target character has two choices: clean, and "low quality" (Shift + number). Only targets have it;
   "other" is never exported anyway. There used to be a separate "several people", now merged into low quality. */
export const newTip = () =>
  tr(
    "新建一个目标角色，名字可以以后再起；有画面时接着截头像",
    "Make a new target character; you can name it later. With video, crop an avatar next",
  );
export const lowTip = () =>
  tr(
    "背景音太重、有人同时出声之类，不能进干净数据集。不拿来认人，也不导出",
    "Too much background sound, someone talking at the same time and so on: not fit for a clean dataset. " +
      "Not used to recognize anyone, and left out on export",
  );

export const confidence = (clip: Clip) => clip.guess[0]?.p ?? 0;

export const chanceOf = (clip: Clip, name: string | undefined) =>
  clip.guess.find((g) => g.name === name)?.p ?? 0;

/* The target character the machine finds most likely. "Not a target" does not count. */
export const bestTarget = (clip: Clip) => clip.guess.find((g) => g.name !== OTHER);

export interface Who {
  name: string;
  human: boolean;
  p?: number;
}

/* Who a clip belongs to now: the human label first, else the machine's top guess. */
export function whoOf(clip: Clip): Who | null {
  if (clip.label) return { name: clip.label, human: true };
  if (clip.guess.length) return { name: clip.guess[0].name, human: false, p: clip.guess[0].p };
  return null;
}

/* To check in the Characters view: given to this character by the machine, not yet confirmed, least sure first.
   Lines that may be low quality are not in it: "Confirm the rest" must not confirm them as clean. */
export const pendingOf = (clips: Clip[]) =>
  clips
    .filter((c) => !c.label && !c.maybe && !c.short && !lowFlagged(c))
    .sort((a, b) => confidence(a) - confidence(b));

/* Given to this character by the machine, but maybe low quality (set aside or only hinted); least likely low first. */
export const setAsideOf = (clips: Clip[]) =>
  clips
    .filter((c) => !c.label && !c.maybe && !c.short && lowFlagged(c))
    .sort((a, b) => (a.low ?? 0) - (b.low ?? 0));

/* Given to this character by the machine, but ignored: short by the rule and not labeled, or ignored by a person. In
   the server's order: by time for a target, most like some target first for "Not a target". */
export const skippedOf = (clips: Clip[]) =>
  clips.filter((c) => c.label === IGNORED || (!c.label && c.short));

/* Maybe missed: not given to this character, but with a fair chance of being them. The server already sorted
   them most likely first; they are re-sorted only when the list is updated, so it doesn't jump under your hand. */
export const maybeListOf = (clips: Clip[]) => clips.filter((c) => c.maybe);

/* The lines that join or leave Maybe missed when the server's newest list of them, `missed`, replaces the list's. */
export const missedChanges = (clips: Clip[], missed: Clip[]) => {
  const now = new Set(maybeListOf(clips).map((c) => c.id));
  const next = new Set(missed.map((c) => c.id));
  return [...[...now].filter((id) => !next.has(id)), ...[...next].filter((id) => !now.has(id))];
};

/* The list with the server's newest Maybe missed lines in place of its own, most likely first: a line no longer
   missed stays only if it belongs to the list some other way, which the caller checks. */
export const withMissed = (clips: Clip[], missed: Clip[]) => {
  const next = new Set(missed.map((c) => c.id));
  const rest = clips
    .filter((c) => !next.has(c.id))
    .map((c) => (c.maybe ? { ...c, maybe: false } : c));
  return [...rest, ...missed];
};

/* Confirmed lines in the server's order: by time for a target, most like some target first for "other". */
export const confirmedOf = (clips: Clip[], role: string | null) =>
  clips.filter((c) => c.label === role);

/* A character's lines in the order the Characters list shows them, before the tick boxes filter them. */
export const roleOrder = (clips: Clip[], role: string | null) => [
  ...pendingOf(clips),
  ...maybeListOf(clips),
  ...setAsideOf(clips),
  ...confirmedOf(clips, role),
  ...skippedOf(clips),
];

/* The parts Characters can show for one character, each with its own tick box. Given by the machine and still to do,
   in two kinds: the machine isn't sure, and confident. Then the lines it gave but that may be low quality, the lines
   it may have missed, the confirmed ones, clean or low quality, and the skipped ones, as in Scenes. A short line
   labeled as this character is confirmed here, so its length counts toward theirs. */
export type RolePart = "review" | "auto" | "aside" | "maybe" | "clean" | "low" | SkipReason;

/* The lines counted in orange on the Characters tab, and the ones "Confirm the rest" confirms. */
export const ROLE_WORK_PARTS: RolePart[] = ["review", "auto"];

export const ROLE_PARTS: RolePart[] = [
  "review",
  "auto",
  "aside",
  "maybe",
  "clean",
  "low",
  "rule",
  "ignored",
];

/* Only To do is ticked at first, as in Scenes. The ticks are then remembered in the browser. */
export const ROLE_PARTS_FIRST: RolePart[] = ROLE_WORK_PARTS;

/* Null for a line just labeled as someone else: it is in no part until the list is fetched again. */
export const rolePartOf = (clip: Clip, role: string | null): RolePart | null =>
  clip.label === role
    ? clip.unusable
      ? "low"
      : "clean"
    : clip.label === IGNORED
      ? "ignored"
      : clip.maybe
        ? "maybe"
        : clip.label
          ? null
          : clip.short
            ? "rule"
            : lowFlagged(clip)
              ? "aside"
              : clip.status === "auto"
                ? "auto"
                : "review";
