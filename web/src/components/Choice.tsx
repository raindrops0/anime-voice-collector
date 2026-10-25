import { cn } from "cn";
import type { ReactNode } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

/* A row of joined buttons for picking one of a few choices (see docs/UI_DESIGN.md). One is always on: pressing
   the one already on keeps it on, and picks it again only with `again`, for a choice that also does something,
   such as a speed that replays the line. `small` is the smaller size used below the picture. */
export function Choice<T extends string | number>({
  value,
  options,
  onPick,
  again,
  small,
  className,
}: {
  value: T;
  options: readonly (readonly [T, ReactNode])[];
  onPick: (value: T) => void;
  again?: boolean;
  small?: boolean;
  className?: string;
}) {
  return (
    <ToggleGroup
      variant="outline"
      size="sm"
      spacing={0}
      className={cn("max-w-fit", className)}
      value={[String(value)]}
      onValueChange={(values) => {
        /* Pressing the one already on asks to turn it off: nothing is picked. */
        const picked = options.find(([o]) => String(o) === values[0]);
        if (picked) onPick(picked[0]);
        else if (again) onPick(value);
      }}
    >
      {options.map(([o, label]) => (
        <ToggleGroupItem
          key={String(o)}
          value={String(o)}
          type="button"
          className={cn("tabular-nums", small && "h-6 text-xs")}
        >
          {label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
