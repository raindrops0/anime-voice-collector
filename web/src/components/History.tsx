import { useEffect, useState } from "react";
import { HistoryIcon } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { call, type HistoryEntry, type HistoryPage, type Roles } from "../api";
import { IGNORED, OTHER, type LabelText } from "../clips";
import { lines, tr } from "../language";
import { Avatar } from "./Avatar";
import { Tip } from "./Tip";

/* How many steps the list shows at first, and how many more each "Show older" adds. */
const PAGE = 50;

interface HistoryProps {
  roles: Roles;
  labelText: LabelText;
  /* Changes after every saved change, so an open list fetches itself again. */
  version: unknown;
  /* Take back these steps, as one new step. `what` is the message shown after. */
  onRevert: (batches: number[], what: string) => Promise<unknown>;
}

/* The history next to Undo: the newest steps first. Any step still in effect can be taken back alone, several can
   be ticked and taken back together, and "Back to here" takes back every step after one. Taking back is a step of
   its own, so the list only grows, and a take-back can itself be taken back. */
export function History({ roles, labelText, version, onRevert }: HistoryProps) {
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [page, setPage] = useState<HistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [working, setWorking] = useState(false);
  /* Steps from today show only the time. Read when the list arrives, not while drawing. */
  const [today, setToday] = useState("");

  useEffect(() => {
    if (!open) return;
    let live = true;
    call<HistoryPage>(`/api/history?limit=${limit}`)
      .then((p) => {
        if (!live) return;
        setPage(p);
        setToday(new Date().toDateString());
        setError(null);
        /* A ticked step taken back meanwhile can't be taken back again. */
        const can = new Set(p.entries.filter((e) => !e.why_not).map((e) => e.batch));
        setTicked((t) => new Set([...t].filter((b) => can.has(b))));
      })
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [open, limit, version]);

  const entries = page?.entries ?? [];
  const run = async (batches: number[], what: string) => {
    setWorking(true);
    try {
      await onRevert(batches, what);
      setTicked(new Set());
    } finally {
      setWorking(false);
    }
  };
  const tick = (batch: number, on: boolean) =>
    setTicked((t) => {
      const next = new Set(t);
      if (on) next.add(batch);
      else next.delete(batch);
      return next;
    });
  /* Every step after this one that can still be taken back. The list is newest first, so they are all loaded. */
  const after = (batch: number) =>
    entries.filter((e) => e.batch > batch && !e.why_not).map((e) => e.batch);

  const nameOf = (name: string | null) =>
    name === null ? tr("清掉标签", "label cleared") : (labelText[name] ?? name);
  const avatarOf = (name: string | null) =>
    name === OTHER ? (
      <Avatar blank size="xs" />
    ) : name === IGNORED ? (
      <Avatar blank ignored size="xs" />
    ) : name ? (
      <Avatar role={roles[name]} name={name} size="xs" />
    ) : null;

  /* What a step did, in a few words: whom its lines went to, a rename or merge, or which steps it took back. */
  const describe = (e: HistoryEntry) => {
    if (e.undo_of.length) {
      const shown = e.undo_of.slice(0, 4).map((b) => `#${b}`);
      const list =
        e.undo_of.length > 4
          ? tr(
              `${shown.join("、")} 等 ${e.undo_of.length} 步`,
              `${shown.join(", ")} and ${e.undo_of.length - 4} more`,
            )
          : tr(shown.join("、"), shown.join(", "));
      return e.source === "undo"
        ? tr(`撤销 ${list}（Z）`, `Undo ${list} (Z)`)
        : tr(`撤销 ${list}`, `Took back ${list}`);
    }
    if (e.renamed)
      return tr(
        `改名：${e.renamed.from} → ${e.renamed.to}`,
        `Renamed ${e.renamed.from} → ${e.renamed.to}`,
      );
    if (e.merged)
      return tr(
        `合并：${e.merged.from} 并入 ${e.merged.into}`,
        `Merged ${e.merged.from} into ${e.merged.into}`,
      );
    const parts = e.to.slice(0, 3).map((t) => (
      <span key={t.name ?? ""} className="inline-flex items-center gap-1">
        {avatarOf(t.name)}
        {nameOf(t.name)}
        {e.to.length > 1 && <span className="text-muted-foreground">{t.count}</span>}
      </span>
    ));
    const low = e.low
      ? tr(`${e.low} 句标为质量低`, `${lines(e.low)} marked low quality`)
      : e.not_low
        ? tr(`${e.not_low} 句取消质量低`, `low quality removed from ${lines(e.not_low)}`)
        : null;
    const rejects = e.rejects ? tr(`${e.rejects} 处「不是此人」`, `${e.rejects} "not them"`) : null;
    return (
      <span className="inline-flex flex-wrap items-center gap-x-2">
        {parts}
        {!parts.length && !low && !rejects && tr("没有改动", "No change")}
        {[low, rejects].filter(Boolean).map((s) => (
          <span key={s} className="text-muted-foreground">
            {s}
          </span>
        ))}
        {e.created.length > 0 && (
          <span className="text-muted-foreground">
            {tr(`新角色 ${e.created.join("、")}`, `new: ${e.created.join(", ")}`)}
          </span>
        )}
      </span>
    );
  };

  const when = (time: string) => {
    const d = new Date(time);
    if (Number.isNaN(d.getTime())) return time;
    const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toDateString() === today
      ? hm
      : `${d.toLocaleDateString([], { month: "2-digit", day: "2-digit" })} ${hm}`;
  };

  const tickedList = [...ticked].sort((a, b) => b - a);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tip
        text={tr(
          "操作历史：撤销较早的某一步，或回到某一步",
          "History: take back an earlier step, or go back to one",
        )}
      >
        <PopoverTrigger
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={tr("操作历史", "History")}
              className="flex-none"
            />
          }
        >
          <HistoryIcon />
        </PopoverTrigger>
      </Tip>
      <PopoverContent
        side="top"
        align="end"
        className="flex w-[30rem] max-w-[calc(100vw-2rem)] flex-col"
      >
        <div className="border-b px-3.5 py-2.5">
          <PopoverTitle>{tr("操作历史", "History")}</PopoverTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {tr(
              "最新的在上面。撤销也算一步，可以再撤销。之后又改过的台词保持后来的样子。",
              "Newest first. Taking back is a step too, and can be taken back. Lines changed again later keep the later change.",
            )}
          </p>
        </div>
        <div
          className="min-h-0 flex-1 overflow-y-auto py-1"
          style={{ maxHeight: "min(60vh, 34rem)" }}
        >
          {error && <p className="px-3.5 py-2 text-sm text-destructive">{error}</p>}
          {page && !entries.length && (
            <p className="px-3.5 py-2 text-sm text-muted-foreground">
              {tr("还没有操作", "Nothing done yet")}
            </p>
          )}
          {entries.map((e) => {
            const gone = e.undone_by !== null;
            const back = after(e.batch);
            return (
              <div
                key={e.batch}
                className="group flex items-start gap-2.5 px-3.5 py-1.5 hover:bg-muted/60"
              >
                <Tip text={e.why_not}>
                  <span className="mt-0.5 flex">
                    <Checkbox
                      aria-label={tr(`选中第 ${e.batch} 步`, `Tick step ${e.batch}`)}
                      checked={ticked.has(e.batch)}
                      disabled={!!e.why_not || working}
                      onCheckedChange={(on) => tick(e.batch, on)}
                    />
                  </span>
                </Tip>
                <div
                  className={cn(
                    "min-w-0 flex-1 text-sm",
                    gone && "text-muted-foreground line-through",
                  )}
                >
                  <div className="flex items-baseline gap-2">
                    <span className="flex-none text-xs text-muted-foreground tabular-nums">
                      #{e.batch}
                    </span>
                    <span className="min-w-0">{describe(e)}</span>
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[
                      gone && tr(`已被 #${e.undone_by} 撤销`, `taken back by #${e.undone_by}`),
                      e.text && `「${e.text}」`,
                      e.lines > 1 && tr(`共 ${e.lines} 句`, `${lines(e.lines)} in all`),
                      e.episode,
                      when(e.time),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                {/* Shown on hover or focus, so the list stays quiet to read. */}
                <div className="flex flex-none gap-1 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
                  {back.length > 0 && (
                    <Tip
                      text={tr(
                        `撤销这一步之后的 ${back.length} 步`,
                        `Take back the ${back.length} steps after this one`,
                      )}
                    >
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={working}
                        onClick={() =>
                          run(back, tr(`已回到第 ${e.batch} 步`, `Back to step ${e.batch}`))
                        }
                      >
                        {tr("回到这里", "Back to here")}
                      </Button>
                    </Tip>
                  )}
                  {!e.why_not && (
                    <Button
                      variant="outline"
                      size="xs"
                      disabled={working}
                      onClick={() =>
                        run([e.batch], tr(`已撤销第 ${e.batch} 步`, `Took back step ${e.batch}`))
                      }
                    >
                      {tr("撤销", "Take back")}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
          {page?.more && (
            <div className="px-3.5 py-1.5">
              <Button variant="ghost" size="sm" onClick={() => setLimit((l) => l + PAGE)}>
                {tr("显示更早的", "Show older")}
              </Button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 border-t px-3.5 py-2">
          <span className="text-xs text-muted-foreground">
            {ticked.size
              ? tr(`已选 ${ticked.size} 步`, `${ticked.size} ticked`)
              : tr("勾选几步可以一起撤销", "Tick steps to take them back together")}
          </span>
          <Button
            size="sm"
            className="ml-auto"
            disabled={!ticked.size || working}
            onClick={() =>
              run(
                tickedList,
                tr(`已撤销 ${tickedList.length} 步`, `Took back ${tickedList.length} steps`),
              )
            }
          >
            {tr("撤销所选", "Take back ticked")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
