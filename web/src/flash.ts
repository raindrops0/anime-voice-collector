import { useEffect, useRef } from "react";

/* Which bottom-bar button the last key press chose, and a count of key presses, so that button pulses once (see
   useFlash and docs/UI_DESIGN.md#layout). The button is a character's name, that name + LOW_KEY for its "Low
   quality", OTHER, NEW_KEY or UNDO_KEY. */
export interface Flash {
  key: string;
  n: number;
}

export const LOW_KEY = ":low";
export const NEW_KEY = ":new";
export const UNDO_KEY = ":undo";

/* A short pulse on a button when its key is pressed, so the eye sees which choice the key made. `n` counts key
   presses: each new number plays the pulse once, `undefined` plays nothing. `color` is a CSS color for the ring.
   With reduced motion asked for, only the ring shows, without the growing. */
export function useFlash<T extends HTMLElement>(n: number | undefined, color: string) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (n == null || !ref.current) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    ref.current.animate(
      [
        { transform: "scale(1)", boxShadow: `0 0 0 0 ${color}` },
        {
          transform: still ? "scale(1)" : "scale(1.08)",
          boxShadow: `0 0 0 4px ${color}`,
          offset: 0.3,
        },
        { transform: "scale(1)", boxShadow: "0 0 0 6px transparent" },
      ],
      { duration: 450, easing: "ease-out" },
    );
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when a key is pressed
  }, [n]);
  return ref;
}
