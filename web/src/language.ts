/* The page comes in Chinese and English. The choice is kept on this machine; the first time, it follows the
   browser. Every string on screen is written as tr(Chinese, English) right where it is used. */

export type Language = "zh" | "en";

let lang: Language = "zh";

export const currentLanguage = (): Language => lang;

export const tr = <T>(zh: T, en: T): T => (lang === "en" ? en : zh);

/* English plural for a count: "1 line", "3 lines". */
export const many = (n: number, word: string, plural = `${word}s`) =>
  `${n} ${n === 1 ? word : plural}`;

export const lines = (n: number) => tr(`${n} 句`, many(n, "line"));

/* Show the language in the page's own lang attribute and title. */
const showLanguage = () => {
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.title = tr("avoc · 按角色整理动画台词", "avoc · sort anime lines by character");
};

/* Read the saved choice, or follow the browser the first time. Called once when the page starts. */
export function startLanguage() {
  const kept = localStorage.getItem("lang");
  lang =
    kept === "en" || kept === "zh"
      ? kept
      : navigator.language.toLowerCase().startsWith("zh")
        ? "zh"
        : "en";
  showLanguage();
}

/* Whether the person has picked a language on this machine, rather than it following the browser. */
export const languageChosen = () => ["zh", "en"].includes(localStorage.getItem("lang") ?? "");

/* Change the language and keep the choice. The caller re-renders the page. */
export function setLanguage(next: Language) {
  lang = next;
  localStorage.setItem("lang", lang);
  showLanguage();
}

/* The languages a voice can speak, as the server's codes. */
export const SPOKEN = ["ja", "zh", "en", "ko"] as const;

export const languageName = (code: string | null | undefined) =>
  ({
    ja: tr("日语", "Japanese"),
    zh: tr("中文", "Chinese"),
    en: tr("英语", "English"),
    ko: tr("韩语", "Korean"),
  })[code ?? ""] ??
  (code || tr("认不出", "unknown"));

/* The styles ticked at first. Reading text aloud cuts clips from the lines in the language spoken, so of a bilingual
   file that keeps each language in its own style, the other language's style is left unticked; it would cut every
   line a second time. If no picked style is in the language spoken, all stay ticked and the form warns instead. */
export function startingStyles(
  picked: string[],
  styleLanguages: Record<string, string>,
  spoken: string,
  needsText: boolean,
): string[] {
  if (!needsText) return picked;
  const kept = picked.filter((s) => (styleLanguages[s] ?? spoken) === spoken);
  return kept.length ? kept : picked;
}

/* The styles of secondary subtitles shown while labeling: of a bilingual file, only the translation, since the
   language spoken is already shown from the main subtitles. The server picks them the same way
   (translation_styles in stages/text_subtitle.py). If every style is in the language spoken, all stay. */
export function translationStyles(
  picked: string[],
  styleLanguages: Record<string, string>,
  spoken: string,
): string[] {
  const kept = picked.filter((s) => styleLanguages[s] !== spoken);
  return kept.length ? kept : picked;
}

/* "Chinese", or "Chinese and Japanese" for a bilingual file. */
export const languageNames = (codes: string[]) =>
  codes.length
    ? codes.map(languageName).join(tr("和", " and "))
    : tr("认不出语言", "language not recognized");
