import { currentLanguage } from "./language";

import type { Clip } from "./generated";
import type { Job } from "./generated";
export type {
  Status,
  Guess,
  Clip,
  Counts,
  Role,
  Roles,
  Episode,
  Spoken,
  Model,
  Summary,
  ChangeResult,
  Job,
} from "./generated";

export interface AudioTracks {
  tracks: {
    number: number;
    tag: string;
    language: string | null;
    default: boolean;
    title: string;
  }[];
  number: number | null;
  language: string | null;
  from: "track" | "assumed" | null;
}

/* One step in the history list: /api/history. */
export interface HistoryEntry {
  batch: number;
  time: string;
  /* "human", "undo" (Z), "revert" (taken back from this list), or "import:…". */
  source: string;
  /* The steps this one takes back; empty for an ordinary step. */
  undo_of: number[];
  lines: number;
  /* The first line's text and episode, so the step can be recognized. */
  text: string | null;
  episode: string | null;
  /* Who the lines were labeled as, most first; null is "label cleared". */
  to: { name: string | null; count: number }[];
  low: number;
  not_low: number;
  rejects: number;
  renamed: { from: string; to: string } | null;
  merged: { from: string; into: string } | null;
  created: string[];
  /* The step in effect now that takes this one back. */
  undone_by: number | null;
  /* Why it cannot be taken back; null when it can. */
  why_not: string | null;
}

export interface HistoryPage {
  entries: HistoryEntry[];
  more: boolean;
}

export interface Group {
  size: number;
  seconds: number;
  hint: { name: string; share: number } | null;
  clips: Clip[];
}

/* One machine check, the same as a line of `avoc doctor`. */
export interface Check {
  ok: boolean;
  text: string;
  fix: string;
  required: boolean;
  /* "system": a question mark rather than a cross. "token" or "ffmpeg": checks the page shows its own steps for,
     instead of `fix`. */
  topic: string;
  /* The page can fix it with one click: FFmpeg on Windows. */
  can_install: boolean;
}

export interface SubtitleStyle {
  name: string;
  lines: number;
  first: number;
  last: number;
  samples: string[];
}

/* What the server read from a subtitle file: /api/subtitle-styles. */
export interface SubtitleStyles {
  format: string;
  encoding: string;
  styles: SubtitleStyle[];
  picked: string[];
  marked: string | null;
  /* The languages of its lines, most first: two for a bilingual file. */
  languages: string[];
  /* The language most of each style's lines are in; a style with no letters is missing. */
  style_languages: Record<string, string>;
}

/* The server's job that adds an episode: /api/add. */
export interface Adding {
  state: "idle" | "running" | "done" | "failed" | "stopped";
  episode: string | null;
  /* Whether its clips are cut, the slowest step; what comes after can be carried on. */
  cut?: boolean;
  lines: string[];
  errors: string[];
  bar: string | null;
  seconds: number;
  /* Every episode of the latest queue, in order; empty when a single episode was added. */
  queue?: { episode: string; state: "waiting" | "running" | "done" | "failed" | "stopped" }[];
}

export interface ExportResult {
  out: string;
  files: number;
  total_sec: number;
  rejected: Record<string, number>;
  /* The next free default folder, so exporting again does not land in the one just written. */
  next: string;
}

/* ───────────── Talking to the server ───────────── */

/* Every request says which language the page is in, so the server's messages come back in it too. */
export async function call<T>(url: string, body?: unknown): Promise<T> {
  const lang = currentLanguage();
  const response = await fetch(
    url,
    body === undefined
      ? { headers: { "X-Language": lang } }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Language": lang },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const error = (await response.json()) as { detail?: string | { msg: string }[] };
      detail =
        typeof error.detail === "string"
          ? error.detail
          : error.detail?.map((e) => e.msg).join("; ") || detail;
    } catch {
      /* Not JSON: keep the status text. */
    }
    throw new Error(sentence(detail));
  }
  return response.json() as Promise<T>;
}

/* A lost response can be retried with the same request ID without applying the change twice. */
export async function command<T>(
  operation: string,
  payload: object,
  revision: number | null,
  requestId: string = crypto.randomUUID(),
): Promise<T> {
  const body = { operation, payload, expected_revision: revision, request_id: requestId };
  try {
    return await call<T>("/api/commands", body);
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
    return call<T>("/api/commands", body);
  }
}

export async function waitForJob<T>(id: string, signal?: AbortSignal): Promise<T> {
  while (!signal?.aborted) {
    const job = await call<Job>(`/api/jobs/${encodeURIComponent(id)}`);
    if (job.state === "done") return job.result as T;
    if (["failed", "stopped", "interrupted"].includes(job.state))
      throw new Error(job.error || sentence(job.state));
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Stopped waiting");
}

/* The server's messages start in lower case, as on the command line; on the page they are sentences. */
export const sentence = (message: string) => message.charAt(0).toUpperCase() + message.slice(1);

export type MediaKind = "audio" | "video";

/* `fresh` throws away the saved cut and cuts again; a different number each time also keeps the browser from
   using its own saved copy. */
export function media(kind: MediaKind, id: string, context = 0, fresh = 0) {
  const query = new URLSearchParams();
  if (context) query.set("context", String(context));
  if (fresh) query.set("fresh", String(fresh));
  const rest = query.size ? `?${query}` : "";
  return `/media/${kind}/${id}.${kind === "audio" ? "wav" : "mp4"}${rest}`;
}

/* A file of an episode's whole copy: the picture alone, or one of its two sounds. */
export const episodeMedia = (episode: string, kind: "video" | "vocals" | "original") =>
  `/episode-media/${encodeURIComponent(episode)}/${kind}`;

/* Why a clip would not play: the server's message when it could not cut it, or null when it was cut but the
   file itself is broken. */
export async function mediaProblem(url: string): Promise<string | null> {
  const response = await fetch(url, { headers: { "X-Language": currentLanguage() } });
  if (response.ok) return null;
  try {
    return sentence(((await response.json()) as { detail?: string }).detail || response.statusText);
  } catch {
    return response.statusText;
  }
}

/* Fetch the next few clips' media ahead of time: the server cuts it on demand, so asking early means it is
   already cut by the time you get there. */
const warmed = new Set<string>();
export function warm(clips: (Clip | undefined)[], kind: MediaKind, context = 0) {
  for (const clip of clips) {
    if (!clip) continue;
    const url = media(kind, clip.id, context);
    if (warmed.has(url)) continue;
    warmed.add(url);
    fetch(url, { priority: "low" }).catch(() => warmed.delete(url));
  }
}
