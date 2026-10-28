import { cn } from "cn";
import { XIcon } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { currentLanguage, type Language, tr } from "../language";
import { withKeys } from "./Keys";
import type { View } from "./TopBar";

/* ───────────── Walk-through ─────────────
   A few steps over the real screen: each one dims the page, lights up one part of it and says what it is for. Two
   steps wait for the person to do the thing (tick lines, make a target), so they label their first character on
   the way. The first card asks for the page language before anything else. The page stays usable underneath, keys
   included. Opened by itself the first time a workspace with
   episodes is opened and nothing is labeled yet; afterwards from the Guide button in the top bar or the shortcuts
   dialog. */
export const GUIDE_SEEN = "guide-seen";

/* What the steps that wait for the person read. */
export interface GuideProgress {
  ticked: number;
  targets: number;
}

interface Step {
  title: string;
  body: ReactNode;
  /* The data-tour name of the part to light up; with none, or when it is not on the page, the card sits in the
     middle. */
  target?: string;
  /* The view the step is about, shown when the step starts. */
  view?: View;
  /* The step goes on by itself once this is true; `start` is the progress when the step began. */
  done?: (now: GuideProgress, start: GuideProgress) => boolean;
  /* What to do to go on, shown while waiting. */
  todo?: string;
  /* The card that asks for the page language: it goes on only through one of the language buttons. */
  language?: boolean;
}

const steps = (demo: boolean): Step[] => [
  {
    /* In both languages, since the person may not read the one shown. */
    title: "界面语言 / Language",
    body: "先选界面的语言，之后随时可以在右上角切换。\nChoose the language of the page first; you can switch it at the top right at any time.",
    language: true,
  },
  {
    title: tr("带你走一遍", "A quick walk-through"),
    body: tr(
      "这个工具帮你从动画里收集一个角色的台词。接下来一步步介绍主要界面，并带你亲手标出第一个角色，大约两分钟。随时可以按 Esc 退出，之后点右上角的「指南」再走一遍。",
      "This tool collects one character's lines from anime. The next steps show the main parts of the screen and have you label your first character yourself, in about two minutes. Press Esc to leave at any time; the Guide button at the top right runs it again.",
    ),
  },
  {
    title: tr("四个页面", "Four views"),
    target: "views",
    view: "groups",
    body: withKeys(
      tr(
        "按使用的顺序排：「分组」[G]、「场景」[S] 看当前这一集，在左边的菜单里换集；「角色」[O] 和「导出」[E] 包括全部集数。",
        "In the order you use them. Groups [G] and Scenes [S] show one episode, picked in the menu on the left; Characters [O] and Export [E] cover all episodes.",
      ),
    ),
  },
  {
    title: tr("画面和声音", "Picture and sound"),
    target: "player",
    body: withKeys(
      tr(
        "选中的台词在这里播放。[空格] 重播，[J] / [K] 去下一句 / 上一句。「只听人声」是去掉音乐后的声音；「多放前后文」多放几秒，听听上下文。",
        'The selected line plays here. [Space] replays it, [J] / [K] go to the next / previous line. "Vocals only" is the voice with the music removed; "More context" plays a few seconds around it.',
      ),
    ),
  },
  {
    title: tr("一组台词", "A group of lines"),
    target: "group",
    view: "groups",
    body: tr(
      "机器把听起来像同一个人的台词分成一组，但可能混进别人。点一句就能听，再勾上同一个人说的那些。",
      "The machine put lines that sound like one person into a group, but others may be mixed in. Click a line to hear it, then tick the ones the same person says.",
    ),
    done: (now) => now.ticked > 0,
    todo: tr("勾上至少一句就继续", "Tick at least one line to go on"),
  },
  {
    title: tr("新目标", "New target"),
    target: "new",
    body: withKeys(
      tr(
        "点「新目标」或按 [N]，把勾上的台词交给一个新角色。可以起个名字，在画面上拖动圆圈选头像，再按「保存」。",
        'Press "New target" or [N] to give the ticked lines to a new character. Type a name if you like, drag the circle on the picture to pick an avatar, and press Save.',
      ),
    ),
    done: (now, start) => now.targets > start.targets,
    todo: tr("做好一个新目标就继续", "Make a new target to go on"),
  },
  {
    title: tr("底栏：这句是谁", "The bottom bar: who is it"),
    target: "dock",
    body: withKeys(
      tr(
        "你的角色现在在底栏，前面的数字就是它的键。对选中的台词：按数字键标成这个角色，[Q] 标成「不是目标」，[Shift] + 数字键标成质量低（背景太吵或两人同时说话），[X] 忽略谁也认不出的一句。",
        'Your character is now on the bottom bar, and its number is its key. For the selected line: the number labels it as that character, [Q] as "Not a target", [Shift] + the number marks it low quality (loud background or two people at once), and [X] ignores a line nobody can tell.',
      ),
    ),
  },
  {
    title: tr("场景", "Scenes"),
    target: "main",
    view: "scene",
    body: withKeys(
      tr(
        "这一集的每句台词按顺序排，边看边标。一个角色确认满 10 句、别人也标了几句「不是目标」以后，机器就开始猜：猜对了按 [Enter]。每标一句，它都马上重新学。",
        'Every line of the episode in order, to label while you watch. Once a character has 10 confirmed lines and a few others are "Not a target", the machine starts guessing: press [Enter] when it is right. It retrains after every label.',
      ),
    ),
  },
  {
    title: tr("角色", "Characters"),
    target: "main",
    view: "roles",
    body: withKeys(
      tr(
        "机器分给一个角色的全部台词，包括全部集数，最不自信的排在前面。改掉错的，剩下的按 [Shift]+[Enter] 一起确认；下面还有它可能漏掉的台词。",
        "Everything the machine gave one character, from all episodes, least sure first. Fix the wrong ones and confirm the rest with [Shift]+[Enter]; below are the lines it may have missed.",
      ),
    ),
  },
  {
    title: tr("撤销", "Undo"),
    target: "undo",
    body: withKeys(
      tr(
        "[Z] 撤销上一步，接着按就继续往回；旁边的时钟可以单独撤回更早的某一步。",
        "[Z] undoes the last step, and again for the one before; the clock next to it takes back any earlier step alone.",
      ),
    ),
  },
  {
    title: tr("就这些", "That's it"),
    target: "guide",
    body: withKeys(
      tr(
        `标够了就去「导出」[E]，写成 GPT-SoVITS 或 RVC 用的数据集${demo ? "（试用里导出是关闭的）" : ""}。[?] 列出全部快捷键，「指南」随时再走一遍。`,
        `When you have enough, Export [E] writes a dataset for GPT-SoVITS or RVC${demo ? " (exporting is off in the demo)" : ""}. [?] lists every shortcut, and Guide runs this walk-through again.`,
      ),
    ),
  },
];

/* Room around the lit part, and between it and the card. */
const PAD = 6;
const GAP = 12;
const CARD_WIDTH = 340;
/* About the size of the "You are here" label under the marked tab. */
const TAG_HEIGHT = 20;
const TAG_WIDTH = 90;

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/* Where the parts with this name are on screen, as one box; null when none is shown. */
function find(target: string | undefined): Box | null {
  if (!target) return null;
  const rects = [...document.querySelectorAll(`[data-tour="${target}"]`)]
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.height > 0);
  if (!rects.length) return null;
  const left = Math.max(0, Math.min(...rects.map((r) => r.left)) - PAD);
  const top = Math.max(0, Math.min(...rects.map((r) => r.top)) - PAD);
  const right = Math.min(innerWidth, Math.max(...rects.map((r) => r.right)) + PAD);
  const bottom = Math.min(innerHeight, Math.max(...rects.map((r) => r.bottom)) + PAD);
  return { left, top, width: right - left, height: bottom - top };
}

/* The outline of the whole window with a rounded hole over each box. Filled even-odd, so only the holes are
   left out. Two holes must not overlap, or the overlap is dimmed again. */
function dimmed(holes: Box[]): string {
  const r = 8;
  const hole = ({ left: x, top: y, width: w, height: h }: Box) =>
    `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}` +
    `A${r} ${r} 0 0 1 ${x + w - r} ${y + h}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}` +
    `V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`;
  return `M0 0H${innerWidth}V${innerHeight}H0Z` + holes.map(hole).join("");
}

/* Where the parts with this name are, looked up on every frame: lists scroll, cards are laid out after they load,
   and the bottom bar grows a chip when a target is made. */
function useLit(target: string | undefined): Box | null {
  const [lit, setLit] = useState<Box | null>(null);
  useEffect(() => {
    let frame = 0;
    const look = () => {
      const box = find(target);
      setLit((old) =>
        !box || !old
          ? box === old
            ? old
            : box
          : Math.abs(box.left - old.left) +
                Math.abs(box.top - old.top) +
                Math.abs(box.width - old.width) +
                Math.abs(box.height - old.height) <
              1
            ? old
            : box,
      );
      frame = requestAnimationFrame(look);
    };
    look();
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return lit;
}

/* The card goes below the lit part, or above, right or left, wherever it fits first; in the middle when nothing
   is lit or it fits nowhere. */
function place(lit: Box | null, height: number): { left: number; top: number } {
  const width = Math.min(CARD_WIDTH, innerWidth - 2 * GAP);
  const middle = { left: (innerWidth - width) / 2, top: (innerHeight - height) / 2 };
  if (!lit) return middle;
  const across = Math.min(
    Math.max(lit.left + lit.width / 2 - width / 2, GAP),
    innerWidth - width - GAP,
  );
  const down = Math.min(Math.max(lit.top, GAP), innerHeight - height - GAP);
  if (lit.top + lit.height + GAP + height <= innerHeight - GAP)
    return { left: across, top: lit.top + lit.height + GAP };
  if (lit.top - GAP - height >= GAP) return { left: across, top: lit.top - GAP - height };
  if (lit.left + lit.width + GAP + width <= innerWidth - GAP)
    return { left: lit.left + lit.width + GAP, top: down };
  if (lit.left - GAP - width >= GAP) return { left: lit.left - GAP - width, top: down };
  return { left: across, top: innerHeight - height - GAP };
}

export function Guide({
  progress,
  demo,
  hidden,
  setView,
  onLanguage,
  onClose,
}: {
  progress: GuideProgress;
  demo: boolean;
  /* Another dialog is open, such as naming the new target: the walk-through steps aside until it closes. */
  hidden: boolean;
  setView: (view: View) => void;
  onLanguage: (language: Language) => void;
  /* `finished`: the last step was reached and closed with its button. */
  onClose: (finished: boolean) => void;
}) {
  const all = steps(demo);
  const [at, setAt] = useState(0);
  const step = all[at];
  const last = at === all.length - 1;
  const [start, setStart] = useState(progress);
  const done = step.done?.(progress, start) ?? true;

  const go = (next: number) => {
    const view = all[next].view;
    if (view) setView(view);
    setStart(progress);
    setAt(next);
  };
  useEffect(() => {
    if (step.view) setView(step.view);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only for the first step shown
  }, []);
  /* A step that waits goes on by itself a moment after the person did the thing, so they see it worked. */
  useEffect(() => {
    if (!step.done || !done || last) return;
    const timer = window.setTimeout(() => go(at + 1), 600);
    return () => window.clearTimeout(timer);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- when the step is done
  }, [done, at]);

  const lit = useLit(step.target);
  /* The tab of the view open now, lit too and marked, so the person always sees which view they are on. */
  const page = step.language ? undefined : all.slice(0, at + 1).findLast((s) => s.view)?.view;
  const tab = useLit(page && `view-${page}`);
  /* The tab gets its own hole only when the lit part does not already hold it, as the view tabs do. */
  const inside = (a: Box, b: Box) =>
    a.left >= b.left &&
    a.top >= b.top &&
    a.left + a.width <= b.left + b.width &&
    a.top + a.height <= b.top + b.height;
  const holes = [lit, tab && lit && inside(tab, lit) ? null : tab].filter((b): b is Box => !!b);
  const rings = [lit, tab].filter((b): b is Box => !!b);

  /* The card's height, which changes with each step's text, decides whether it fits above or below. */
  const [cardHeight, setCardHeight] = useState(200);
  const card = useCallback((node: HTMLDivElement | null) => {
    if (!node) return;
    const watch = new ResizeObserver(() => setCardHeight(node.offsetHeight));
    watch.observe(node);
    return () => watch.disconnect();
  }, []);
  const cardWidth = Math.min(CARD_WIDTH, innerWidth - 2 * GAP);
  const placed = place(lit, cardHeight);
  /* The card must not cover the marked tab or its label: if it would, it moves down below them. */
  const tabBottom = tab ? tab.top + tab.height + 4 + TAG_HEIGHT : 0;
  const covers =
    tab &&
    placed.top < tabBottom &&
    placed.left < tab.left + Math.max(tab.width, TAG_WIDTH) &&
    placed.left + cardWidth > tab.left;
  const spot = covers
    ? { ...placed, top: Math.min(tabBottom + GAP, innerHeight - cardHeight - GAP) }
    : placed;

  if (hidden) return null;
  return createPortal(
    /* Nothing here catches the mouse but the card, so the lit part, and the rest of the page, can be used. */
    <div className="pointer-events-none fixed inset-0 z-50">
      {/* The page dimmed, with a hole over each lit part. */}
      <svg className="absolute inset-0 size-full" aria-hidden="true">
        <path d={dimmed(holes)} fill="black" fillOpacity={0.45} fillRule="evenodd" />
      </svg>
      {rings.map((b, i) => (
        <div
          key={i}
          className="absolute rounded-lg ring-2 ring-primary transition-all duration-300"
          style={b}
        />
      ))}
      {tab && (
        <div
          className="absolute rounded-md bg-primary px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap text-primary-foreground shadow-sm transition-all duration-300"
          style={{ left: tab.left, top: tab.top + tab.height + 4 }}
        >
          {tr("当前页面", "You are here")}
        </div>
      )}
      <div
        ref={card}
        role="dialog"
        aria-label={step.title}
        className="pointer-events-auto absolute flex flex-col gap-2 rounded-xl border bg-popover p-4 text-sm text-popover-foreground shadow-lg transition-[left,top] duration-300"
        style={{ ...spot, width: cardWidth }}
      >
        <div className="flex items-center gap-2">
          <b className="font-semibold">{step.title}</b>
          {/* The language card is not counted: the steps are numbered from the one after it. */}
          {at > 0 && (
            <span className="text-xs text-muted-foreground">
              {at} / {all.length - 1}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            className="-mt-1 -mr-2 ml-auto"
            onClick={() => onClose(false)}
            aria-label={tr("退出指南", "Leave the walk-through")}
          >
            <XIcon />
          </Button>
        </div>
        <div className="text-[13px] leading-relaxed whitespace-pre-line">{step.body}</div>
        {step.todo && (
          <div className={cn("text-xs", done ? "text-success" : "text-primary")}>
            {done ? tr("做到了 ✓", "Done ✓") : step.todo}
          </div>
        )}
        <div className="mt-1 flex items-center gap-2">
          {at > 0 && (
            <Button variant="ghost" size="sm" onClick={() => go(at - 1)}>
              {tr("上一步", "Back")}
            </Button>
          )}
          <span className="flex-1" />
          {step.language ? (
            (["zh", "en"] as const).map((language) => (
              <Button
                key={language}
                size="sm"
                variant={language === currentLanguage() ? "default" : "outline"}
                onClick={() => {
                  onLanguage(language);
                  go(at + 1);
                }}
              >
                {language === "zh" ? "中文" : "English"}
              </Button>
            ))
          ) : last ? (
            <Button size="sm" onClick={() => onClose(true)}>
              {tr("开始标注", "Start labeling")}
            </Button>
          ) : done ? (
            <Button size="sm" onClick={() => go(at + 1)}>
              {at === 1 ? tr("开始", "Start") : tr("下一步", "Next")}
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => go(at + 1)}>
              {tr("跳过这步", "Skip this step")}
            </Button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
