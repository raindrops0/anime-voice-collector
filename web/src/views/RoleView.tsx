import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "cn";
import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import type { Clip, Counts as RoleCounts, Role, Roles, Summary } from "../api";
import {
  confirmedOf,
  IGNORED,
  ignoredTip,
  type LabelText,
  lowTip,
  maybeListOf,
  maybeLowTip,
  optionalTip,
  OTHER,
  pendingOf,
  ROLE_WORK_PARTS,
  type RolePart,
  rolePartOf,
  setAsideOf,
  skippedOf,
  skippedTip,
} from "../clips";
import { Avatar } from "../components/Avatar";
import { Empty } from "../components/Notes";
import { PartFilter, type PartItem } from "../components/PartFilter";
import { RoleName } from "../components/RoleName";
import { Row } from "../components/Row";
import { Tip } from "../components/Tip";
import { howLong } from "../format";
import { lines, tr } from "../language";
import { TODO_COUNT } from "../looks";

/* ───────────── Characters view: check the machine's calls per character ───────────── */

/* The numbers on the right of a character row: lines confirmed, lines the machine gave them, and below,
   the total length of the confirmed lines. */
function Counts({ info }: { info: RoleCounts }) {
  return (
    <span className="text-right text-[11px] text-muted-foreground tabular-nums">
      {info.confirmed}
      {info.to_check ? (
        <>
          {" "}
          <span className={cn(TODO_COUNT, "inline-block")}>{info.to_check}</span>
        </>
      ) : (
        ""
      )}
      {info.seconds > 0 && (
        <>
          <br />
          <Tip text={tr("确认过的台词累计时长", "Total length of confirmed lines")}>
            <span>{howLong(info.seconds)}</span>
          </Tip>
        </>
      )}
    </span>
  );
}

/* One row of the character list on the left. */
const ITEM =
  "grid grid-cols-[auto_1fr_auto] items-center gap-x-3 rounded-lg border border-transparent px-2 py-1.5 hover:bg-muted/60";
const ITEM_ON = "border-primary/40 bg-accent hover:bg-accent";

/* A short gray heading above a part of the list. */
const SECTION_TITLE = "mx-1 mt-[18px] mb-1.5 text-xs text-muted-foreground";

/* The lines of the list on the right, with the headings between its parts. */
type Item =
  | { kind: "row"; clip: Clip; maybeOf?: string; showTarget?: boolean }
  | { kind: "maybe" }
  | { kind: "aside" }
  | { kind: "confirmed" }
  | { kind: "skipped" };

/* How a part of the list is sorted: by time for a target, and for "Not a target" most like some target first, so
   wrong labels show up early. */
const inTimeOrder = () => tr("按时间排", "in time order");
const mostLikeTarget = () => tr("最像某个目标角色的在前", "most like a target character first");

/* A first guess at a line's height before it is drawn and measured; one line of text with its pills. */
const ROW_HEIGHT = 62;

interface RoleViewProps {
  state: Summary;
  roles: Roles;
  labelText: LabelText;
  role: string | null;
  setRole: (name: string) => void;
  /* The lines as laid out: where each sits comes from these, what it shows from `live`. */
  clips: Clip[];
  /* The newest version of each line, by ID. */
  live: Record<string, Clip | undefined>;
  /* The character's lines have not come yet. */
  loading: boolean;
  focus: string | null;
  setFocus: (id: string) => void;
  onConfirmRest: () => void;
  parts: Set<RolePart>;
  setParts: (parts: Set<RolePart>) => void;
  onRename: () => void;
  onToggleTarget: () => void;
  onAvatar: () => void;
  canCrop: boolean;
  flashes: Set<string>;
  playing: boolean;
  setPlaying: (on: boolean) => void;
}

export function RoleView({
  state,
  roles,
  labelText,
  role,
  setRole,
  clips,
  live,
  loading,
  focus,
  setFocus,
  onConfirmRest,
  parts,
  setParts,
  onRename,
  onToggleTarget,
  onAvatar,
  canCrop,
  flashes,
  playing,
  setPlaying,
}: RoleViewProps) {
  const list = state.roles;
  const other = role === OTHER;
  /* "Not a target" has no entry of its own, so it gets an empty one. */
  const current: Partial<Role> | undefined = other ? {} : role ? roles[role] : undefined;
  const info: RoleCounts | undefined = other ? state.other : list.find((r) => r.name === role);
  const name = other ? labelText[OTHER] : role;
  const allPending = pendingOf(clips);
  const allMaybe = maybeListOf(clips);
  const allAside = setAsideOf(clips);
  const allConfirmed = confirmedOf(clips, role);
  const allSkipped = skippedOf(clips);
  const low = allConfirmed.filter((c) => c.unusable).length;
  /* The lines of the ticked parts. */
  const ticked = (c: Clip) => {
    const part = rolePartOf(c, role);
    return !!part && parts.has(part);
  };
  const pending = allPending.filter(ticked);
  /* What "Confirm the rest" confirms: the lines of To do shown, whose newest guess is still this character. */
  const confirmable = pending.filter((c) => (live[c.id] ?? c).guess[0]?.name === role).length;
  const maybe = allMaybe.filter(ticked);
  const aside = allAside.filter(ticked);
  const confirmed = allConfirmed.filter(ticked);
  const skipped = allSkipped.filter(ticked);
  /* The counts of each part are on its box; above the list is what the ticked ones add up to. */
  const shown = [...pending, ...maybe, ...aside, ...confirmed, ...skipped];
  const shownCount = shown.length;
  const shownSeconds = shown.reduce((s, c) => s + c.duration, 0);
  /* Confirmed first, then To do, then the rest, as in Scenes. */
  const filterItems: PartItem<RolePart>[] = [
    /* "Not a target" has no low quality, so its confirmed lines are one box. */
    other
      ? {
          keys: ["clean", "low"],
          label: tr("确认过的", "Confirmed"),
          count: allConfirmed.length,
          look: "confirmed",
        }
      : {
          keys: ["clean", "low"],
          label: tr("确认过的", "Confirmed"),
          count: allConfirmed.length,
          children: [
            {
              keys: ["clean"],
              label: tr("干净", "Clean"),
              count: allConfirmed.length - low,
              look: "confirmed",
            },
            {
              keys: ["low"],
              label: tr("质量低", "Low quality"),
              count: low,
              tip: lowTip(),
              look: "unusable",
            },
          ],
        },
    {
      /* The lines counted in orange on the Characters tab, and the ones "Confirm the rest" confirms. */
      keys: ROLE_WORK_PARTS,
      label: tr("要处理的", "To do"),
      count: allPending.length,
      todo: true,
      tip: tr(
        "机器归给这个角色、还没人确认的台词",
        "Lines the machine gave this character that no one has confirmed yet",
      ),
      children: [
        {
          keys: ["review"],
          label: tr("不自信", "Not confident"),
          count: allPending.filter((c) => c.status !== "auto").length,
          look: "review",
        },
        {
          keys: ["auto"],
          label: tr("很自信", "Confident"),
          count: allPending.filter((c) => c.status === "auto").length,
          look: "auto",
        },
      ],
    },
    {
      keys: ["maybe", "aside"],
      label: tr("可选", "Optional"),
      count: allMaybe.length + allAside.length,
      tip: optionalTip(),
      children: [
        {
          keys: ["maybe"],
          label: tr("可能漏掉的", "Maybe missed"),
          count: allMaybe.length,
          look: "maybe",
        },
        {
          keys: ["aside"],
          label: tr("可能质量低", "Maybe low quality"),
          count: allAside.length,
          tip: maybeLowTip(),
          look: "likely_low",
        },
      ],
    },
    {
      keys: ["rule", "ignored"],
      label: tr("忽略的", "Ignored"),
      count: allSkipped.length,
      tip: tr(
        "机器归给这个角色、但被忽略的台词：不算要处理的，也不会被当成机器很自信的导出",
        "Lines the machine gave this character but that are ignored: not work to do, and not exported as confident guesses",
      ),
      children: [
        {
          keys: ["rule"],
          label: tr("太短", "Too short"),
          count: allSkipped.filter((c) => c.label !== IGNORED).length,
          tip: skippedTip(),
          look: "skipped",
        },
        {
          keys: ["ignored"],
          label: tr("你忽略的", "Ignored by you"),
          count: allSkipped.filter((c) => c.label === IGNORED).length,
          tip: ignoredTip(),
          look: "ignored",
        },
      ],
    },
  ];
  /* Who the machine gave these lines to, as written inside a sentence. */
  const them = other ? tr("「不是目标」", '"Not a target"') : role;
  /* A character can have thousands of lines, and drawing them all made every key press take half a second. So the
     list on the right is one long scroll, but only the lines near the screen are drawn. */
  const items: Item[] = [
    ...pending.map((clip): Item => ({ kind: "row", clip, showTarget: other })),
    ...(maybe.length > 0 ? [{ kind: "maybe" } as Item] : []),
    ...maybe.map((clip): Item => ({ kind: "row", clip, maybeOf: role ?? undefined })),
    ...(aside.length > 0 ? [{ kind: "aside" } as Item] : []),
    ...aside.map((clip): Item => ({ kind: "row", clip, showTarget: other })),
    ...(confirmed.length > 0 ? [{ kind: "confirmed" } as Item] : []),
    ...confirmed.map((clip): Item => ({ kind: "row", clip, showTarget: other })),
    ...(skipped.length > 0 ? [{ kind: "skipped" } as Item] : []),
    ...skipped.map((clip): Item => ({ kind: "row", clip, showTarget: other })),
  ];
  /* The character's heading, tick boxes and button stay on top while the list scrolls; so does the list of
     characters when it is a row above them. Their heights change when they wrap, so they are measured: `pick` is
     the row of characters (0 when it is a column on the left), `covered` how much of the page they hide. */
  const picker = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState({ pick: 0, covered: 0 });
  /* The heading is drawn only once the character is known, which can come after the role. */
  const known = !!current;
  useLayoutEffect(() => {
    const row = picker.current;
    const box = head.current;
    if (!row || !box) return;
    const measure = () => {
      const pick = getComputedStyle(row).flexDirection === "row" ? row.offsetHeight : 0;
      const covered = pick + box.offsetHeight;
      setStuck((s) => (s.pick === pick && s.covered === covered ? s : { pick, covered }));
    };
    const watch = new ResizeObserver(measure);
    watch.observe(row);
    watch.observe(box);
    return () => watch.disconnect();
  }, [role, known]);
  const listRef = useRef<HTMLDivElement>(null);
  const [scroller, setScroller] = useState<HTMLElement | null>(null);
  /* Where the list starts inside the scrolling page, below the character's heading. */
  const [margin, setMargin] = useState(0);
  // oxlint-disable-next-line react-hooks/exhaustive-deps -- measured after every render; sets state only when it moved
  useLayoutEffect(() => {
    const list = listRef.current;
    const page = list?.closest("main") ?? null;
    if (page !== scroller) setScroller(page);
    if (list && page) {
      const top =
        list.getBoundingClientRect().top - page.getBoundingClientRect().top + page.scrollTop;
      if (Math.abs(top - margin) > 0.5) setMargin(top);
    }
  });
  // oxlint-disable-next-line react/incompatible-library -- the compiler then leaves this view unmemoized, which is fine
  const lister = useVirtualizer({
    count: items.length,
    getScrollElement: () => scroller,
    estimateSize: (i) => (items[i].kind === "row" ? ROW_HEIGHT : 40),
    getItemKey: (i) => {
      const item = items[i];
      return item.kind === "row" ? item.clip.id : item.kind;
    },
    overscan: 8,
    scrollMargin: margin,
    /* A selected line comes into view below the parts that stay on top. */
    scrollPaddingStart: stuck.covered,
  });
  const focusAt = items.findIndex((item) => item.kind === "row" && item.clip.id === focus);
  /* The selected line comes into view, whether J/K, playing all or a click on the picture side picked it. */
  useEffect(() => {
    if (focusAt >= 0) lister.scrollToIndex(focusAt, { align: "auto" });
  }, [focusAt, lister]);
  /* The list on the left is as wide as its longest row, up to 230px. When the list side of the page is narrow
     (the divider can make it so), the list goes on top as a row of characters instead. */
  return (
    <div
      style={{ "--pick": `${stuck.pick}px` } as CSSProperties}
      className="grid grid-cols-[auto_minmax(0,1fr)] gap-[18px] @max-xl:grid-cols-1"
    >
      {/* Characters that are not targets are listed under the target characters, with a lighter name. "Not a target"
          goes at the very bottom, with a divider line above it. As a row on top, -top-2 cancels the top padding of
          the page, so lines don't show through above it. */}
      <div
        ref={picker}
        className="sticky top-2.5 mt-2.5 flex max-h-[calc(100vh-170px)] w-max max-w-[230px] min-w-40 flex-col gap-0.5 self-start overflow-y-auto @max-xl:-top-2 @max-xl:z-[4] @max-xl:-mt-2 @max-xl:max-h-none @max-xl:w-auto @max-xl:max-w-none @max-xl:flex-row @max-xl:flex-wrap @max-xl:bg-background @max-xl:pt-[18px]"
      >
        {list.map((r) => (
          <Tip
            key={r.name}
            text={
              r.target
                ? ""
                : tr(
                    "不是目标角色：机器不再猜这个角色，已有的标签照样留着",
                    "Not a target character: the machine no longer guesses them, their labels stay",
                  )
            }
          >
            <div className={cn(ITEM, r.name === role && ITEM_ON)} onClick={() => setRole(r.name)}>
              <Avatar role={r} name={r.name} size="md" />
              <RoleName
                role={r}
                name={r.name}
                className={cn(!r.target && "text-muted-foreground")}
              />
              <Counts info={r} />
            </div>
          </Tip>
        ))}
        <Separator className="my-1 @max-xl:hidden" />
        <Tip text={tr("不是任何一个目标角色", "Not any of the target characters")}>
          <div className={cn(ITEM, other && ITEM_ON)} onClick={() => setRole(OTHER)}>
            <Avatar blank={true} size="md" />
            <span>{labelText[OTHER]}</span>
            <Counts info={state.other} />
          </div>
        </Tip>
      </div>
      <div>
        {!current || !role ? (
          <Empty title={tr("选一个角色", "Pick a character")}>
            <p>
              {tr(
                "左边上面是目标角色，就是你要收集的人；其余的人一律标「不是目标」。灰色数字是确认过的句数，橙色是机器归进来、还没人确认的句数，下面是确认过的台词累计多长。",
                'At the top left are the target characters, the people you want to collect; everyone else is labeled "Not a target". The gray number is lines confirmed, the orange one is lines the machine gave them that no one has confirmed yet, and below is the total length of the confirmed lines.',
              )}
            </p>
          </Empty>
        ) : (
          <>
            {/* Stays on top: at the page's top, or below the row of characters. It starts where it stays (its negative
                margin takes back the space above it), so it never moves a little before it stays. */}
            <div
              ref={head}
              className="pb-2@max-xl:top-[calc(var(--pick)-0.5rem)] sticky -top-2 z-[3] -mt-2 border-b bg-background pt-[18px] @max-xl:-mt-[18px]"
            >
              {/* Beside the avatar: the name and length on one row, and under them the buttons that manage the
                  character, so they read as being about it. Playing is about the list, so it is in the bar above it. */}
              <div className="flex items-center gap-x-3 pt-1 pb-2">
                {other ? (
                  <Avatar blank={true} size="lg" />
                ) : (
                  <Avatar
                    role={current as Role}
                    name={role}
                    size="lg"
                    onClick={canCrop ? onAvatar : null}
                    title={
                      canCrop
                        ? tr(
                            "从左边的画面里截一块当头像",
                            "Crop an avatar from the picture on the left",
                          )
                        : tr(
                            "左边放出画面后，可以从画面里截头像",
                            "Once the picture on the left shows, you can crop an avatar from it",
                          )
                    }
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2.5">
                    <h2 className="text-lg leading-tight font-semibold">
                      {other ? name : <RoleName role={current as Role} name={role} />}
                    </h2>
                    {/* How many lines each part holds is in the tick boxes below; here only how long. */}
                    <div className="text-xs text-muted-foreground">
                      {info && info.seconds > 0
                        ? tr(
                            `确认过的台词共 ${howLong(info.seconds)}`,
                            `${howLong(info.seconds)} of confirmed lines`,
                          )
                        : tr("还没有确认过的台词", "No confirmed lines yet")}
                      {info && info.low_seconds > 0
                        ? tr(
                            `，其中质量低 ${howLong(info.low_seconds)}`,
                            `, ${howLong(info.low_seconds)} of it low quality`,
                          )
                        : ""}
                      {other || current.target
                        ? ""
                        : tr(" · 不是目标角色", " · not a target character")}
                    </div>
                  </div>
                  {!other && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      <Button
                        variant={current.named === false ? "default" : "outline"}
                        size="sm"
                        onClick={onRename}
                      >
                        {current.named === false
                          ? tr("起名字", "Name")
                          : tr("改名或合并", "Rename or merge")}
                      </Button>
                      <Tip
                        text={
                          current.target
                            ? tr(
                                "不再收集这个人：机器不再猜这个角色，已标的留着，以后还能加回来",
                                "Stop collecting this person: the machine stops guessing them, their labels stay, and you can add them back later",
                              )
                            : tr(
                                "重新收集这个人：以前标「不是目标」的台词会列进「可能漏掉的」，要复查",
                                'Collect this person again: lines labeled "Not a target" before will be listed under Maybe missed for you to recheck',
                              )
                        }
                      >
                        <Button variant="outline" size="sm" onClick={onToggleTarget}>
                          {current.target
                            ? tr("不再作为目标", "Stop targeting")
                            : tr("设为目标角色", "Make target")}
                        </Button>
                      </Tip>
                    </div>
                  )}
                </div>
              </div>
              <PartFilter
                items={filterItems}
                ticked={parts}
                onChange={setParts}
                loading={loading}
              />
              {/* What the ticked parts add up to. Always one line of the same height, so the divider under the
                  heading does not move as boxes are ticked. */}
              <div className="mx-1 mt-2 flex h-5 items-center text-xs text-muted-foreground">
                {loading ? (
                  <Spinner className="size-4" />
                ) : shownCount > 0 ? (
                  tr(
                    `勾的部分共 ${shownCount} 句，${howLong(shownSeconds)}`,
                    `Ticked: ${lines(shownCount)}, ${howLong(shownSeconds)}`,
                  )
                ) : clips.length > 0 ? (
                  tr("勾的部分里没有台词", "No lines in the ticked parts")
                ) : (
                  tr("还没有归到这里的台词", "No lines here yet")
                )}
              </div>
              {/* One slim bar: what the list is, the how-to in its hint, and the buttons that work on these lines. The
                buttons go under the text when there is not room for both side by side. */}
              {pending.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border bg-muted/50 py-1.5 pr-1.5 pl-3">
                  <Tip
                    text={tr(
                      <>
                        百分比是机器猜这句是{other ? "「不是目标」" : ` ${role} `}
                        的概率。听到不对的，直接标成对的人或「不是目标」<Kbd>Q</Kbd>
                        ，它就离开这里；听完一键确认其余的。
                      </>,
                      <>
                        The percentage is the machine's chance that the line is {them}. When one is
                        wrong, label it with the right character or "Not a target" <Kbd>Q</Kbd> and
                        it leaves this list; when you're done listening, confirm the rest at once.
                      </>,
                    )}
                  >
                    <span className="min-w-0 flex-[1_1_14rem] text-[13px]">
                      {tr(
                        `要处理的：机器归给了${other ? "「不是目标」" : ` ${role}`}，最不自信的在前`,
                        `To do: the machine gave these to ${them}, least sure first`,
                      )}
                    </span>
                  </Tip>
                  <div className="flex flex-wrap gap-1.5">
                    <Button variant="outline" size="sm" onClick={() => setPlaying(!playing)}>
                      {playing
                        ? tr("停止连播", "Stop playing")
                        : tr("连播待核对", "Play all to check")}{" "}
                      <Kbd>P</Kbd>
                    </Button>
                    <Button size="sm" onClick={onConfirmRest} disabled={!confirmable}>
                      {tr(`确认其余 ${confirmable} 句`, `Confirm the other ${lines(confirmable)}`)}{" "}
                      <Kbd className="ml-1">Shift+Enter</Kbd>
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <div ref={listRef} className="relative" style={{ height: lister.getTotalSize() }}>
              {lister.getVirtualItems().map((v) => {
                const item = items[v.index];
                return (
                  <div
                    key={v.key}
                    data-index={v.index}
                    ref={lister.measureElement}
                    className="absolute top-0 left-0 w-full"
                    style={{ transform: `translateY(${v.start - margin}px)` }}
                  >
                    {item.kind === "row" ? (
                      <Row
                        clip={live[item.clip.id] ?? item.clip}
                        roles={roles}
                        labelText={labelText}
                        selected={item.clip.id === focus}
                        flash={flashes.has(item.clip.id)}
                        onSelect={() => setFocus(item.clip.id)}
                        showEpisode
                        follow={false}
                        maybeOf={item.maybeOf}
                        showTarget={item.showTarget}
                      />
                    ) : item.kind === "maybe" ? (
                      <Tip
                        text={tr(
                          `百分比是机器猜这句是 ${role} 的概率。刚设成目标角色时，以前标成「不是目标」的台词也会列在这里。`,
                          `The percentage is the machine's chance that the line is ${role}. Right after you make someone a target, lines labeled "Not a target" before are listed here too.`,
                        )}
                      >
                        <div className={SECTION_TITLE}>
                          {tr(
                            `可能漏掉的：机器没归给 ${role}，但有可能是，最可能的在前`,
                            `Maybe missed: the machine didn't give these to ${role} but they might be them, most likely first`,
                          )}
                        </div>
                      </Tip>
                    ) : item.kind === "aside" ? (
                      <div className={SECTION_TITLE}>
                        {tr(
                          "可能质量低：机器归进来了，但不会被一键确认，最不像质量低的在前",
                          "Maybe low quality: given by the machine but never confirmed at once, least likely low first",
                        )}
                      </div>
                    ) : item.kind === "skipped" ? (
                      <div className={SECTION_TITLE}>
                        {tr(
                          `忽略的：机器归给了${other ? "「不是目标」" : ` ${role} `}，`,
                          `Ignored: the machine gave these to ${them}, `,
                        )}
                        {other ? mostLikeTarget() : inTimeOrder()}
                      </div>
                    ) : (
                      <div className={SECTION_TITLE}>
                        {tr("确认过的，", "Confirmed, ")}
                        {other ? mostLikeTarget() : inTimeOrder()}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
