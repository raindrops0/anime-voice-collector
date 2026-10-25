import { cn } from "cn";
import { Fragment, type ReactNode } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { tr } from "../language";
import { LOOKS, type PillLook, TODO_COUNT } from "../looks";
import { Tip } from "./Tip";

/* One tick box of a filter, or a named group of them. `keys` are the parts a box stands for: usually one, several
   for a box that stands for parts that look the same here. A group's own box comes before its parts, as in
   "[To do]: [Not confident] [Not guessed yet]", ticks or clears all of them, and shows a dash when only some are
   ticked. Every group has one, so all groups look alike. Each line is in exactly one part, so the ticked boxes list
   exactly the lines they count. */
export interface PartItem<K extends string> {
  keys: K[];
  label: ReactNode;
  count: number;
  tip?: ReactNode;
  /* The look of the pill on the lines of this part, so the box and its lines look alike. */
  look?: PillLook;
  /* The count of lines still to do: shown as the same orange count as on the tabs. */
  todo?: boolean;
  children?: PartItem<K>[];
  /* Boxes on the same line after a group's parts, past a divider line: not among its parts, so the group's box
     does not tick them. */
  after?: PartItem<K>[];
}

function PartBox<K extends string>({
  item,
  ticked,
  onChange,
  loading,
}: {
  item: PartItem<K>;
  ticked: Set<K>;
  onChange: (next: Set<K>) => void;
  loading?: boolean;
}) {
  const all = item.keys.every((k) => ticked.has(k));
  const some = !all && item.keys.some((k) => ticked.has(k));
  const set = () => {
    const next = new Set(ticked);
    for (const k of item.keys) {
      if (all) next.delete(k);
      else next.add(k);
    }
    onChange(next);
  };
  return (
    <Tip text={item.tip ?? ""}>
      <label
        className={cn(
          "flex cursor-pointer items-center gap-1.5 rounded-md border border-transparent px-1.5 py-0.5 whitespace-nowrap",
          item.look
            ? cn(LOOKS[item.look], "hover:opacity-80")
            : "text-foreground hover:bg-muted/60",
        )}
      >
        <Checkbox
          checked={all}
          indeterminate={some}
          onCheckedChange={set}
          className="bg-background"
        />
        <span>{item.label}</span>
        {loading ? (
          <span className="opacity-80">…</span>
        ) : item.todo && item.count > 0 ? (
          <span className={TODO_COUNT}>{item.count}</span>
        ) : (
          <span className="tabular-nums opacity-80">{item.count}</span>
        )}
      </label>
    </Tip>
  );
}

/* Which parts of a list are shown, in Scenes and in Characters. All boxes flow in one row that wraps. A group has
   lines of its own, so a box after it does not read as one of its parts, and its own box stays on the same line as
   its first part. No "Show" in front: on a narrow list it took a row of its own. */
export function PartFilter<K extends string>({
  items,
  ticked,
  onChange,
  loading,
  end,
}: {
  items: PartItem<K>[];
  ticked: Set<K>;
  onChange: (next: Set<K>) => void;
  /* The list has not come yet: the counts show "…", not 0. */
  loading?: boolean;
  /* Shown at the right end of the last line, such as what the ticked parts add up to. */
  end?: ReactNode;
}) {
  const box = (item: PartItem<K>) => (
    <PartBox
      key={item.keys.join()}
      item={item}
      ticked={ticked}
      onChange={onChange}
      loading={loading}
    />
  );
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
      {items.map((item, n) => {
        if (!item.children) return box(item);
        const [first, ...rest] = item.children;
        return (
          <Fragment key={item.keys.join()}>
            {n > 0 && !items[n - 1].children && <div className="h-0 basis-full" />}
            <div className="flex items-center gap-1">
              <span className="flex items-center">
                {box(item)}
                {tr("：", ":")}
              </span>
              {box(first)}
            </div>
            {rest.map(box)}
            {item.after && (
              <>
                <span className="mx-1 h-4 w-px bg-muted-foreground/60" aria-hidden="true" />
                {item.after.map(box)}
              </>
            )}
            {n < items.length - 1 && <div className="h-0 basis-full" />}
          </Fragment>
        );
      })}
      {end && <span className="ml-auto pl-2 whitespace-nowrap">{end}</span>}
    </div>
  );
}
