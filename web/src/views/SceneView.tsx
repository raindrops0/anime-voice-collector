import {
  type CSSProperties,
  memo,
  type ReactNode,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import type { Clip, Roles } from "../api";
import {
  DONE_PARTS,
  ignoredTip,
  type LabelText,
  lowTip,
  maybeLowTip,
  optionalTip,
  type Part,
  partOf,
  SKIP_PARTS,
  skippedTip,
  statusText,
  WORK_PARTS,
} from "../clips";
import { EpisodeProgress, type Progress } from "../components/EpisodeProgress";
import { Empty } from "../components/Notes";
import { PartFilter, type PartItem } from "../components/PartFilter";
import type { PillLook } from "../looks";
import { Row } from "../components/Row";
import { howLong, stamp } from "../format";
import { lines, tr } from "../language";

interface SceneViewProps {
  clips: Clip[];
  order: string[];
  focus: string | null;
  setFocus: (id: string) => void;
  roles: Roles;
  labelText: LabelText;
  parts: Set<Part>;
  setParts: (parts: Set<Part>) => void;
  onlyWork: boolean;
  toggleOnlyWork: () => void;
  /* The episode's lines have not come yet. */
  loading: boolean;
  flashes: Set<string>;
  episode: string | null;
  progress: Progress;
}

const SceneRow = memo(function SceneRow({
  clip,
  select,
  ...rest
}: {
  clip: Clip;
  roles: Roles;
  labelText: LabelText;
  selected: boolean;
  flash: boolean;
  select: (id: string) => void;
}) {
  return <Row clip={clip} onSelect={() => select(clip.id)} {...rest} />;
});

/* ───────────── Scenes view ───────────── */

export function SceneView({
  clips,
  order,
  focus,
  setFocus,
  roles,
  labelText,
  parts,
  setParts,
  onlyWork,
  toggleOnlyWork,
  loading,
  flashes,
  episode,
  progress,
}: SceneViewProps) {
  /* The lines of the ticked parts, in scenes, in episode order. */
  const shown = new Set(order);
  const scenes: { scene: number; clips: Clip[] }[] = [];
  for (const clip of clips) {
    if (!shown.has(clip.id)) continue;
    const last = scenes[scenes.length - 1];
    if (!last || last.scene !== clip.scene) scenes.push({ scene: clip.scene, clips: [clip] });
    else last.clips.push(clip);
  }
  const shownClips = scenes.flatMap((s) => s.clips);
  const shownCount = shownClips.length;
  const shownSeconds = shownClips.reduce((s, c) => s + c.duration, 0);
  const count: Record<Part, number> = {
    review: 0,
    unlabeled: 0,
    auto: 0,
    clean: 0,
    low: 0,
    aside: 0,
    rule: 0,
    ignored: 0,
  };
  for (const clip of clips) count[partOf(clip)]++;
  /* A box looks like the status pill on its lines only when all its lines carry that one pill. Too short also holds
     labeled short lines, so it stays plain, and so do the boxes of whole groups. "Maybe someone new" on some lines
     not confident is the same orange. */
  const looks: Partial<Record<Part, PillLook>> = {
    review: "review",
    unlabeled: "unlabeled",
    auto: "auto",
    clean: "confirmed",
    low: "unusable",
    aside: "likely_low",
    ignored: "ignored",
  };
  const one = (part: Part, label: ReactNode, tip?: ReactNode): PartItem<Part> => ({
    keys: [part],
    label,
    count: count[part],
    tip,
    look: looks[part],
  });
  /* Confirmed first, then To do, then the rest. */
  const items: PartItem<Part>[] = [
    {
      keys: DONE_PARTS,
      label: tr("确认过的", "Confirmed"),
      count: DONE_PARTS.reduce((n, p) => n + count[p], 0),
      children: [
        one("clean", tr("干净", "Clean")),
        one("low", tr("质量低", "Low quality"), lowTip()),
      ],
    },
    {
      keys: WORK_PARTS,
      label: tr("要处理的", "To do"),
      count: WORK_PARTS.reduce((n, p) => n + count[p], 0),
      todo: true,
      tip: tr("要你逐句选人的台词", "Lines that need you to pick the character, one by one"),
      children: [one("unlabeled", statusText("unlabeled")), one("review", statusText("review"))],
      /* On the same line, past a divider: not work to do here, so To do does not tick it. */
      after: [
        one(
          "auto",
          tr("有把握", "Confident"),
          tr(
            "不用逐句听；去「角色」视图按人核对",
            "No need to listen one by one; check them per character in the Characters view",
          ),
        ),
      ],
    },
    {
      keys: ["aside"],
      label: tr("可选", "Optional"),
      count: count.aside,
      tip: optionalTip(),
      children: [one("aside", tr("可能质量低", "Maybe low quality"), maybeLowTip())],
    },
    {
      keys: SKIP_PARTS,
      label: tr("忽略的", "Ignored"),
      count: SKIP_PARTS.reduce((n, p) => n + count[p], 0),
      tip: tr(
        "不算要处理的，也不会被当成机器有把握的导出",
        "Not work to do, and not exported as confident guesses",
      ),
      children: [
        one("rule", tr("太短", "Too short"), skippedTip()),
        one("ignored", tr("你忽略的", "Ignored by you"), ignoredTip()),
      ],
    },
  ];
  /* The summary stays at the top while scrolling, so each scene header sticks just below it, and a selected
     line scrolls into view below both. Its height changes when it wraps, so it is measured. */
  const head = useRef<HTMLDivElement>(null);
  const [headHeight, setHeadHeight] = useState(0);
  useLayoutEffect(() => {
    const box = head.current;
    if (!box) return;
    const watch = new ResizeObserver(() => setHeadHeight(box.offsetHeight));
    watch.observe(box);
    return () => watch.disconnect();
  }, []);
  /* The same function on every draw, so a line is drawn again only when it changes itself: moving to the next line
     changes two lines, not the whole episode. */
  const latest = useRef(setFocus);
  latest.current = setFocus;
  const select = useCallback((id: string) => latest.current(id), []);
  return (
    <div
      style={{ "--head": `${headHeight}px` } as CSSProperties}
      className="[&_section>*]:scroll-mt-(--head)"
    >
      {/* -top-2 cancels the top padding of the list, so lines don't show through above it, and -mt-2 starts it
          there too: starting below it, it moved up those 8 pixels before it stayed. */}
      <div ref={head} className="sticky -top-2 z-[3] -mt-2 border-b bg-background px-1 pt-5 pb-2">
        {/* The button stays at the top right; only the text beside it wraps. */}
        <div className="flex items-start gap-2.5">
          <div className="flex min-h-7 min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1">
            <h2 className="text-base font-semibold">{episode}</h2>
            <EpisodeProgress progress={progress} />
          </div>
          <Button
            variant={onlyWork ? "secondary" : "outline"}
            size="sm"
            className="shrink-0"
            onClick={toggleOnlyWork}
          >
            {onlyWork ? tr("回到刚才勾的", "Back to my ticks") : tr("只看要处理的", "Only to do")}{" "}
            <Kbd>F</Kbd>
          </Button>
        </div>
        <div className="mt-1.5">
          <PartFilter
            items={items}
            ticked={parts}
            onChange={setParts}
            loading={loading}
            /* What the ticked parts add up to, as in Characters; how many lines each part holds is on its box. */
            end={
              !loading &&
              shownCount > 0 &&
              tr(
                `勾的部分共 ${shownCount} 句，${howLong(shownSeconds)}`,
                `Ticked: ${lines(shownCount)}, ${howLong(shownSeconds)}`,
              )
            }
          />
        </div>
      </div>
      {scenes.length === 0 &&
        (loading ? (
          <Empty>
            <Spinner className="mx-auto size-6" />
          </Empty>
        ) : parts.size === 0 ? (
          <Empty title={tr("什么都没勾", "Nothing ticked")}>
            <p>{tr("在上面勾上要看的部分。", "Tick the parts you want to see above.")}</p>
          </Empty>
        ) : onlyWork ? (
          <Empty title={tr("这一集都处理完了", "This episode is done")}>
            <p>
              {tr(
                "在上面多勾几项可以回头翻看，或者去「角色」视图按人核对机器的判断。",
                "Tick more parts above to look back, or check the machine's calls per character in the Characters view.",
              )}
            </p>
          </Empty>
        ) : (
          <Empty title={tr("勾的部分里没有台词", "No lines in the ticked parts")}>
            <p>{tr("在上面多勾几项。", "Tick more parts above.")}</p>
          </Empty>
        ))}
      {scenes.map((s) => (
        <section key={`${s.scene}-${s.clips[0].id}`}>
          {/* Sticks right under the summary, which sits 0.5rem above the top of the list. */}
          <div className="sticky top-[calc(var(--head)-0.5rem)] z-[2] flex items-center gap-2 bg-background px-1 pt-3.5 pb-1.5 text-xs text-muted-foreground">
            <b className="font-semibold text-foreground/80">
              {tr(`第 ${s.scene + 1} 场`, `Scene ${s.scene + 1}`)}
            </b>
            <span>{stamp(s.clips[0].start)}</span>
            <span>· {lines(s.clips.length)}</span>
          </div>
          {s.clips.map((clip) => (
            <SceneRow
              key={clip.id}
              clip={clip}
              roles={roles}
              labelText={labelText}
              selected={clip.id === focus}
              flash={flashes.has(clip.id)}
              select={select}
            />
          ))}
        </section>
      ))}
    </div>
  );
}
