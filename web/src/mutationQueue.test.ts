import { expect, test } from "vitest";
import { MutationQueue } from "./mutationQueue";

test("a failed save does not lose the next save or clear its pending line", async () => {
  const busy: boolean[] = [];
  const queue = new MutationQueue((value) => busy.push(value));
  const order: number[] = [];
  const first = queue.enqueue(["a"], async () => {
    order.push(1);
    throw new Error("failed");
  });
  const second = queue.enqueue(["a"], async () => {
    order.push(2);
    expect(queue.saving.has("a")).toBe(true);
    return "saved";
  });
  await expect(first).rejects.toThrow("failed");
  await expect(second).resolves.toBe("saved");
  expect(order).toEqual([1, 2]);
  expect(queue.pending).toBe(0);
  expect(queue.saving.size).toBe(0);
  expect(busy.at(-1)).toBe(false);
});
