import { useEffect, useRef } from "react";
import { call, type Clip, type Summary } from "./api";

/* Changes from another window or a script update the data while lists keep their places. */
export function useWorkspaceSync(
  revision: number | undefined,
  busy: boolean,
  update: (state: Summary, clips: Clip[]) => void,
) {
  const current = useRef({ revision, busy, update });
  current.current = { revision, busy, update };
  useEffect(() => {
    let active = true;
    let loading = false;
    const check = async () => {
      if (
        loading ||
        current.current.busy ||
        document.hidden ||
        current.current.revision === undefined
      )
        return;
      loading = true;
      try {
        const latest = await call<{ revision: number }>("/api/revision");
        if (latest.revision === current.current.revision) return;
        const snapshot = await call<{ state: Summary; clips: Clip[] }>("/api/snapshot");
        if (
          active &&
          !current.current.busy &&
          snapshot.state.revision > (current.current.revision ?? -1)
        )
          current.current.update(snapshot.state, snapshot.clips);
      } catch {
        /* The next check retries after a server restart. */
      } finally {
        loading = false;
      }
    };
    const timer = setInterval(() => void check(), 5000);
    window.addEventListener("focus", check);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, []);
}
