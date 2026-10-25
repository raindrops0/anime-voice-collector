import { lines, tr } from "./language";

/* What loading the machine's new guesses would change in the open list: lines joining it and lines leaving it.
   Both 0 when the lines would only change places. */
export interface Held {
  join: number;
  leave: number;
}

/* The changes in a few words, after a colon, or "the order changed" when lines only change places. */
function changeText({ join, leave }: Held, added: [string, string], gone: [string, string]) {
  const what = [
    join ? tr(`${join} 句${added[0]}`, `${lines(join)} ${added[1]}`) : "",
    leave ? tr(`${leave} 句${gone[0]}`, `${lines(leave)} ${gone[1]}`) : "",
  ].filter(Boolean);
  return what.length
    ? tr(`：${what.join("，")}`, `: ${what.join(", ")}`)
    : tr("，顺序有变", "; the order changed");
}

/* The note shown when the machine has guessed again: what would change, and how to update the list. */
export function heldText(held: Held) {
  const change = changeText(held, ["要加进来", "to add"], ["要移出", "to take out"]);
  return tr(
    `机器重新猜过了${change}。列表先不动，点「更新列表」再变。`,
    `The machine guessed again${change}. The list waits for Update list.`,
  );
}

/* The same note when Auto is on: the list has already changed. */
export function autoText(held: Held) {
  const change = changeText(held, ["加进来了", "added"], ["移出去了", "taken out"]);
  return tr(
    `机器重新猜过了，列表已跟着更新${change}。`,
    `The machine guessed again and the list updated${change}.`,
  );
}
