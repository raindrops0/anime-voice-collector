import { cn } from "cn";
import type { MouseEvent, ReactNode } from "react";
import { Kbd } from "@/components/ui/kbd";
import { useFlash } from "../flash";
import { tr } from "../language";
import { Tip } from "./Tip";

/* "Low quality" inside a character's chip or row: the same character, but not fit for a clean dataset (red, see
   docs/UI_DESIGN.md#color). `hotkey` is the number of the character, shown as Shift + number. `compact`, for the
   chips in the bottom bar and under groups, shows only the red key; the words move into the hint. */
export function LowButton({
  hotkey,
  tip,
  disabled,
  flash,
  compact,
  onClick,
}: {
  hotkey?: number;
  tip: ReactNode;
  disabled?: boolean;
  /* See useFlash. */
  flash?: number;
  compact?: boolean;
  onClick: () => void;
}) {
  const ref = useFlash<HTMLButtonElement>(disabled ? undefined : flash, "var(--destructive)");
  const words = tr("质量低", "Low quality");
  const press = (e: MouseEvent) => {
    e.stopPropagation();
    onClick();
  };
  if (compact)
    return (
      <Tip
        text={
          <>
            <b>{words}</b>
            {hotkey != null && ` (Shift + ${hotkey})`}: {tip}
          </>
        }
      >
        <button
          ref={ref}
          type="button"
          aria-label={words}
          disabled={disabled}
          onClick={press}
          className="ml-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-destructive/30 bg-destructive/10 px-1 text-[10px] font-medium whitespace-nowrap text-destructive transition-colors hover:border-destructive hover:bg-destructive/15 disabled:opacity-45 disabled:hover:border-destructive/30"
        >
          {hotkey != null ? `⇧${hotkey}` : tr("低", "Low")}
        </button>
      </Tip>
    );
  return (
    <Tip text={tip}>
      <button
        ref={ref}
        type="button"
        disabled={disabled}
        onClick={press}
        className="ml-0.5 inline-flex items-center gap-1 rounded-full border border-destructive/20 px-1.5 text-[11px] whitespace-nowrap text-destructive transition-colors hover:border-destructive disabled:opacity-45 disabled:hover:border-destructive/20"
      >
        {words}
        {hotkey != null && <Kbd className="h-4 min-w-4 text-[10px]">⇧{hotkey}</Kbd>}
      </button>
    </Tip>
  );
}

/* A "who is it" choice: a rounded button with a small picture, a name and its key (see docs/UI_DESIGN.md). The same
   look in the bottom bar and under each group. `top` marks the machine's guess; `off` grays it out when there is
   nothing to label yet, without hiding it. */
export function Chip({
  picture,
  children,
  hotkey,
  tip,
  top,
  off,
  small,
  onPick,
  extra,
  flash,
}: {
  picture: ReactNode;
  children: ReactNode;
  hotkey?: string;
  tip?: ReactNode;
  top?: boolean;
  off?: boolean;
  small?: boolean;
  onPick: () => void;
  /* More buttons inside the chip, such as "Low quality". */
  extra?: ReactNode;
  /* See useFlash. */
  flash?: number;
}) {
  const ref = useFlash<HTMLDivElement>(off ? undefined : flash, "var(--primary)");
  return (
    <Tip text={tip}>
      <div
        ref={ref}
        role="button"
        tabIndex={-1}
        aria-disabled={off || undefined}
        onClick={() => !off && onPick()}
        className={cn(
          "inline-flex flex-none cursor-pointer items-center gap-1.5 rounded-full border bg-background whitespace-nowrap transition-[border-color,box-shadow] hover:border-primary hover:shadow-md",
          small ? "py-0.5 pr-2.5 pl-0.5 text-[13px]" : "py-1 pr-2.5 pl-1",
          top && "border-primary/40 bg-accent",
          off && "cursor-default opacity-45 hover:border-border hover:shadow-none",
        )}
      >
        {picture}
        {children}
        {hotkey && <Kbd>{hotkey}</Kbd>}
        {extra}
      </div>
    </Tip>
  );
}
