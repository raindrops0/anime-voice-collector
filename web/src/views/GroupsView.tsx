import { cn } from "cn";
import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import type { Clip, Group, Roles } from "../api";
import type { LabelText } from "../clips";
import { EpisodeProgress, type Progress } from "../components/EpisodeProgress";
import { Empty } from "../components/Notes";
import { Closest, Tag } from "../components/Pills";
import { SELECTED_ROW } from "../components/Row";
import { withKeys } from "../components/Keys";
import { Tip } from "../components/Tip";
import type { View } from "../components/TopBar";
import { stamp } from "../format";
import { lines, many, tr } from "../language";

/* A group as the page keeps it: the server's group, with its place in the list as a key. */
export interface KeyedGroup extends Group {
  key: number;
}

/* The ticked lines in each group, by the group's key. */
export type Picked = Record<number, Set<string> | undefined>;

interface GroupsViewProps {
  groups: KeyedGroup[];
  loading: boolean;
  roles: Roles;
  labelText: LabelText;
  focus: string | null;
  setFocus: (id: string) => void;
  picked: Picked;
  setPicked: (next: Picked | ((p: Picked) => Picked)) => void;
  episode: string | null;
  progress: Progress;
  /* Lines still to do in this episode, as counted on the Scenes tab. */
  work: number;
  onGo: (view: View) => void;
}

/* Cards are at least this wide; the columns share the rest. */
const CARD_WIDTH = 340;
/* Space between cards, across and down. */
const GAP = 14;

const GUESSED_MOST = () =>
  tr("机器在这组里最常猜的角色", "The character the machine guesses most often in this group");

/* ───────────── Groups view: name a group of similar voices ───────────── */

/* `picked`: the ticked lines in each group. The keys and the bottom bar label these, see App. */
export function GroupsView({
  groups,
  loading,
  roles,
  labelText,
  focus,
  setFocus,
  picked,
  setPicked,
  episode,
  progress,
  work,
  onGo,
}: GroupsViewProps) {
  /* The last line ticked in each group, so Shift+click can tick the lines between. */
  const [anchor, setAnchor] = useState<Record<number, string>>({});
  /* Groups stay put while labeling, so a group whose lines are all labeled no longer counts as left. */
  const left = groups.filter((g) => g.clips.some((c) => !c.label)).length;

  /* The cards' functions stay the same from render to render and call the newest ones App gave. */
  const latest = useRef({ setFocus, setPicked });
  useLayoutEffect(() => {
    latest.current = { setFocus, setPicked };
  });
  const act = useMemo<CardActions>(
    () => ({
      focus: (id) => latest.current.setFocus(id),
      pick: (next) => latest.current.setPicked(next),
      anchor: (key, id) => setAnchor((a) => ({ ...a, [key]: id })),
    }),
    [],
  );

  /* Cards sit in columns at least CARD_WIDTH wide, each as tall as its lines need. Each group in turn goes into the
     column that is shortest so far, so every card starts no higher than the one before it, and the last group is
     the lowest card on the page. Group numbers mean little to the person, so they need not go straight across.
     An episode has dozens of groups and each card holds many tick boxes and choices; drawing them all made every
     key press take about 0.2 seconds. So only the cards near the screen are drawn. */
  const [list, setList] = useState<HTMLDivElement | null>(null);
  const [page, setPage] = useState<HTMLElement | null>(null);
  /* Where the list starts in the page's scrolled content. */
  const [margin, setMargin] = useState(0);
  const [width, setWidth] = useState(0);
  const [screen, setScreen] = useState({ top: 0, height: 0 });
  const summaryRef = useRef<HTMLDivElement>(null);
  // oxlint-disable-next-line react-hooks/exhaustive-deps -- measured after every render; sets state only when it moved
  useLayoutEffect(() => {
    const main = list?.closest("main") ?? null;
    if (main !== page) setPage(main);
    if (list && main) {
      const top =
        list.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop;
      if (Math.abs(top - margin) > 0.5) setMargin(top);
    }
  });
  useEffect(() => {
    if (!list) return;
    const watch = new ResizeObserver(() => setWidth(list.clientWidth));
    watch.observe(list);
    return () => watch.disconnect();
  }, [list]);
  useEffect(() => {
    if (!page) return;
    const read = () => setScreen({ top: page.scrollTop, height: page.clientHeight });
    read();
    page.addEventListener("scroll", read, { passive: true });
    const watch = new ResizeObserver(read);
    watch.observe(page);
    return () => {
      page.removeEventListener("scroll", read);
      watch.disconnect();
    };
  }, [page]);
  const lanes = Math.max(1, Math.floor((width + GAP) / (CARD_WIDTH + GAP)));
  const column = width ? (width - GAP * (lanes - 1)) / lanes : 0;

  /* The cards' measured heights, by group key. A card that gets shorter (all its lines labeled, so its choices go)
     keeps its old height here, so the cards below it don't jump to another column while the person works. The
     heights belong to one set of groups at one column width, and start again when either changes: a wider page
     makes the cards shorter, and kept heights would leave gaps between them. */
  const shape = `${Math.round(column)}|${groups.map((g) => g.clips[0]?.id).join()}`;
  const [measured, setMeasured] = useState<{ shape: string; sizes: Record<number, number> }>({
    shape: "",
    sizes: {},
  });
  const sizes = useMemo(() => (measured.shape === shape ? measured.sizes : {}), [measured, shape]);
  const shapeNow = useRef(shape);
  shapeNow.current = shape;
  const [watchCards] = useState(
    () =>
      new ResizeObserver((entries) =>
        setMeasured((m) => {
          const now = shapeNow.current;
          const next = m.shape === now ? { ...m.sizes } : {};
          let moved = m.shape !== now;
          for (const e of entries) {
            const key = Number((e.target as HTMLElement).dataset.key);
            const h = e.borderBoxSize[0]?.blockSize ?? (e.target as HTMLElement).offsetHeight;
            if (h > (next[key] ?? 0) + 0.5) {
              next[key] = h;
              moved = true;
            }
          }
          return moved ? { shape: now, sizes: next } : m;
        }),
      ),
  );
  useEffect(() => () => watchCards.disconnect(), [watchCards]);
  const measure = useCallback(
    (node: HTMLDivElement | null) => {
      if (!node) return;
      watchCards.observe(node);
      return () => watchCards.unobserve(node);
    },
    [watchCards],
  );
  const { spots, height } = useMemo(() => {
    const bottoms: number[] = Array.from({ length: lanes }, () => 0);
    const spots = groups.map((g) => {
      const lane = bottoms.indexOf(Math.min(...bottoms));
      const top = bottoms[lane];
      const size = sizes[g.key] ?? guess(g);
      bottoms[lane] = top + size + GAP;
      return { lane, top, size };
    });
    return { spots, height: Math.max(0, ...bottoms) };
  }, [groups, lanes, sizes]);

  const focusAt = groups.findIndex((g) => g.clips.some((c) => c.id === focus));
  /* The group of the selected line comes into view, as J and K move through the lines. Only when the selection
     moves to another group: heights measured later must not pull the page back. */
  const spotsNow = useRef(spots);
  spotsNow.current = spots;
  useEffect(() => {
    const spot = spotsNow.current[focusAt];
    if (!page || !spot) return;
    const covered = summaryRef.current?.offsetHeight ?? 0;
    const top = margin + spot.top - covered;
    const bottom = margin + spot.top + spot.size;
    if (top < page.scrollTop) page.scrollTop = top;
    else if (bottom > page.scrollTop + page.clientHeight)
      page.scrollTop = Math.min(top, bottom - page.clientHeight);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when the selection moves to another group
  }, [focusAt, page]);
  /* Cards within this distance of the screen are drawn too, so scrolling shows no empty space. */
  const near = 600;
  const from = screen.top - margin - near;
  const to = screen.top - margin + screen.height + near;

  if (loading)
    return (
      <Empty>
        <Spinner className="mx-auto size-6" />
        <p>{tr("正在把声音相近的台词分组…", "Grouping lines with similar voices…")}</p>
      </Empty>
    );
  return (
    <div>
      {/* The episode's summary, kept on screen while scrolling like the one in Scenes. -top-2 cancels the top
          padding of the list, so cards don't show through above it. */}
      <div
        ref={summaryRef}
        className="sticky -top-2 z-[3] flex flex-wrap items-center gap-2.5 border-b bg-background px-1 pt-3 pb-2"
      >
        <h2 className="text-base font-semibold">{episode}</h2>
        <EpisodeProgress progress={progress} />
        <Tip
          text={tr(
            "只给要处理的台词分组，跟「场景」里「只看要处理的」是同一批。机器很自信的在「角色」里核对",
            'Only lines still to do are grouped, the same lines as "Only to do" in Scenes. Lines the machine is confident about are checked in Characters',
          )}
        >
          <span className="text-xs text-muted-foreground">
            {tr(`还剩 ${left} 组`, `${many(left, "group")} left`)}
          </span>
        </Tip>
        {/* The tab is only called "Groups", so the view says who made them. */}
        {groups.length > 0 && (
          <p className="m-0 basis-full text-xs text-muted-foreground">
            {tr(
              "机器按声音自动分的组：每组的台词听起来像同一个人，但可能混进别人。",
              "The machine made these groups by itself, by voice: each sounds like one person, but may mix in others.",
            )}
          </p>
        )}
      </div>
      {/* Says why there is nothing to do here, then where the work goes on. Wider than usual, so each step fits on one line when there is room. */}
      {groups.length === 0 && (
        <Empty
          title={tr("「分组」里没有要做的了", "No more work to do in Groups")}
          className="max-w-4xl"
        >
          <p>
            {progress.auto > 0
              ? tr(
                  "你标的已经够机器学了，它替你做了大部分判断。下一步：",
                  "You have labeled enough for the machine to learn from, and it has made most of the calls. Next:",
                )
              : tr("下一步：", "Next:")}
          </p>
          <ol className="mx-auto mt-1.5 w-fit list-decimal pl-[18px] text-left">
            {work > 0 && (
              <li>
                {withKeys(
                  tr(
                    `去「场景」，按 [F] 只看要处理的，确认剩下的 ${work} 句`,
                    `In Scenes, press [F] for Only to do and confirm the ${lines(work)} left`,
                  ),
                )}
                {/* Why these lines are not here as a group. */}
                <div className="text-xs">
                  {work === 1
                    ? tr(
                        "一句成不了组：分组要至少两句听起来像同一个人",
                        "One line can't make a group: a group needs at least two lines that sound like the same person",
                      )
                    : tr(
                        "它们分不成组：彼此听起来不像",
                        "They can't be grouped: they don't sound alike",
                      )}
                </div>
              </li>
            )}
            {progress.auto > 0 && (
              <li>
                {withKeys(
                  tr(
                    "去「角色」，逐个角色核对机器的判断：改掉错的，其余按 [Shift]+[Enter] 一起确认",
                    "In Characters, check what the machine gave each character: fix the wrong ones, then confirm the rest with [Shift]+[Enter]",
                  ),
                )}
              </li>
            )}
            <li>{tr("够用了就去「导出」", "When you have enough, go to Export")}</li>
          </ol>
          {/* A button for the first step, so the person need not find the tab. */}
          <Button
            className="mt-4"
            onClick={() => onGo(work > 0 ? "scene" : progress.auto > 0 ? "roles" : "export")}
          >
            {work > 0
              ? tr("去「场景」", "Go to Scenes")
              : progress.auto > 0
                ? tr("去「角色」", "Go to Characters")
                : tr("去「导出」", "Go to Export")}
            <Kbd className="ml-1">{work > 0 ? "S" : progress.auto > 0 ? "O" : "E"}</Kbd>
          </Button>
        </Empty>
      )}
      <div ref={setList} className="relative mt-3" style={{ height }}>
        {column > 0 &&
          groups.map((g, i) => {
            const spot = spots[i];
            const shown = i === focusAt || (spot.top + spot.size > from && spot.top < to);
            return (
              shown && (
                <div
                  key={g.key}
                  ref={measure}
                  data-key={g.key}
                  data-tour={i === 0 ? "group" : undefined}
                  className="absolute top-0"
                  style={{
                    width: column,
                    left: spot.lane * (column + GAP),
                    transform: `translateY(${spot.top}px)`,
                  }}
                >
                  <GroupCard
                    g={g}
                    number={i + 1}
                    roles={roles}
                    labelText={labelText}
                    focus={g.clips.some((c) => c.id === focus) ? focus : null}
                    ticked={picked[g.key]}
                    anchor={anchor[g.key]}
                    act={act}
                  />
                </div>
              )
            );
          })}
      </div>
    </div>
  );
}

/* About how tall a card is, before it is measured. */
const guess = (g: Group) => 100 + 26 * Math.min(g.clips.length, 8);

/* What a group card does, the same functions on every render, so a card that did not change is not drawn
   again. */
interface CardActions {
  focus: (id: string) => void;
  pick: (next: Picked | ((p: Picked) => Picked)) => void;
  anchor: (key: number, id: string) => void;
}

interface GroupCardProps {
  g: KeyedGroup;
  number: number;
  roles: Roles;
  labelText: LabelText;
  /* The selected line, only when it is in this group; otherwise null, so other cards stay as they are. */
  focus: string | null;
  ticked: Set<string> | undefined;
  /* The last line ticked here, so Shift+click can tick the lines between. */
  anchor: string | undefined;
  act: CardActions;
}

/* One group: its lines with tick boxes. */
const GroupCard = memo(function GroupCard({
  g,
  number,
  roles,
  labelText,
  focus,
  ticked: given,
  anchor,
  act,
}: GroupCardProps) {
  const ticked = given || new Set<string>();
  /* Labeled lines stay in the group for you to see, but can't be ticked. */
  const open = g.clips.filter((c) => !c.label);
  const keep = open.filter((c) => ticked.has(c.id));
  const all = open.length > 0 && keep.length === open.length;
  const done = open.length === 0;
  /* Built on the newest ticks, so two clicks before the page draws again both count. */
  const tick = (c: Clip, e: MouseEvent) => {
    e.stopPropagation();
    const shift = e.shiftKey;
    act.pick((p) => {
      const next = new Set(p[g.key] || []);
      const on = !next.has(c.id);
      const from = open.findIndex((o) => o.id === anchor);
      const to = open.findIndex((o) => o.id === c.id);
      const span =
        shift && from >= 0 ? open.slice(Math.min(from, to), Math.max(from, to) + 1) : [c];
      span.forEach((o) => (on ? next.add(o.id) : next.delete(o.id)));
      return { ...p, [g.key]: next };
    });
    act.anchor(g.key, c.id);
  };
  const tickAll = () =>
    act.pick((p) => ({ ...p, [g.key]: new Set(all ? [] : open.map((c) => c.id)) }));
  const setFocus = act.focus;
  const gi = number - 1;
  /* The list scrolls by itself when the group is long; keep the selected line in sight in it, as J and K move.
     Only the list scrolls here: the page is brought to the group by GroupsView. */
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = listRef.current;
    const row = focus ? list?.querySelector<HTMLElement>(`[data-id="${CSS.escape(focus)}"]`) : null;
    if (!list || !row) return;
    const top = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (top + row.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = top + row.offsetHeight - list.clientHeight;
  }, [focus]);
  return (
    <Card className={cn("gap-2.5 p-3.5", done && "opacity-60")}>
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        {tr(`第 ${gi + 1} 组 · 像同一个人`, `Group ${gi + 1} · sounds like one person`)}
        <span className="text-xs font-normal text-muted-foreground">
          {lines(g.size)} · {tr(`${g.seconds} 秒`, `${g.seconds} s`)}
          {done ? tr(" · 都标好了", " · all labeled") : ""}
        </span>
        {g.hint && <Closest roles={roles} name={g.hint.name} title={GUESSED_MOST()} />}
      </h3>
      {/* Columns: tick box (blank once labeled), text, label, time. */}
      <div ref={listRef} className="flex max-h-[210px] flex-col gap-0.5 overflow-y-auto">
        {g.clips.map((c) => (
          <div
            key={c.id}
            data-id={c.id}
            className={cn(
              "grid grid-cols-[28px_1fr_auto_auto] items-center gap-2 rounded-md border border-transparent px-1.5 py-[3px] text-[13px] hover:bg-muted/60",
              c.id === focus && SELECTED_ROW,
            )}
            onClick={() => setFocus(c.id)}
          >
            {c.label ? (
              <span></span>
            ) : (
              /* The tick box only selects; the rest of the row plays the line. The whole left end
                         of the row, top to bottom, counts as the box, so it is easy to hit; only this part
                         shows the hand and its own hover color, so it is clear where it ends. It clips the
                         box's own larger click area, which reached past the row and gave short groups a
                         scroll bar. */
              <span
                className="-my-[3px] -ml-1.5 flex cursor-pointer items-center justify-center self-stretch overflow-hidden rounded-l-md pl-1.5 hover:bg-muted"
                onClick={(e) => tick(c, e)}
                onMouseDown={(e) => e.preventDefault()}
              >
                <Checkbox
                  aria-label={c.text}
                  checked={ticked.has(c.id)}
                  className="pointer-events-none"
                />
              </span>
            )}
            <span
              className={cn(
                ticked.has(c.id) && !c.label && "font-semibold",
                c.label && "text-muted-foreground",
              )}
            >
              {c.text || tr("（没有字幕文字）", "(no subtitle text)")}
              {/* The secondary subtitle line, small under it. */}
              {c.display && c.display !== c.text && (
                <span className="block text-xs font-normal text-muted-foreground">{c.display}</span>
              )}
            </span>
            {c.label ? (
              <Tag
                look="done"
                tip={withKeys(
                  tr(
                    "已经标了；按 [Z] 撤销，或在左边改",
                    "Already labeled. Press [Z] to undo, or change it on the left",
                  ),
                )}
              >
                {labelText[c.label] || c.label}
                {c.unusable ? tr("·质量低", " · low quality") : ""}
              </Tag>
            ) : (
              <span></span>
            )}
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {c.episode} {stamp(c.start)}
            </span>
          </div>
        ))}
      </div>
      {/* Labels are picked in the bottom bar or with its keys, which label the ticked lines. This row stays when
          the group is done, so the card keeps its height and leaves no gap above the cards below. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant="outline" size="sm" onClick={tickAll} disabled={done}>
          {all ? tr("全不选", "Select none") : tr("全选", "Select all")}
        </Button>
        <span className="text-xs text-muted-foreground">
          {done
            ? tr("这组都标好了", "This group is all labeled")
            : keep.length
              ? withKeys(
                  tr(
                    `勾了 ${keep.length} 句；在底栏选是谁，或按 [1]–[9]、[Q]、[N]`,
                    `${lines(keep.length)} ticked; pick who in the bottom bar, or press [1]–[9], [Q] or [N]`,
                  ),
                )
              : tr(
                  "先勾上同一个人的台词，再在底栏选是谁",
                  "Tick the lines of one person first, then pick who in the bottom bar",
                )}
        </span>
      </div>
    </Card>
  );
});
