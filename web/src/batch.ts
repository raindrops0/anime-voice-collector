import { tr } from "./language";

/* Adding several episodes at once: the server pairs the files in a video folder and a subtitle folder by episode
   number (batch.py), and the page names each episode and finds what stops it from being added. */

export interface PairedEpisode {
  number: number;
  videos: string[];
  subtitles: string[];
  display_subtitles?: string[];
}

export interface Pairs {
  episodes: PairedEpisode[];
  no_number: string[];
}

export interface Row {
  number: number;
  name: string;
  video: string | null;
  subtitles: string | null;
  display: string | null;
  /* Why it cannot be added, or null. */
  problem: string | null;
}

export type Kind = "videos" | "subtitles" | "display_subtitles";

export const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

/* Only the files whose name holds `filter`, such as "x265" when a folder has two encodes of each episode. */
export const narrow = (paths: string[], filter: string) => {
  const part = filter.trim().toLowerCase();
  return part ? paths.filter((p) => fileName(p).toLowerCase().includes(part)) : paths;
};

/* Whether some episode has more than one file of this kind, so a filter is needed. */
export const repeats = (pairs: Pairs, kind: Kind) =>
  pairs.episodes.some((e) => (e[kind]?.length ?? 0) > 1);

export const batchName = (prefix: string, number: number) =>
  `${prefix}${String(number).padStart(2, "0")}`;

/* The part before the number of the latest episode name, such as "usagi-s2-ep" from "usagi-s2-ep12", so the next
   season is named the same way. "ep" when there is none. */
export const namePrefix = (names: string[]) => {
  for (const name of [...names].reverse()) {
    const found = /^(.*?)\d+$/.exec(name);
    if (found?.[1]) return found[1];
  }
  return "ep";
};

const NAME = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

export function batchRows(
  pairs: Pairs,
  prefix: string,
  filters: Record<Kind, string>,
  taken: Set<string>,
): Row[] {
  return pairs.episodes.map((e) => {
    const name = batchName(prefix.trim(), e.number);
    const videos = narrow(e.videos, filters.videos);
    const subtitles = narrow(e.subtitles, filters.subtitles);
    const display = narrow(e.display_subtitles ?? [], filters.display_subtitles);
    const problem = !videos.length
      ? tr("没有视频", "no video")
      : videos.length > 1
        ? tr(
            `有 ${videos.length} 个视频，用上面的筛选留下一个`,
            `${videos.length} videos; narrow them with the filter above`,
          )
        : !subtitles.length
          ? tr("没有字幕", "no subtitles")
          : subtitles.length > 1
            ? tr(
                `有 ${subtitles.length} 个字幕，用上面的筛选留下一个`,
                `${subtitles.length} subtitle files; narrow them with the filter above`,
              )
            : !NAME.test(name)
              ? tr(
                  "集名只能用英文字母、数字、下划线和连字符",
                  "use only letters, digits, _ and - in names",
                )
              : taken.has(name)
                ? tr("已经有这一集", "already added")
                : null;
    return {
      number: e.number,
      name,
      video: videos.length === 1 ? videos[0] : null,
      subtitles: subtitles.length === 1 ? subtitles[0] : null,
      /* Secondary subtitles are optional: an episode without one, or with several, is added without. */
      display: display.length === 1 ? display[0] : null,
      problem,
    };
  });
}
