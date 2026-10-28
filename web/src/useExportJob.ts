import { useEffect, useRef, useState } from "react";
import { call, command, waitForJob, type ExportResult, type Job } from "./api";
import { tr } from "./language";

interface PendingExport {
  payload: object;
  revision: number;
  requestId: string;
}

export function useExportJob(
  workspace: string,
  done: (result: ExportResult) => void,
  error: (message: string) => void,
) {
  const key = `export-job:${workspace}`;
  const requestKey = `${key}:request`;
  const [id, setId] = useState<string | null>(() => localStorage.getItem(key));
  const [pending, setPending] = useState<string | null>(() => localStorage.getItem(requestKey));
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(!!id || !!pending);
  const callbacks = useRef({ done, error });
  callbacks.current = { done, error };
  useEffect(() => {
    const controller = new AbortController();
    if (!id && pending) {
      setBusy(true);
      const restore = async () => {
        const saved = JSON.parse(pending) as PendingExport;
        const job = await command<Job>("export", saved.payload, saved.revision, saved.requestId);
        if (controller.signal.aborted) return;
        localStorage.setItem(key, job.id);
        localStorage.removeItem(requestKey);
        setPending(null);
        setId(job.id);
      };
      restore().catch((e: Error) => {
        if (controller.signal.aborted) return;
        if (!(e instanceof TypeError)) {
          localStorage.removeItem(requestKey);
          setPending(null);
        }
        setBusy(false);
        callbacks.current.error(e.message);
      });
      return () => controller.abort();
    }
    if (!id) return;
    setBusy(true);
    waitForJob<ExportResult>(id, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        localStorage.removeItem(key);
        setBusy(false);
        setId(null);
        callbacks.current.done(result);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) {
          setBusy(false);
          callbacks.current.error(e.message);
        }
      });
    return () => controller.abort();
  }, [id, key, pending, requestKey, attempt]);
  return {
    busy,
    id,
    hasJob: !!id || !!pending,
    async start(payload: object, revision: number) {
      if (pending)
        throw new Error(tr("先接着处理上次的导出请求", "Resume the previous export request first"));
      const saved = JSON.stringify({ payload, revision, requestId: crypto.randomUUID() });
      localStorage.removeItem(key);
      localStorage.setItem(requestKey, saved);
      setBusy(true);
      setId(null);
      setPending(saved);
    },
    async resume() {
      if (id) await call(`/api/jobs/${id}/resume`, {});
      setAttempt((n) => n + 1);
    },
    async cancel() {
      let target = id;
      if (!target && pending) {
        const saved = JSON.parse(pending) as PendingExport;
        const job = await command<Job>("export", saved.payload, saved.revision, saved.requestId);
        target = job.id;
        localStorage.setItem(key, target);
        localStorage.removeItem(requestKey);
        setPending(null);
        setId(target);
      }
      if (target) await call(`/api/jobs/${target}/cancel`, {});
    },
  };
}
