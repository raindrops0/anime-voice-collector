import { currentLanguage } from "./language";

/* ───────────── What the server sends back ─────────────
   Written by hand from src/avoc/app/server.py. When an answer there changes, change it here too. */

/* Where a line stands: confirmed by a person, the machine is confident, needs a person to check, no guess (no model
   yet, or no voiceprint), a short line skipped by default, ignored by a person, or set aside as very likely low
   quality. */
export type Status =
  "confirmed" | "auto" | "review" | "unlabeled" | "skipped" | "ignored" | "likely_low";

export interface Guess {
  name: string;
  p: number;
}

/* One line, as AppState.view writes it. */
export interface Clip {
  id: string;
  episode: string;
  start: number;
  end: number;
  duration: number;
  /* Shorter than 1 second or of at most two syllables: skipped by default (status "skipped") until someone labels
     it, and then used like any other line. Stays true after it is labeled. */
  short: boolean;
  /* Its voice overlaps another line's: two people speaking at once, most likely. */
  overlap: boolean;
  /* The main subtitle line, shown large. */
  text: string;
  /* The secondary subtitle line, shown small under it ("" when there is none). */
  display?: string;
  scene: number;
  voiced: boolean;
  label: string | null;
  rejects: string[];
  unusable: boolean;
  /* The machine's chance that it is low quality, only when high enough to show the hint; else null. */
  low: number | null;
  guess: Guess[];
  familiar: boolean | null;
  status: Status;
  /* Only in the Characters view's list: not given to this character, but it might be them. */
  maybe?: boolean;
  /* The text in the language spoken, as exported, and why it would not be exported (null if it would). */
  spoken: string;
  spoken_problem: string | null;
  /* The target character it belongs to, by a person's label or the machine's top guess. */
  role: string | null;
}

/* Lines confirmed, lines the machine gave them, and the seconds of the confirmed ones. `to_check` is the part of
   `predicted` without the "maybe low quality" hint: what Characters lists under Not confident and Confident. */
export interface Counts {
  confirmed: number;
  predicted: number;
  to_check: number;
  seconds: number;
  low_seconds: number;
}

export interface Role extends Counts {
  name: string;
  named: boolean;
  pattern: number;
  target: boolean;
  color?: string | null;
  avatar?: string | null;
}

/* The characters by name. A name may be missing: a label can name a character that has just been renamed. */
export type Roles = Record<string, Role | undefined>;

export interface Episode {
  name: string;
  video: boolean;
  offset: number | null;
  /* More than one when the subtitle timing jumped within the episode and each part got its own offset. */
  offset_parts?: number;
  counts: Partial<Record<Status, number>>;
  /* Lines still to do, what Scenes lists under To do: not confident or not guessed yet, without the "maybe low
     quality" hint. */
  work: number;
  /* Its whole-episode copy is ready, so lines play from it instead of one cut each. Missing on an older server. */
  player?: boolean;
  spoken: Spoken;
}

/* The language an episode speaks, and where its text in that language comes from. */
export interface Spoken {
  language: string;
  /* No audio track tag or person said it, so Japanese is taken. */
  assumed: boolean;
  /* "cut": the main subtitles are in that language; null: they are not, so there is no text. */
  source: "cut" | null;
  problem: string | null;
  /* Clips of target characters that cannot be exported with text. */
  blocked: number;
}

/* The audio tracks of a video: /api/audio-tracks. `number` is the one used when no language is given. */
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

export interface Model {
  labels?: number;
  roles?: number;
  seconds?: number;
  familiar_threshold?: number | null;
  /* A target is guessed once this many of their lines are confirmed and someone is labeled not them. */
  min_labels?: number;
  /* Targets not guessed yet: their confirmed lines, and lines known not to be them. */
  waiting?: Record<string, { lines: number; others: number }>;
  auto_confidence: number;
}

/* The overview: /api/state. */
export interface Summary {
  episodes: Episode[];
  workspace: string;
  /* Where an export goes by default, in full: exports/<today> in the workspace, or <today>-2 and so on when used. */
  export_folder: string;
  /* Episodes not loaded, and why. */
  skipped: Record<string, string>;
  /* Those of them whose clips were never cut: they can be given up. Missing when the server is older than this page. */
  not_cut?: string[];
  roles: Role[];
  other: Counts;
  model: Model;
  /* Seconds of picture shown before and after each line, with the vocals muted there (PICTURE_PAD in the
     server's video.py). Missing when the server is older than this page. */
  picture_pad?: number;
  can_undo: boolean;
  /* The program was updated after this server started. Missing when the server is older than this page. */
  outdated?: boolean;
  /* What the voices are for, chosen once at the start; null until then (see purpose.ts). */
  purpose: "tts" | "audio" | null;
}

/* The answer to a label change, an undo or a character change. */
export interface ChangeResult {
  batch: number | null;
  undo?: boolean;
  updated: Clip[];
  ripple: number;
  state: Summary;
  /* Only when a new character was made: its name. */
  role?: string;
  /* Only after taking steps back: steps left out because a name they need back is taken now, or a character
     they need is gone; and how many lines kept a later change. */
  skipped?: { batch: number; name: string }[];
  kept?: number;
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
      detail = ((await response.json()) as { detail?: string }).detail || detail;
    } catch {
      /* Not JSON: keep the status text. */
    }
    throw new Error(sentence(detail));
  }
  return response.json() as Promise<T>;
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
