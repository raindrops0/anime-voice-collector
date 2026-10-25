/* The looks of a pill, a small rounded label inside a line of text (see docs/UI_DESIGN.md#color). Green is
   confirmed, orange waits to be checked, red is low quality. A dashed outline is the machine's guess, which may be
   wrong; a solid look is a fact, a person's label or a fixed rule. The tick boxes of Scenes and Characters use the
   look of the pill on their lines. */
export const LOOKS = {
  confirmed: "bg-success/10 text-success",
  auto: "border-dashed border-muted-foreground/50 bg-muted text-muted-foreground",
  review: "border-dashed border-warning/70 bg-warning/15 text-warning",
  unlabeled: "bg-muted text-muted-foreground",
  done: "bg-muted text-muted-foreground",
  skipped: "border-border text-muted-foreground",
  ignored: "border-border text-muted-foreground",
  likely_low: "border-dashed border-destructive text-destructive",
  lowHint: "border-dashed border-destructive text-destructive",
  stranger: "border-dashed border-warning bg-warning/15 font-medium text-warning",
  unusable: "border-destructive text-destructive",
  noText: "border-warning text-warning",
  maybe: "border-dashed border-warning text-warning",
  overlap: "border-dashed border-muted-foreground/60 text-muted-foreground",
  closest: "border-dashed border-muted-foreground/50 bg-muted/60 pl-0.5 text-muted-foreground",
};

export type PillLook = keyof typeof LOOKS;

/* The orange count of lines still to do, the same wherever it shows: on the Scenes and Characters tabs, beside each
   character, and in the "To do" tick box. */
export const TODO_COUNT =
  "min-w-4 rounded-full bg-warning/15 px-1.5 text-center text-[11px] leading-4 font-semibold text-warning tabular-nums";
