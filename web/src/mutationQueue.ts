/* Keep writes in order and remember every line whose save has not finished yet. */
export class MutationQueue {
  private tail: Promise<void> = Promise.resolve();
  pending = 0;
  readonly saving = new Map<string, number>();

  private readonly onBusy: (busy: boolean) => void;

  constructor(onBusy: (busy: boolean) => void) {
    this.onBusy = onBusy;
  }

  enqueue<T>(ids: string[], work: () => Promise<T>): Promise<T> {
    this.pending += 1;
    this.onBusy(true);
    for (const id of ids) this.saving.set(id, (this.saving.get(id) ?? 0) + 1);
    const result = this.tail.then(work).finally(() => {
      for (const id of ids) {
        const left = (this.saving.get(id) ?? 1) - 1;
        if (left) this.saving.set(id, left);
        else this.saving.delete(id);
      }
      this.pending -= 1;
      if (!this.pending) this.onBusy(false);
    });
    this.tail = result.then(
      () => {},
      () => {},
    );
    return result;
  }
}
