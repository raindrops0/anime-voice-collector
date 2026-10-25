import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  call,
  type Adding,
  type AudioTracks,
  type Check,
  type Summary,
  type SubtitleStyles as Styles,
} from "../api";
import { cn } from "cn";
import { CheckIcon, CopyIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { Note } from "../components/Notes";
import { Section } from "../components/Section";
import { Choice } from "../components/Choice";
import { withKeys } from "../components/Keys";
import { PathInput } from "../components/PathInput";
import { Tip } from "../components/Tip";
import { minutes, nextEpisodeName } from "../format";
import {
  batchRows,
  fileName,
  namePrefix,
  repeats,
  type Kind,
  type Pairs,
  type Row,
} from "../batch";
import {
  currentLanguage,
  languageName,
  languageNames,
  lines,
  many,
  SPOKEN,
  startingStyles,
  tr,
  translationStyles,
} from "../language";
import { needsText, type Purpose } from "../purpose";
import type { Toast } from "../toast";

/* ───────────── Adding an episode ───────────── */

/* The progress of a running add: monospace, scrolling, kept at the bottom. */
const LOG =
  "m-0 max-h-[180px] overflow-y-auto rounded-lg bg-muted px-2.5 py-2 font-mono text-xs break-all whitespace-pre-wrap";

/* What `avoc doctor` finds on this machine. On the first page (`all`) every check is listed with a tick, so the
   person sees the machine is ready before adding anything; in the dialog only problems are shown, and nothing while
   checking or when all is well. Each failed check says what to do; the token gets its steps here, and the offset
   box links up to them. */
function MachineChecks({
  list,
  all,
  onCheck,
  checking,
}: {
  list: Check[] | null;
  all: boolean;
  onCheck: () => void;
  checking: boolean;
}) {
  if (!list && !all) return null;
  const shown = (list ?? []).filter((c) => all || !c.ok);
  if (list && !shown.length) return null;
  return (
    <Section id={MACHINE} title={tr("这台机器", "This machine")}>
      {!list && <Note>{tr("正在检查这台机器…", "Checking this machine…")}</Note>}
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]">
        {shown.map((c) => (
          <li
            key={c.text}
            className={cn("flex items-baseline gap-2", !c.ok && c.required && "text-destructive")}
          >
            <span
              className={cn(
                "w-3.5 flex-none font-semibold",
                c.ok ? "text-success" : c.required ? "text-destructive" : "text-warning",
              )}
            >
              {/* A cross for every failed check; red when the tool cannot work without it, orange when only one
                  feature needs it. A system other than Windows gets a question mark: untested, not broken. */}
              {c.ok ? "✓" : c.topic === "system" ? "?" : "✗"}
            </span>
            <span className="flex min-w-0 flex-col gap-1">
              {c.text}
              {!c.ok &&
                (c.topic === "token" ? (
                  <TokenSteps />
                ) : c.topic === "ffmpeg" ? (
                  <FfmpegSteps canInstall={c.can_install} onDone={onCheck} />
                ) : (
                  c.fix && <span className="text-muted-foreground">{c.fix}</span>
                ))}
            </span>
          </li>
        ))}
      </ul>
      {shown.some((c) => !c.ok) && (
        <div>
          <Button type="button" variant="outline" size="sm" disabled={checking} onClick={onCheck}>
            {checking
              ? tr("正在检查…", "Checking…")
              : tr("改好了，再检查一次", "Fixed it, check again")}
          </Button>
        </div>
      )}
    </Section>
  );
}

/* The id of the machine checks, which the offset box links up to. */
const MACHINE = "machine-checks";

const link = (href: string, text: string) => (
  <a
    href={href}
    target="_blank"
    rel="noreferrer"
    className="text-primary underline underline-offset-2"
  >
    {text}
  </a>
);

const shell = (text: string) => (
  <pre className="mt-1 mb-0 rounded-md bg-background px-2.5 py-1.5 font-mono text-xs whitespace-pre-wrap">
    {text}
  </pre>
);

/* How to install FFmpeg: one click where the server can do it (Windows), then the same steps as `avoc doctor`
   says, Scoop first and by hand second, for those who would rather do it themselves. */
function FfmpegSteps({ canInstall, onDone }: { canInstall: boolean; onDone: () => void }) {
  const [installing, setInstalling] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const install = async () => {
    setInstalling(true);
    setFailed(null);
    try {
      const done = await call<{ ok: boolean; output: string }>("/api/install-ffmpeg", {});
      if (done.ok) onDone();
      else
        setFailed(
          done.output || tr("没装上，原因不明。", "It did not install, for no clear reason."),
        );
    } catch (error) {
      setFailed((error as Error).message);
    } finally {
      setInstalling(false);
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3.5 py-3 text-[13px] text-foreground">
      <div className="font-semibold">
        {tr("avoc 靠它读视频、切音频，必须装。", "avoc needs it to read videos and cut audio.")}
      </div>
      {canInstall && (
        <div className="flex flex-col items-start gap-1.5">
          <Button type="button" size="sm" disabled={installing} onClick={install}>
            {installing && <Spinner />}
            {installing
              ? tr("正在安装…（约 1–3 分钟）", "Installing… (about 1–3 minutes)")
              : tr("一键帮我装好", "Install it for me in one click")}
          </Button>
          <span className="text-muted-foreground">
            {tr(
              "会用 Scoop 装 FFmpeg；没有 Scoop 就先装上它。都装在你的用户文件夹里，不用管理员权限，装好不用重启 avoc。",
              "It installs FFmpeg with Scoop, installing Scoop first if you have none. Both go in your user folder, need no administrator rights, and avoc needs no restart.",
            )}
          </span>
          {failed && (
            <>
              <span className="text-destructive">
                {tr(
                  "没装上，下面是安装时的输出。也可以照下面的步骤自己装：",
                  "It did not install; here is what it printed. You can also install it yourself with the steps below:",
                )}
              </span>
              <pre className="m-0 max-h-40 w-full overflow-auto rounded-md bg-background px-2.5 py-1.5 font-mono text-xs whitespace-pre-wrap">
                {failed}
              </pre>
            </>
          )}
        </div>
      )}
      <div className={cn(canInstall && "mt-1 font-semibold")}>
        {canInstall
          ? tr(
              "想自己装的话，最简单的是用 Scoop：",
              "To install it yourself, Scoop is the easiest:",
            )
          : tr("最简单的是用 Scoop：", "The easiest way is Scoop:")}
      </div>
      <ol className="m-0 flex list-decimal flex-col gap-1 pl-5">
        <li>
          {tr(
            "还没有 Scoop 的话，在 PowerShell 里运行这两行装上它（",
            "If you have no Scoop yet, install it by running these two lines in PowerShell (",
          )}
          {link("https://scoop.sh", tr("Scoop 官网", "the Scoop site"))}
          {tr("）：", "):")}
          {shell(
            "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser\nInvoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression",
          )}
        </li>
        <li>
          {tr("再运行：", "Then run:")}
          {shell("scoop install ffmpeg")}
        </li>
        <li>
          {tr(
            "关掉终端、新开一个，再启动 avoc，然后点下面的「再检查一次」。",
            'Close the terminal, open a new one, start avoc again, then click "check again" below.',
          )}
        </li>
      </ol>
      <div className="text-muted-foreground">
        {tr("不想用 Scoop 的话，也可以从 ", "Or, without Scoop, download the Windows build from ")}
        {link("https://ffmpeg.org/download.html", tr("FFmpeg 官网", "the FFmpeg site"))}
        {tr(
          " 下载 Windows 版，解压后把里面的 bin 文件夹加进 PATH 环境变量，再同样重启终端和 avoc。",
          ", unzip it and add its bin folder to the PATH environment variable, then restart the terminal and avoc the same way.",
        )}
      </div>
    </div>
  );
}

/* How to get the Hugging Face token that measuring the offset needs, step by step. */
function TokenSteps() {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3.5 py-3 text-[13px] text-foreground">
      <div className="font-semibold">
        {tr(
          "自动测字幕偏移要用它。做一次这几步（免费，约 3 分钟）：",
          "Measuring the subtitle offset needs it. Do these steps once (free, about 3 minutes):",
        )}
      </div>
      <ol className="m-0 flex list-decimal flex-col gap-1 pl-5">
        <li>
          {tr("登录 ", "Log in to ")}
          {link("https://huggingface.co/login", "Hugging Face")}
          {tr("，没有账号就免费注册一个。", " (sign up for free if you have no account).")}
        </li>
        <li>
          {tr("打开 ", "Open ")}
          {link(
            "https://huggingface.co/pyannote/speaker-diarization-community-1",
            tr("测偏移用的模型页", "the page of the model that measures the offset"),
          )}
          {tr("，同意使用条款。", " and accept its terms of use.")}
        </li>
        <li>
          {tr("在 ", "On ")}
          {link("https://huggingface.co/settings/tokens", tr("令牌页", "the tokens page"))}
          {tr(
            " 新建一个令牌，类型选 Read，复制它。",
            ", create a new token of type Read and copy it.",
          )}
        </li>
        <li>
          {tr(
            "在启动 avoc 的文件夹里打开终端（用 Windows 下载包的话，双击里面的 terminal.bat），运行下面这条命令，按提示粘贴令牌：",
            "Open a terminal in the folder you started avoc in (with the Windows download, double-click terminal.bat in it), run this command, and paste the token when asked:",
          )}
          {shell("uv run hf auth login")}
        </li>
      </ol>
      <div className="text-muted-foreground">
        {tr(
          "不想弄的话，在下面自己填字幕偏移也行，比如同一片源、同一字幕组之前测过的值。",
          "Or type the subtitle offset below yourself, such as the value measured for an earlier episode from the same source and subtitle group.",
        )}
      </div>
    </div>
  );
}

/* The command that adds an episode in a terminal, with a button that copies it. The parts in <> are to be
   filled in, and look it. */
function AddCommand({ workspace }: { workspace: string }) {
  const [copied, setCopied] = useState(false);
  const command = `uv run avoc add "${workspace}" <video> --subs <subtitles>`;
  const box = useRef<HTMLPreElement>(null);
  /* Browsers allow the clipboard only on a secure page, which a server opened from another machine over plain
     http is not; there the command is selected instead, ready for Ctrl+C. */
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      if (box.current) getSelection()?.selectAllChildren(box.current);
    }
  };
  const label = copied ? tr("已复制", "Copied") : tr("复制", "Copy");
  return (
    <div className="relative mt-1">
      <pre
        ref={box}
        className="rounded-lg bg-muted py-2 pr-10 pl-2.5 font-mono text-xs break-all whitespace-pre-wrap text-foreground"
      >
        uv run avoc add "{workspace}" <span className="text-muted-foreground">{"<video>"}</span>
        {" --subs "}
        <span className="text-muted-foreground">{"<subtitles>"}</span>
      </pre>
      <Tip text={label}>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1 right-1"
          aria-label={label}
          onClick={copy}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
        </Button>
      </Tip>
    </div>
  );
}

/* null: no subtitle path yet. {}: reading. Otherwise the server's description, or {error}. */
type Found = (Partial<Styles> & { error?: string }) | null;

/* What the server read from the main subtitles: the text encoding, and the styles (the named looks an ASS file
   gives its lines, such as "Default" or "OP"). The ticked styles are cut into clips; they start as the ones picked
   automatically. With a single style there is nothing to choose, so only the line count is shown. */
function SubtitleStyles({
  found,
  chosen,
  setChosen,
}: {
  found: NonNullable<Found>;
  chosen: Set<string>;
  setChosen: (next: Set<string>) => void;
}) {
  /* Subtitle groups often give each sign its own style with a line or two, so only the ticked styles and the next
     few biggest are shown at first. */
  const [all, setAll] = useState(false);
  if (found.error) return <Note warn>{found.error}</Note>;
  if (!found.styles) return <Note>{tr("正在读字幕…", "Reading the subtitles…")}</Note>;
  const format = (found.format ?? "").toUpperCase();
  const said = languageNames(found.languages ?? []);
  const read = tr(`${format}，${found.encoding}，${said}`, `${format}, ${found.encoding}, ${said}`);
  if (found.styles.length === 0)
    return (
      <Note warn>
        {tr(`字幕里没有台词（${read}）`, `There are no dialogue lines in the subtitles (${read})`)}
      </Note>
    );
  /* Marks such as speaker names that the text cleaning does not know, found in the picked styles. */
  const marked = found.marked && <Note warn>{found.marked}</Note>;
  if (found.styles.length === 1)
    return (
      <>
        <Note>
          {tr(
            `读到 ${found.styles[0].lines} 句台词（${read}）`,
            `Read ${lines(found.styles[0].lines)} of dialogue (${read})`,
          )}
        </Note>
        {marked}
      </>
    );
  const toggle = (name: string) => {
    const next = new Set(chosen);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setChosen(next);
  };
  const automatic = found.picked ?? [];
  /* Ordered by the automatic choice, not the ticks, so a row stays put when it is clicked. */
  const picked = (s: { name: string }) => Number(automatic.includes(s.name));
  const ordered = [...found.styles].sort((a, b) => picked(b) - picked(a) || b.lines - a.lines);
  const shown = all
    ? ordered
    : ordered.filter((s, i) => chosen.has(s.name) || i < automatic.length + 3);
  const hidden = ordered.filter((s) => !shown.includes(s));
  const hiddenLines = hidden.reduce((n, s) => n + s.lines, 0);
  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      <Note>
        {tr(
          `字幕（${read}）里的台词分几种样式。勾上的切成片段；歌词、招牌字之类的不用勾。已经自动选好，一般不用改，看看例句对不对就行。`,
          `The lines in these subtitles (${read}) come in several styles. Ticked styles are cut into clips; leave out song lyrics, signs and such. They are already picked automatically and rarely need changing; just check the sample lines.`,
        )}
      </Note>
      {shown.map((s) => (
        <label
          className="-mx-1.5 flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-0.5 text-[13px] hover:bg-muted/60"
          key={s.name}
        >
          <Checkbox
            className="mt-0.5"
            checked={chosen.has(s.name)}
            onCheckedChange={() => toggle(s.name)}
          />
          <span className="min-w-0">
            <b>{s.name}</b>{" "}
            <span className="text-xs text-muted-foreground">
              {lines(s.lines)} · {minutes(s.first)}–{minutes(s.last)}
            </span>
            <span className="block max-w-[560px] truncate text-xs text-muted-foreground">
              {s.samples.join(" ／ ")}
            </span>
          </span>
        </label>
      ))}
      {hidden.length > 0 && (
        <div>
          <Button type="button" variant="ghost" size="sm" onClick={() => setAll(true)}>
            {tr(
              `还有 ${hidden.length} 种样式，共 ${hiddenLines} 句`,
              `${many(hidden.length, "more style")}, ${lines(hiddenLines)} in all`,
            )}
          </Button>
        </div>
      )}
      {chosen.size === 0 && <Note warn>{tr("至少勾一种", "Tick at least one")}</Note>}
      {marked}
    </div>
  );
}

/* Ask the server about a path shortly after it stops changing. An answer for an older path is dropped. `null`
   while there is no path or no answer yet. */
type Answer<T> = Partial<T> & { error?: string };

function useAnswer<T>(url: string, path: string): Answer<T> | null {
  const [answer, setAnswer] = useState<{ for: string; found: Answer<T> } | null>(null);
  useEffect(() => {
    const clean = path.trim();
    if (!clean) return;
    let current = true;
    const timer = setTimeout(
      () =>
        call<T>(url, { path: clean })
          .then((found) => current && setAnswer({ for: path, found: found as Answer<T> }))
          .catch(
            (e: Error) =>
              current && setAnswer({ for: path, found: { error: e.message } as Answer<T> }),
          ),
      300,
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [url, path]);
  return path.trim() && answer?.for === path ? answer.found : null;
}

/* What was read from the secondary subtitles (display subtitles in the code), so a wrong file shows before the long run, not after it. Their
   dialogue styles are always picked automatically: of a bilingual file, only the translation (see translationStyles). */
function DisplayNote({ path, spoken }: { path: string; spoken: string }) {
  const found = useAnswer<Styles>("/api/subtitle-styles", path);
  if (!found) return null;
  if (found.error) return <Note warn>{found.error}</Note>;
  if (!found.styles) return <Note>{tr("正在读字幕…", "Reading the subtitles…")}</Note>;
  const shown = translationStyles(found.picked ?? [], found.style_languages ?? {}, spoken);
  const count = found.styles.filter((s) => shown.includes(s.name)).reduce((n, s) => n + s.lines, 0);
  const format = (found.format ?? "").toUpperCase();
  const said = languageNames(found.languages ?? []);
  const read = tr(`${format}，${found.encoding}，${said}`, `${format}, ${found.encoding}, ${said}`);
  return count ? (
    <Note>
      {tr(`读到 ${count} 句台词（${read}）`, `Read ${lines(count)} of dialogue (${read})`)}
    </Note>
  ) : (
    <Note warn>
      {tr(`字幕里没有台词（${read}）`, `There are no dialogue lines in the subtitles (${read})`)}
    </Note>
  );
}

/* Which audio track the voices are taken from, and the language it speaks. */
function TrackNote({ tracks, spoken }: { tracks: AudioTracks; spoken: string }) {
  if (!tracks.tracks.length)
    return <Note warn>{tr("视频里没有音轨", "The video has no audio track")}</Note>;
  const tagged = tracks.tracks.find((t) => t.language === spoken);
  const used = tagged ?? tracks.tracks.find((t) => t.default) ?? tracks.tracks[0];
  const what = [
    used.language ? languageName(used.language) : used.tag || tr("没标语言", "no language tag"),
    used.title,
  ]
    .filter(Boolean)
    .join(tr("，", ", "));
  return (
    <Note warn={!(tagged || tracks.tracks.length === 1)}>
      {tr(
        `视频里有 ${tracks.tracks.length} 条音轨，用第 ${used.number + 1} 条（${what}）`,
        `${many(tracks.tracks.length, "audio track")}; the voices are taken from track ${used.number + 1} (${what})`,
      )}
      {!tagged &&
        tracks.tracks.length > 1 &&
        tr(
          `。没有标成${languageName(spoken)}的音轨，确认一下`,
          `. No track is tagged ${languageName(spoken)}; check it`,
        )}
    </Note>
  );
}

/* The episodes found in the folders, one line each: ticked ones are added in this order. One that cannot be added
   says why and cannot be ticked. */
function BatchRows({
  rows,
  unticked,
  setUnticked,
}: {
  rows: Row[];
  unticked: Set<number>;
  setUnticked: (next: Set<number>) => void;
}) {
  const toggle = (number: number) => {
    const next = new Set(unticked);
    if (next.has(number)) next.delete(number);
    else next.add(number);
    setUnticked(next);
  };
  return (
    <div className="mt-1.5 flex flex-col gap-0.5">
      {rows.map((r) => (
        <label
          key={r.number}
          className={cn(
            "-mx-1.5 flex items-start gap-2 rounded-md px-1.5 py-0.5 text-[13px]",
            r.problem ? "text-muted-foreground" : "cursor-pointer hover:bg-muted/60",
          )}
        >
          <Checkbox
            className="mt-0.5"
            disabled={!!r.problem}
            checked={!r.problem && !unticked.has(r.number)}
            onCheckedChange={() => toggle(r.number)}
          />
          <span className="min-w-0">
            <b className={cn(!r.problem && "text-foreground")}>{r.name}</b>
            {r.problem && <span className="text-xs text-warning"> · {r.problem}</span>}
            {r.video && (
              <span className="block max-w-[560px] truncate text-xs text-muted-foreground">
                {fileName(r.video)}
                {r.subtitles && ` ／ ${fileName(r.subtitles)}`}
                {r.display && ` ／ ${fileName(r.display)}`}
              </span>
            )}
          </span>
        </label>
      ))}
    </div>
  );
}

/* When some episode has two files of a kind, such as two encodes, a box to keep only the files whose name holds
   some text. */
function NarrowBox({
  value,
  onChange,
  what,
}: {
  value: string;
  onChange: (value: string) => void;
  what: string;
}) {
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[13px]">
      <span className="text-muted-foreground">
        {tr(
          `有的集不止一个${what}，只用文件名里有`,
          `Some episodes have more than one ${what}; use only names with`,
        )}
      </span>
      <Input
        className="h-7 max-w-[140px]"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={tr("比如 x265", "such as x265")}
      />
      <span className="text-muted-foreground">{tr("的", "")}</span>
    </div>
  );
}

/* Where each episode of a queue stands. */
function QueueList({ queue }: { queue: NonNullable<Adding["queue"]> }) {
  const marks = {
    waiting: ["·", "text-muted-foreground", tr("等着", "waiting")],
    running: ["▸", "text-primary", tr("正在加", "adding")],
    done: ["✓", "text-success", tr("加好了", "added")],
    failed: ["✗", "text-destructive", tr("没加成", "failed")],
    stopped: ["■", "text-muted-foreground", tr("停下了", "stopped")],
  } as const;
  const done = queue.filter((q) => q.state === "done").length;
  return (
    <div className="flex flex-col gap-0.5 text-[13px]">
      <span className="text-xs text-muted-foreground">
        {tr(`共 ${queue.length} 集，加好 ${done} 集`, `${done} of ${queue.length} episodes added`)}
      </span>
      <div className="flex flex-wrap gap-x-3.5 gap-y-0.5">
        {queue.map((q) => {
          const [mark, color, said] = marks[q.state];
          return (
            <span key={q.episode} className="whitespace-nowrap">
              <span className={cn("inline-block w-3.5 font-semibold", color)}>{mark}</span>
              {q.episode} <span className="text-xs text-muted-foreground">{said}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export interface AddEpisodeProps {
  state: Summary;
  setState: (state: Summary) => void;
  adding: Adding | null;
  setAdding: (adding: Adding) => void;
  onOpen: (episode: string) => void;
  toast: Toast;
  onPurpose: (purpose: Purpose) => void;
  /* On the first page: list every machine check, not only the problems. */
  allChecks?: boolean;
}

const purposeNames = () => ({
  tts: tr("朗读文字（GPT-SoVITS 等）", "Read text aloud (GPT-SoVITS and such)"),
  audio: tr("只要声音（RVC 等）", "Sound only (RVC and such)"),
});

/* The form for one episode, and the progress of the `avoc add` the server runs for it. `adding` is the server's job
   status, polled by App. */
export function AddEpisode({
  state,
  setState,
  adding,
  setAdding,
  onOpen,
  toast,
  onPurpose,
  allChecks = false,
}: AddEpisodeProps) {
  const text = needsText();
  const last = [...state.episodes].reverse().find((e) => e.offset != null);
  const [video, setVideo] = useState("");
  const [subtitles, setSubtitles] = useState("");
  const [displaySubtitles, setDisplaySubtitles] = useState("");
  /* An episode whose subtitle timing jumped has no one offset to carry over, so the next is measured too. */
  const [offset, setOffset] = useState(
    last && (last.offset_parts ?? 1) === 1 ? String(last.offset) : "",
  );
  /* Empty lets the server take the next free epNN. The rule is the server's validate_name. */
  const [name, setName] = useState("");
  const badName = !!name.trim() && !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(name.trim());
  const takenName = state.episodes.some((e) => e.name === name.trim());
  const nextName = nextEpisodeName(state.episodes.map((e) => e.name));
  /* The machine checks of `avoc doctor`. Fetched when the form opens and again on "check again"; torch is loaded for
     the GPU check, so the first time can take a few seconds. */
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [checking, setChecking] = useState(false);
  const check = () => {
    setChecking(true);
    call<Check[]>("/api/doctor")
      .then(setChecks)
      .catch(() => setChecks([]))
      .finally(() => setChecking(false));
  };
  /* The server writes the checks in the page language, so they are fetched again when it changes. */
  const language = currentLanguage();
  useEffect(check, [language]);
  const noToken = !!checks?.some((c) => c.topic === "token" && !c.ok);
  /* Several episodes at once: a video folder and a subtitle folder, paired by episode number on the server. The
     first ticked episode stands for all of them in the audio track and subtitle style checks below. */
  const [several, setSeveral] = useState(false);
  const [folders, setFolders] = useState<Record<Kind, string>>({
    videos: "",
    subtitles: "",
    display_subtitles: "",
  });
  const [filters, setFilters] = useState<Record<Kind, string>>({
    videos: "",
    subtitles: "",
    display_subtitles: "",
  });
  const [prefix, setPrefix] = useState(() => namePrefix(state.episodes.map((e) => e.name)));
  const [unticked, setUnticked] = useState(new Set<number>());
  const [pairs, setPairs] = useState<{ for: string; found: Pairs | { error: string } } | null>(
    null,
  );
  const pairsKey = JSON.stringify([folders.videos, folders.subtitles, folders.display_subtitles]);
  useEffect(() => {
    if (!several || !folders.videos.trim() || !folders.subtitles.trim()) return;
    let current = true;
    const timer = setTimeout(
      () =>
        call<Pairs>("/api/add/pairs", folders)
          .then((found) => current && setPairs({ for: pairsKey, found }))
          .catch((e: Error) => current && setPairs({ for: pairsKey, found: { error: e.message } })),
      300,
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- pairsKey stands for the folders
  }, [several, pairsKey]);
  const paired = pairs?.for === pairsKey ? pairs.found : null;
  const foundPairs = paired && "episodes" in paired ? paired : null;
  const taken = new Set(state.episodes.map((e) => e.name));
  const rows = foundPairs ? batchRows(foundPairs, prefix, filters, taken) : [];
  const ticked = rows.filter((r) => !r.problem && !unticked.has(r.number));
  const first = ticked[0];
  const videoPath = several ? (first?.video ?? "") : video;
  const subtitlePath = several ? (first?.subtitles ?? "") : subtitles;
  /* "" lets the audio track's tag decide. */
  const [spoken, setSpoken] = useState("");
  const tracks = useAnswer<AudioTracks>("/api/audio-tracks", videoPath);
  const automatic = tracks?.language || "ja";
  const heard = spoken || automatic;
  const [busy, setBusy] = useState(false);
  /* The server's answer, and the text of the box it answers. */
  const [answer, setAnswer] = useState<{ for: string; found: Found } | null>(null);
  /* "Reading" is worked out here rather than set when the text changes: setting a new {} on every key made
     React stop with "Maximum update depth exceeded" when text arrived fast. */
  const found: Found = !subtitlePath.trim()
    ? null
    : answer?.for === subtitlePath
      ? answer.found
      : {};
  /* Reading text aloud needs each clip's own words, so its main subtitles must be in the language spoken (a
     bilingual file counts). Clips cut from a translation don't line up with the original lines. */
  const wrongLanguage = text && !!found?.languages?.length && !found.languages.includes(heard);
  const [chosen, setChosen] = useState(new Set<string>());
  const log = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [adding?.lines.length]);
  /* Read the subtitles shortly after the path stops changing. An answer for an older path is dropped. */
  useEffect(() => {
    const path = subtitlePath.trim();
    if (!path) return;
    let current = true;
    const timer = setTimeout(
      () =>
        call<Styles>("/api/subtitle-styles", { path })
          .then((f) => {
            if (current) setAnswer({ for: subtitlePath, found: f });
          })
          .catch((e: Error) => {
            if (current) setAnswer({ for: subtitlePath, found: { error: e.message } });
          }),
      300,
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [subtitlePath]);
  /* Tick the starting styles when the subtitles are read, and again when the language spoken becomes known or is
     changed, since it decides which half of a bilingual file is cut. */
  const read = answer?.found;
  useEffect(() => {
    if (read?.picked)
      setChosen(new Set(startingStyles(read.picked, read.style_languages ?? {}, heard, text)));
  }, [read, heard, text]);
  const progress = useRef<HTMLDivElement>(null);
  const run = async (body: object, url = "/api/add") => {
    setBusy(true);
    try {
      /* The first add also fixes what the voices are for. */
      if (!state.purpose)
        setState(await call<Summary>("/api/purpose", { purpose: text ? "tts" : "audio" }));
      setAdding(await call<Adding>(url, body));
      /* The button is at the bottom and the progress at the top: bring the progress into view, or nothing seems to
         happen. */
      requestAnimationFrame(() =>
        progress.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
      );
    } catch (e) {
      toast((e as Error).message, true);
    }
    setBusy(false);
  };
  const start = (e: FormEvent) => {
    e.preventDefault();
    const seconds = offset.trim() === "" ? null : Number(offset);
    if (seconds !== null && !Number.isFinite(seconds)) {
      toast(
        tr("字幕偏移要填一个数，比如 -0.95", "The subtitle offset must be a number, such as -0.95"),
        true,
      );
      return;
    }
    /* While the subtitles are still being read, or could not be read, the server picks the styles itself. */
    const styles = found?.styles
      ? found.styles.map((s) => s.name).filter((n) => chosen.has(n))
      : null;
    if (several) {
      /* Left as picked automatically, each episode picks its own: the counts differ, and a style with few lines in
         the first episode may have none in another. */
      const starting = read?.picked
        ? startingStyles(read.picked, read.style_languages ?? {}, heard, text)
        : [];
      const same = styles?.length === starting.length && starting.every((s) => chosen.has(s));
      run(
        {
          episodes: ticked.map((r) => ({
            name: r.name,
            video: r.video,
            subtitles: r.subtitles,
            display_subtitles: r.display ?? "",
          })),
          offset: seconds,
          styles: same ? null : styles,
          spoken: spoken || null,
        },
        "/api/add/queue",
      );
      return;
    }
    run({
      video,
      subtitles,
      display_subtitles: displaySubtitles,
      offset: seconds,
      styles,
      spoken: spoken || null,
      name: name.trim(),
    });
  };
  const stop = async () => {
    setBusy(true);
    try {
      setAdding(await call<Adding>("/api/add/stop", {}));
    } catch (e) {
      toast((e as Error).message, true);
    }
    setBusy(false);
  };
  const forget = async (episode: string) => {
    setBusy(true);
    try {
      setState(await call<Summary>("/api/add/forget", { episode }));
    } catch (e) {
      toast((e as Error).message, true);
    }
    setBusy(false);
  };
  const running = adding?.state === "running";
  /* The episode being added now is shown in the box above, not here as well. */
  const unfinished = Object.entries(state.skipped || {}).filter(
    ([name]) => !(running && name === adding?.episode),
  );
  /* What is kept after it ended without finishing. The slowest step, cutting the clips, is kept only once it is
     done; stopped partway, it starts over. */
  const kept = adding?.cut
    ? tr(
        "切好的片段和算好的声纹都留着，在下面「没做完的集」里点「接着做」，从停下的地方接着做。",
        "The clips and the voiceprints already done are kept. Press Carry on under Unfinished episodes to go on from where it stopped.",
      )
    : tr(
        "切片段这一步没做完，没有留下什么。在下面「没做完的集」里点「接着做」，会从头切。",
        "Cutting the clips was not finished, so nothing is kept. Pressing Carry on under Unfinished episodes cuts them again from the start.",
      );
  const after =
    adding?.state === "failed"
      ? tr(
          `改好问题以后再试：文件没问题就点「接着做」，要换文件就在下面重填再点「开始」。${kept}`,
          `Fix the problem, then try again: if the files are right, press Carry on; to use other files, fill in the form below and press Start. ${kept}`,
        )
      : kept;
  const trackNote =
    tracks &&
    (tracks.error ? (
      <Note warn>{tracks.error}</Note>
    ) : (
      tracks.tracks && (
        <>
          {several && first && (
            <Note>{tr(`以 ${first.name} 为例：`, `Taking ${first.name} as an example:`)}</Note>
          )}
          <TrackNote tracks={tracks as AudioTracks} spoken={heard} />
        </>
      )
    ));
  const heading =
    adding &&
    {
      idle: "",
      running: tr(`正在加 ${adding.episode}…`, `Adding ${adding.episode}…`),
      done: tr(`${adding.episode} 加好了`, `${adding.episode} is added`),
      failed: tr(`${adding.episode} 没加成`, `${adding.episode} failed`),
      stopped: tr(`${adding.episode} 已停下`, `${adding.episode} was stopped`),
    }[adding.state];
  return (
    <div className="flex flex-col gap-6">
      {adding && adding.state !== "idle" && (
        <div
          ref={progress}
          className={cn(
            "flex flex-col gap-2 rounded-xl border px-3 py-2.5",
            adding.state === "done" && "bg-success/10",
            adding.state === "failed" && "border-destructive",
          )}
        >
          <div className="flex items-center gap-2.5">
            <b>{heading}</b>
            <span className="text-xs text-muted-foreground">{minutes(adding.seconds)}</span>
            <span className="flex-1"></span>
            {running && (
              <Button variant="outline" size="sm" disabled={busy} onClick={stop}>
                {tr("停下", "Stop")}
              </Button>
            )}
            {adding.state === "done" &&
              adding.episode &&
              state.episodes.some((e) => e.name === adding.episode) && (
                <Button size="sm" onClick={() => onOpen(adding.episode as string)}>
                  {tr(`打开 ${adding.episode}`, `Open ${adding.episode}`)}
                </Button>
              )}
          </div>
          {(adding.queue?.length ?? 0) > 1 && <QueueList queue={adding.queue ?? []} />}
          <pre className={LOG} ref={log}>
            {adding.lines.join("\n") || tr("正在启动…", "Starting…")}
          </pre>
          {running && adding.bar && (
            <Note className="overflow-hidden font-mono text-ellipsis whitespace-pre">
              {adding.bar}
            </Note>
          )}
          {adding.state === "failed" && adding.errors?.length > 0 && (
            <pre className={cn(LOG, "bg-destructive/10 text-destructive")}>
              {adding.errors.slice(-15).join("\n")}
            </pre>
          )}
          {running && (
            <Note>
              {tr(
                "有显卡时一集要 10 到 15 分钟，只用 CPU 会慢很多。",
                "With a GPU one episode takes 10 to 15 minutes; on the CPU it takes much longer.",
              )}{" "}
              {state.episodes.length > 0
                ? tr(
                    "可以关掉这个窗口接着标别的集，做完会提示。",
                    "You can close this and keep labeling other episodes; you will be told when it is done.",
                  )
                : tr(
                    "做完后从这里打开这一集。",
                    "When it is done, open the episode from here.",
                  )}{" "}
              {adding.cut
                ? tr(
                    "片段已经切好，现在停下的话，下次从这里接着做。",
                    "The clips are cut; if it stops now, the next run goes on from here.",
                  )
                : tr(
                    "切片段是最慢的一步，在这一步停下的话，下次要从头切。",
                    "Cutting the clips is the slowest step; if it stops during this step, the next run cuts them again from the start.",
                  )}
            </Note>
          )}
          {(adding.state === "failed" || adding.state === "stopped") && <Note>{after}</Note>}
        </div>
      )}
      {unfinished.length > 0 && (
        <Section title={tr("没做完的集", "Unfinished episodes")}>
          {unfinished.length > 1 && (
            <div>
              <Button
                variant="outline"
                size="sm"
                disabled={busy || running}
                onClick={() => run({ resume: unfinished.map(([name]) => name) }, "/api/add/queue")}
              >
                {tr("全部接着做，一集接一集", "Carry on with all, one after another")}
              </Button>
            </div>
          )}
          {unfinished.map(([name, why]) => (
            <div className="mt-1 flex items-center gap-2.5" key={name}>
              <b>{name}</b>
              <span className="flex-1 text-xs text-muted-foreground">{why}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={busy || running}
                onClick={() => run({ resume: name })}
              >
                {tr("接着做", "Carry on")}
              </Button>
              {state.not_cut?.includes(name) && (
                <Tip
                  text={tr(
                    "删掉这一集的记录和做了一半的文件",
                    "Delete its record and half-built files",
                  )}
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy || running}
                    onClick={() => forget(name)}
                  >
                    {tr("不要了", "Give up")}
                  </Button>
                </Tip>
              )}
            </div>
          ))}
        </Section>
      )}
      <MachineChecks list={checks} all={allChecks} onCheck={check} checking={checking} />
      <form className="flex flex-col gap-6" onSubmit={start}>
        <Section title={tr("收集声音做什么用", "What the voices are for")}>
          {/* Chosen once, before the first episode; after that only shown. */}
          {state.purpose ? (
            <>
              <div className="text-sm font-medium">{purposeNames()[state.purpose]}</div>
              <Note>
                {tr(
                  "开始时选定的，这个工作区的每一集都按它收集。中途换用途还不支持。",
                  "Chosen at the start; every episode in this workspace is collected this way. Switching midway is not supported yet.",
                )}
              </Note>
            </>
          ) : (
            <>
              <Choice<Purpose>
                value={text ? "tts" : "audio"}
                options={[
                  ["audio", purposeNames().audio],
                  ["tts", purposeNames().tts],
                ]}
                onPick={onPurpose}
              />
              <ul className="flex list-disc flex-col gap-1 pl-5 text-[13px] text-muted-foreground">
                <li>
                  <b className="font-semibold text-foreground">{purposeNames().audio}</b>
                  {tr(
                    "：只收集角色的声音，用来训练变声模型，也就是把别人说的话换成这个角色的音色。字幕用什么语言都行。",
                    ": collects only the character's voice, to train a voice-changing model, which turns someone else's speech into this character's voice. Subtitles in any language will do.",
                  )}
                </li>
                <li>
                  <b className="font-semibold text-foreground">{purposeNames().tts}</b>
                  {tr(
                    "：连同每句台词的原话一起收集，用来训练朗读模型，让这个角色念出你给的任何文字。主字幕必须是视频原来的语言：日语动画就要日语字幕。",
                    ": collects each line together with the words actually said, to train a text-to-speech model that has this character read any text you give it. The main subtitles must be in the video's original language: Japanese subtitles for a Japanese anime.",
                  )}
                </li>
              </ul>
              {/* The one choice that cannot be undone later, so it is said plainly before anything is picked. */}
              <Note warn={!text}>
                <b className="mb-1 block text-base">
                  {tr(
                    "想好再选：拿不准就选「朗读文字」。",
                    'Decide first: if unsure, choose "Read text aloud".',
                  )}
                </b>
                {tr(
                  "选了「朗读文字」，导出时还能退回只导出声音，给 RVC 用；选了「只要声音」，导出时不能升级成朗读文字，因为没有收集原话。开始加第一集后就不能再改。",
                  'With "Read text aloud", Export can still fall back to sound only, for RVC. With "Sound only", Export cannot move up to reading text aloud, because the words were never collected. Once the first episode starts, this cannot be changed.',
                )}
              </Note>
            </>
          )}
        </Section>
        <Section title={tr("加几集", "How many episodes")}>
          <Choice
            value={several ? "many" : "one"}
            options={[
              ["one", tr("一集", "One")],
              ["many", tr("多集，一集接一集", "Several, one after another")],
            ]}
            onPick={(v) => {
              setSeveral(v === "many");
              /* Episodes from one source can differ by a second (S2 of one test anime: -1.30 and -0.67), so a
                 queue measures each by default. */
              if (v === "many") setOffset("");
            }}
          />
        </Section>
        {!several && (
          <Section title={tr("视频文件", "Video file")}>
            <PathInput
              kind="video"
              value={video}
              onChange={setVideo}
              placeholder={tr("视频文件的路径", "Path to the video file")}
              toast={toast}
            />
            {trackNote}
          </Section>
        )}
        {several && (
          <>
            <Section title={tr("文件夹", "Folders")}>
              <PathInput
                kind="folder"
                value={folders.videos}
                onChange={(v) => setFolders({ ...folders, videos: v })}
                placeholder={tr("视频所在的文件夹", "Folder with the videos")}
                toast={toast}
              />
              {foundPairs && repeats(foundPairs, "videos") && (
                <NarrowBox
                  what={tr("视频", "video")}
                  value={filters.videos}
                  onChange={(v) => setFilters({ ...filters, videos: v })}
                />
              )}
              <PathInput
                kind="folder"
                value={folders.subtitles}
                onChange={(v) => setFolders({ ...folders, subtitles: v })}
                placeholder={tr("主字幕所在的文件夹", "Folder with the main subtitles")}
                toast={toast}
              />
              {foundPairs && repeats(foundPairs, "subtitles") && (
                <NarrowBox
                  what={tr("字幕", "subtitle file")}
                  value={filters.subtitles}
                  onChange={(v) => setFilters({ ...filters, subtitles: v })}
                />
              )}
              <PathInput
                kind="folder"
                value={folders.display_subtitles}
                onChange={(v) => setFolders({ ...folders, display_subtitles: v })}
                placeholder={tr(
                  "辅助字幕所在的文件夹（可以不填）",
                  "Folder with the secondary subtitles (optional)",
                )}
                toast={toast}
              />
              {foundPairs && repeats(foundPairs, "display_subtitles") && (
                <NarrowBox
                  what={tr("辅助字幕", "secondary subtitle file")}
                  value={filters.display_subtitles}
                  onChange={(v) => setFilters({ ...filters, display_subtitles: v })}
                />
              )}
              <Note>
                {tr(
                  "按文件名里的集数配对，比如 S02E03、[03]、- 03。视频和字幕可以在同一个文件夹。辅助字幕见下面的说明。",
                  "Files are paired by the episode number in their names, such as S02E03, [03] or - 03. The videos and subtitles may share a folder. Secondary subtitles are explained below.",
                )}
              </Note>
            </Section>
            <Section title={tr("要加的集", "Episodes to add")}>
              <div className="flex items-center gap-2 text-[13px]">
                <span className="text-muted-foreground">{tr("集名：", "Names:")}</span>
                <Input
                  className="h-7 max-w-[160px]"
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                />
                <span className="text-muted-foreground">
                  {tr("后面接集数，比如 ", "then the number, such as ")}
                  {`${prefix.trim()}01`}
                </span>
              </div>
              {paired && "error" in paired && <Note warn>{paired.error}</Note>}
              {foundPairs && rows.length === 0 && (
                <Note warn>
                  {tr(
                    "文件夹里没找到带集数的视频或字幕",
                    "No videos or subtitles with an episode number were found",
                  )}
                </Note>
              )}
              <BatchRows rows={rows} unticked={unticked} setUnticked={setUnticked} />
              {foundPairs && foundPairs.no_number.length > 0 && (
                <Note>
                  {tr(
                    `${foundPairs.no_number.length} 个文件名里没有集数，没用上：`,
                    `${many(foundPairs.no_number.length, "file")} with no episode number left out: `,
                  )}
                  {foundPairs.no_number.slice(0, 3).map(fileName).join(" ／ ")}
                  {foundPairs.no_number.length > 3 && " …"}
                </Note>
              )}
              {first && trackNote}
            </Section>
          </>
        )}
        <Section title={tr("角色说哪种语言", "Language the characters speak")}>
          {/* Each language once. The one the audio track gives (Japanese when it has no tag) is marked, and
              picking it again goes back to letting the track decide. */}
          <NativeSelect
            className="max-w-fit"
            value={heard}
            onChange={(e) => setSpoken(e.target.value === automatic ? "" : e.target.value)}
          >
            {[...new Set([automatic, ...SPOKEN])].map((code) => (
              <NativeSelectOption key={code} value={code}>
                {languageName(code)}
                {code === automatic &&
                  (tracks?.language
                    ? tr("（音轨上标的）", " (as the audio track says)")
                    : tr("（音轨没标语言时默认）", " (when the audio track doesn't say)"))}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <Note>
            {tr(
              "一般不用改。视频里有原声和配音两条音轨时，选你要收集的那种语言。",
              "Usually leave it as is. If the video has both the original voices and a dub, pick the language of the voices you want.",
            )}
          </Note>
        </Section>
        <Section title={tr("主字幕", "Main subtitles")} aside="ASS / SRT">
          {several ? (
            first && (
              <Note>
                {tr(
                  `下面读的是 ${first.name} 的字幕。样式没改的话，每集自己挑；改了的话，每集都用勾上的样式。`,
                  `Below is what was read from ${first.name}. Left as they are, each episode picks its own styles; once changed, every episode uses the ticked ones.`,
                )}
              </Note>
            )
          ) : (
            <PathInput
              kind="subtitles"
              value={subtitles}
              onChange={setSubtitles}
              placeholder={tr("主字幕文件的路径", "Path to the main subtitles")}
              toast={toast}
            />
          )}
          {!found && (
            <Note>
              {text
                ? tr(
                    "台词按主字幕切：每句字幕按它的时间切成一段。最好用角色说的语言（一般是日语）的字幕，导出时文字才对得上。",
                    "Lines are cut by the main subtitles: each entry becomes one clip, at its times. Best in the language the characters speak (usually Japanese), so the text matches on export.",
                  )
                : tr(
                    "台词按主字幕切：每句字幕按它的时间切成一段。",
                    "Lines are cut by the main subtitles: each entry becomes one clip, at its times.",
                  )}
            </Note>
          )}
          {found && (
            <SubtitleStyles
              key={subtitlePath}
              found={found}
              chosen={chosen}
              setChosen={setChosen}
            />
          )}
          {found?.languages?.length === 1 && found.languages[0] === heard && (
            <Note>
              {text
                ? tr(
                    "主字幕和角色说的是同一种语言，所以每段的文字就是它自己那句台词。一条字幕里有两个人说话（用「－」或名字标出）的，会按人分开切。",
                    "The main subtitles are in the language spoken, so each clip's text is its own line. An entry where two people speak (marked with a dash or a name) is cut into one clip per person.",
                  )
                : tr(
                    "主字幕和角色说的是同一种语言。一条字幕里有两个人说话（用「－」或名字标出）的，会按人分开切。",
                    "The main subtitles are in the language spoken: an entry where two people speak (marked with a dash or a name) is cut into one clip per person.",
                  )}
            </Note>
          )}
          {wrongLanguage && found?.languages && (
            <Note warn>
              {tr(
                `朗读文字要用角色说的语言做主字幕：这份是${languageNames(found.languages)}，这一集说的是${languageName(heard)}。换一份${languageName(heard)}字幕填在这里；这份可以填到下面的「辅助字幕」，标注时给你看。${state.purpose ? "" : "只要声音的话，在最上面选「只要声音」。"}`,
                `Reading text aloud needs main subtitles in the language spoken: these are in ${languageNames(found.languages)}, and this episode speaks ${languageName(heard)}. Put ${languageName(heard)} subtitles here; these can go under "Secondary subtitles" below, to be shown while labeling.${state.purpose ? "" : ' If you only want the sound, choose "Sound only" at the top.'}`,
              )}
            </Note>
          )}
          {/* Allowed for sound only, but said once more for this file: there is no way to add the text later. */}
          {!text && !!found?.languages?.length && !found.languages.includes(heard) && (
            <Note warn>
              {tr(
                `这份主字幕是${languageNames(found.languages)}，这一集说的是${languageName(heard)}：用它切，这一集永远导不出台词文字。有${languageName(heard)}字幕的话，用它当主字幕，这份填到下面的「辅助字幕」。`,
                `These main subtitles are in ${languageNames(found.languages)}, and this episode speaks ${languageName(heard)}: cut from them, this episode can never give the text. If you have ${languageName(heard)} subtitles, use them as the main subtitles and put these under "Secondary subtitles" below.`,
              )}
            </Note>
          )}
        </Section>
        <Section title={tr("辅助字幕", "Secondary subtitles")} aside={tr("可以不填", "optional")}>
          {!several && (
            <PathInput
              kind="subtitles"
              value={displaySubtitles}
              onChange={setDisplaySubtitles}
              placeholder={tr("辅助字幕文件的路径", "Path to the secondary subtitles")}
              toast={toast}
            />
          )}
          <Note>
            {tr(
              "辅助字幕是另一份你看得懂的字幕，一般是译文。标注时它用浅色小字显示在每句台词下面，帮你听懂角色在说什么。它只给你看：不影响怎么切台词、机器认人，也不会被导出。",
              "Secondary subtitles are another subtitle file you can read, usually a translation. While labeling they are shown in small gray type under each line, so you know what is being said. They are only for you: they change nothing in how lines are cut or who the machine thinks is speaking, and they are not exported.",
            )}
          </Note>
          {several ? (
            <Note>
              {tr(
                "加多集时，在上面填它们所在的文件夹。",
                "When adding several episodes, give their folder above.",
              )}
            </Note>
          ) : (
            <DisplayNote path={displaySubtitles} spoken={heard} />
          )}
        </Section>
        <Section
          title={tr("字幕偏移（秒）", "Subtitle offset (seconds)")}
          aside={tr(
            "空着就自动测（要 Hugging Face 令牌）",
            "leave it empty to measure it (needs a Hugging Face token)",
          )}
        >
          <Input
            className="max-w-[120px]"
            value={offset}
            onChange={(e) => setOffset(e.target.value)}
            placeholder={tr("自动测", "Auto-measure")}
          />
          <Note>
            {several
              ? tr(
                  "字幕时间要加几秒才和声音对上。空着的话每集各测各的：同一片源、同一字幕组的集也可能差半秒以上。填了的话每集都用这个值。",
                  "How many seconds to add to the subtitle times so they line up with the sound. Left empty, each episode is measured on its own: episodes from the same source and subtitle group can differ by half a second or more. Filled in, every episode uses this value.",
                )
              : last
                ? tr(
                    "字幕时间要加几秒才和声音对上。同一片源、同一字幕组的每一集都一样，所以默认填上一集的值。换了片源或字幕组的话，清空让它重新测。",
                    "How many seconds to add to the subtitle times so they line up with the sound. It is the same for every episode from the same source and subtitle group, so the last episode's value is filled in. For another source or subtitle group, empty it to measure again.",
                  )
                : tr(
                    "字幕时间要加几秒才和声音对上。测出来的值，之后同一片源、同一字幕组的集会默认填上。",
                    "How many seconds to add to the subtitle times so they line up with the sound. Later episodes from the same source and subtitle group get the measured value filled in.",
                  )}
          </Note>
          {noToken && !offset.trim() && (
            <Note warn>
              {tr(
                "这台机器没有 Hugging Face 令牌，测不了：照上面的步骤弄好，或者在这里填上偏移。",
                "This machine has no Hugging Face token, so it cannot be measured: follow the steps above, or type the offset here.",
              )}{" "}
              <button
                type="button"
                className="text-primary underline underline-offset-2"
                onClick={() =>
                  document.getElementById(MACHINE)?.scrollIntoView({ behavior: "smooth" })
                }
              >
                {tr("看步骤", "See the steps")}
              </button>
            </Note>
          )}
        </Section>
        {!several && (
          <Section title={tr("集名", "Episode name")} aside={tr("可以不填", "optional")}>
            <Input
              className="max-w-[240px]"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tr(`自动：${nextName}`, `Automatic: ${nextName}`)}
            />
            {badName ? (
              <Note warn>
                {tr(
                  "只能用英文字母、数字、下划线和连字符，开头要是字母或数字。",
                  "Use only English letters, digits, underscores and hyphens, starting with a letter or digit.",
                )}
              </Note>
            ) : takenName ? (
              <Note warn>{tr("已经有一集叫这个名字", "An episode already has this name")}</Note>
            ) : (
              <Note>
                {tr(
                  "列表里和导出文件名里用这个名字。一个工作区放几部动画或几季时，起成 usagi-s1-ep01 这样好分。",
                  "Shown in the list and used in exported file names. When one workspace holds several anime or seasons, a name like usagi-s1-ep01 keeps them apart.",
                )}
              </Note>
            )}
          </Section>
        )}
        <Note>
          {withKeys(
            tr(
              "按「浏览…」选文件，或者把整段路径粘贴进框里。Windows 上按住 [Shift] 右键文件，选「复制文件地址」。",
              'Press "Browse…" to pick each file, or paste its full path into the box. On Windows, hold [Shift], right-click the file, and choose "Copy as path".',
            ),
          )}
        </Note>
        <div>
          <Button
            type="submit"
            disabled={
              busy ||
              wrongLanguage ||
              (!!found?.styles && chosen.size === 0) ||
              (several
                ? ticked.length === 0
                : running || !video.trim() || !subtitles.trim() || badName || takenName)
            }
          >
            {several
              ? running
                ? tr(
                    `排到后面，再加 ${ticked.length} 集`,
                    `Queue ${many(ticked.length, "more episode")}`,
                  )
                : tr(`开始，加 ${ticked.length} 集`, `Start, ${many(ticked.length, "episode")}`)
              : tr("开始", "Start")}
          </Button>
        </div>
        <Note>
          {tr("也可以在命令行里加：", "You can also add one in a terminal:")}
          <AddCommand workspace={state.workspace} />
        </Note>
      </form>
    </div>
  );
}

export function AddDialog({ onClose, ...props }: AddEpisodeProps & { onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-[680px]">
        <DialogHeader>
          <DialogTitle>{tr("加一集", "Add an episode")}</DialogTitle>
        </DialogHeader>
        <AddEpisode {...props} />
      </DialogContent>
    </Dialog>
  );
}
