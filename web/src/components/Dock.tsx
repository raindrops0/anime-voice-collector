import { RefreshCwIcon } from "lucide-react";
import type { ReactNode, Ref } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Kbd } from "@/components/ui/kbd";
import type { Roles } from "../api";
import { IGNORED, ignoredTip, lowTip, newTip, OTHER, type LabelText } from "../clips";
import { tr } from "../language";
import { Avatar } from "./Avatar";
import { type Flash, LOW_KEY, NEW_KEY, UNDO_KEY, useFlash } from "../flash";
import { Chip, LowButton } from "./Chip";
import { RoleName } from "./RoleName";
import { Tip } from "./Tip";

interface DockProps {
  dock: string[];
  roles: Roles;
  labelText: LabelText;
  /* Whether there is a line to label, which "New target" needs. */
  canNew: boolean;
  /* Whether there is a line to label: one selected, or lines ticked in Groups. */
  canLabel: boolean;
  onName: (name: string, low?: boolean) => void;
  onNew: () => void;
  canUndo: boolean;
  onUndo: () => void;
  /* The machine guessed again and the open list has changes waiting: lines to add, take out or move. */
  canRefresh: boolean;
  onRefresh: () => void;
  /* Update the list by itself whenever the machine guesses again. */
  autoRefresh: boolean;
  setAutoRefresh: (on: boolean) => void;
  /* The history button, see History. */
  history?: ReactNode;
  flash?: Flash;
  /* Gets the bar's element, so the page can keep messages above it. */
  ref?: Ref<HTMLElement>;
}

/* The bar at the bottom: one chip per target character, in a fixed order so the number keys don't move, then
   "Not a target", "New target" and "Ignore line". */
export function Dock({
  dock,
  roles,
  labelText,
  canNew,
  canLabel,
  onName,
  onNew,
  canUndo,
  onUndo,
  canRefresh,
  onRefresh,
  autoRefresh,
  setAutoRefresh,
  history,
  flash,
  ref,
}: DockProps) {
  const at = (key: string) => (flash?.key === key ? flash.n : undefined);
  const undoRef = useFlash<HTMLButtonElement>(canUndo ? at(UNDO_KEY) : undefined, "var(--primary)");
  return (
    <footer ref={ref} className="flex items-center gap-1.5 border-t bg-background px-3.5 py-2">
      {/* The chips wrap to a second row when there are many, so none scrolls away and Undo stays on screen. */}
      <div data-tour="dock" className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {dock.map((name, i) => (
          <Chip
            key={name}
            off={!canLabel}
            onPick={() => onName(name)}
            picture={<Avatar role={roles[name]} name={name} size="md" />}
            hotkey={i < 9 ? String(i + 1) : undefined}
            flash={at(name)}
            extra={
              <LowButton
                compact
                disabled={!canLabel}
                flash={at(name + LOW_KEY)}
                tip={lowTip()}
                hotkey={i < 9 ? i + 1 : undefined}
                onClick={() => onName(name, true)}
              />
            }
          >
            <RoleName role={roles[name]} name={name} />
          </Chip>
        ))}
        <Chip
          off={!canLabel}
          tip={tr("不是任何一个目标角色", "Not any of the target characters")}
          onPick={() => onName(OTHER)}
          picture={<Avatar blank size="md" />}
          hotkey="Q"
          flash={at(OTHER)}
        >
          {labelText[OTHER]}
        </Chip>
        <Chip
          off={!canNew}
          tip={newTip()}
          onPick={onNew}
          picture={<Avatar plus size="md" />}
          hotkey="N"
          flash={at(NEW_KEY)}
          tour="new"
        >
          {tr("新目标", "New target")}
        </Chip>
        <Chip
          off={!canLabel}
          tip={ignoredTip()}
          onPick={() => onName(IGNORED)}
          picture={<Avatar blank ignored size="md" />}
          hotkey="X"
          flash={at(IGNORED)}
        >
          {tr("忽略本条", "Ignore line")}
        </Chip>
        {/* Undo goes back on the last label, so it sits with the choices that label: at the right end of their
            last row, however many rows they take. The history next to it reaches further back. */}
        {/* Update list with its Auto switch under it, as one block. The button is gray until the machine's new
            guesses would change the list, so nothing moves when it can be used. */}
        <div className="ml-auto flex flex-none flex-col items-stretch gap-0.5">
          <Tip
            text={tr(
              "机器重新猜过后，列表先不动；点这里按新的猜测更新列表",
              "After the machine guesses again the list stays as it is; click to update it with the new guesses",
            )}
          >
            <Button
              variant={canRefresh ? "secondary" : "ghost"}
              size="xs"
              disabled={!canRefresh}
              onClick={onRefresh}
            >
              <RefreshCwIcon />
              {tr("更新列表", "Update list")}
            </Button>
          </Tip>
          <Tip
            text={tr(
              "勾上后，机器重新猜过就马上更新列表，不用再点；台词会在你眼前加进来、移出去、换位置",
              "When ticked, the list updates as soon as the machine guesses again, without a click; lines join, leave and move while you watch",
            )}
          >
            <label className="flex cursor-pointer items-center justify-center gap-1.5 text-xs text-muted-foreground">
              <Checkbox checked={autoRefresh} onCheckedChange={(on) => setAutoRefresh(on)} />
              {tr("自动", "Auto")}
            </label>
          </Tip>
        </div>
        <Button
          ref={undoRef}
          data-tour="undo"
          variant="ghost"
          size="sm"
          className="flex-none"
          disabled={!canUndo}
          onClick={onUndo}
        >
          {tr("撤销", "Undo")} <Kbd>Z</Kbd>
        </Button>
        {history}
      </div>
    </footer>
  );
}
