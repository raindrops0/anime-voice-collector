import { cn } from "cn";
import { useEffect, useRef, useState, type RefObject, type SyntheticEvent } from "react";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import { media, mediaProblem, type Clip, type Roles } from "../api";
import {
  IGNORED,
  ignoredTip,
  lowHintTip,
  lowTip,
  newTip,
  noVoiceprintTip,
  OTHER,
  type LabelText,
} from "../clips";
import { pct, stamp } from "../format";
import { tr } from "../language";
import { needsText } from "../purpose";
import { CONTEXTS, playLog, SPEEDS, type Player, type Sound } from "../playback";
import { EpisodePlayer } from "./EpisodePlayer";
import { Avatar } from "./Avatar";
import { Chip, LowButton } from "./Chip";
import { Choice } from "./Choice";
import { NoText, Tag } from "./Pills";
import { RoleName } from "./RoleName";
import { withKeys } from "./Keys";
import { Tip } from "./Tip";

/* @container: parts inside can follow the stage's own width, which the divider changes. */
const STAGE = "@container overflow-y-auto bg-background p-4";
/* The picture's frame is always dark, in both themes. */
const SCREEN = "relative aspect-video overflow-hidden rounded-lg bg-neutral-950";
/* A message or the spinner in the middle of the screen. */
const WAIT = "absolute inset-0 grid place-items-center text-xs text-neutral-400";
/* The small heading above the choices. */
const ASK = "mt-[18px] mb-2 text-xs tracking-[0.3px] text-muted-foreground";
/* A note above the choices when the voice may be someone new. */
const STRANGER = "mb-2 rounded-lg px-2.5 py-[7px] text-xs leading-[1.7]";

/* The text that export writes for this line, in the language spoken, when it differs from the main subtitles
   shown above. For a target character's line that cannot be exported with text, the same short pill as in the
   lists (the reason is in its hint) and whatever spoken text was found. Nothing when only the sound is collected
   (see purpose.ts). */
function SpokenLine({ clip }: { clip: Clip }) {
  if (!needsText()) return null;
  if (clip.role && clip.spoken_problem)
    return (
      <div className="mx-0.5 mb-1 flex flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground">
        <NoText problem={clip.spoken_problem} />
        {clip.spoken}
      </div>
    );
  if (!clip.spoken || clip.spoken === clip.text) return null;
  return (
    <Tip
      text={tr(
        "导出时写的文字，用说话的语言",
        "The text written on export, in the language spoken",
      )}
    >
      <div className="mx-0.5 mb-1 text-[15px] leading-normal text-muted-foreground">
        {clip.spoken}
      </div>
    </Tip>
  );
}

interface StageProps {
  clip: Clip | null;
  roles: Roles;
  labelText: LabelText;
  sound: Sound;
  setSound: (sound: Sound) => void;
  speed: number;
  setSpeed: (speed: number) => void;
  onAssign: (name: string, low?: boolean) => void;
  onAccept: () => void;
  onPlayRef: (name: string) => void;
  hasVideo: boolean;
  /* The line's episode has its whole copy ready (see EpisodePlayer); until then each line plays its own cut. */
  whole: boolean;
  /* The player on the stage, for replaying, pausing and cropping an avatar. */
  playerRef: RefObject<Player | null>;
  /* The line has played to its end. */
  onEnded: () => void;
  onAvatar: (name: string) => void;
  onNewRole: () => void;
  onClear: () => void;
  context: number;
  setContext: (context: number) => void;
  /* Seconds of picture before and after the line, with the vocals muted there (see Summary.picture_pad). */
  pad: number;
  dock: string[];
  /* Targets the machine does not guess yet, and how many confirmed lines it waits for. */
  waiting: Record<string, { lines: number; others: number }>;
  minLabels: number;
}

/* ───────────── Stage: picture, line, who is it ───────────── */

export function Stage({
  clip,
  roles,
  labelText,
  sound,
  setSound,
  speed,
  setSpeed,
  onAssign,
  onAccept,
  onPlayRef,
  hasVideo,
  whole,
  playerRef,
  onEnded,
  onAvatar,
  onNewRole,
  onClear,
  context,
  setContext,
  pad,
  dock,
  waiting,
  minLabels,
}: StageProps) {
  /* Targets not guessed yet, in dock order; those short of lines; and whether any has no "Not a target" to compare with. */
  const waits = dock.filter((n) => waiting[n]);
  const few = waits.filter((n) => waiting[n].lines < minLabels);
  const lonely = waits.some((n) => !waiting[n].others);
  const line = `${clip?.id}-${sound}-${context}`;
  /* How many times "Cut again" was pressed on this line. Only this line asks for a fresh cut. */
  const [retry, setRetry] = useState<{ for: string; times: number } | null>(null);
  const fresh = retry?.for === line ? retry.times : 0;
  const shown = `${line}-${fresh}`;
  /* Which player can play, named by what it plays. "Loading" is worked out from it while drawing. It used to be
     switched on when the line changed, but a clip already cut could be ready before that ran, and then the
     spinner covered the picture for good. `problem` is set when a player failed: "" until the reason comes back
     from the server. */
  const [status, setStatus] = useState<{ for: string; problem?: string } | null>(null);
  const problem = status?.for === shown ? status.problem : undefined;
  const loading = status?.for !== shown;
  const ready = () =>
    setStatus((s) => (s?.for === shown && s.problem !== undefined ? s : { for: shown }));
  const fail = (kind: "video" | "audio") => {
    const at = shown;
    setStatus({ for: at, problem: "" });
    mediaProblem(media(kind, clip!.id, context))
      .catch(() => null)
      .then((reason) =>
        setStatus((s) =>
          s?.for === at
            ? {
                for: at,
                problem:
                  reason ??
                  tr(
                    "切好的文件坏了，浏览器放不了",
                    "The cut file is broken, so the browser cannot play it",
                  ),
              }
            : s,
        ),
      );
  };
  /* Which line's player is playing, so a new line starts out shown as paused. */
  const [playingFor, setPlayingFor] = useState<string | null>(null);
  const playing = playingFor === shown;
  /* The number key of each of the first 9 characters in the bottom bar; Shift + it is that character, low quality. */
  const slot = (name: string) => {
    const i = dock.indexOf(name);
    return i >= 0 && i < 9 ? i + 1 : null;
  };
  /* Episodes whose copy would not play here; they go back to one cut per line. */
  const [broken, setBroken] = useState<string[]>([]);
  /* Whether this line plays from the episode's copy is settled when the line opens: the copy can become ready
     while a line plays, and switching then would start the line over. */
  const wholeNow = !!clip && whole && !broken.includes(clip.episode);
  const [mode, setMode] = useState<{ for: string; whole: boolean } | null>(null);
  if (clip && mode?.for !== line) setMode({ for: line, whole: wholeNow });
  const fromCopy = mode?.for === line ? mode.whole && wholeNow : wholeNow;
  /* The cut's player: the video, or the vocals when there is no video. */
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  /* Starts the vocals when the picture reaches the line (see `follow`). */
  const voiceTimer = useRef(0);
  useEffect(() => () => clearTimeout(voiceTimer.current), [shown]);
  /* On a new clip the player resets its speed to defaultPlaybackRate, so set both. */
  useEffect(() => {
    for (const el of [mediaRef.current, audioRef.current]) {
      if (el) {
        el.defaultPlaybackRate = speed;
        el.playbackRate = speed;
      }
    }
  }, [speed, shown]);
  useEffect(() => {
    if (fromCopy) return;
    playerRef.current = {
      replay: () => {
        const p = mediaRef.current;
        if (!p) return;
        p.currentTime = 0;
        p.play().catch(() => {});
      },
      pause: () => mediaRef.current?.pause(),
      frame: () => (mediaRef.current instanceof HTMLVideoElement ? mediaRef.current : null),
    };
  }, [fromCopy, playerRef]);

  if (!clip) {
    return (
      <aside className={STAGE}>
        <div className={SCREEN}>
          <div className={WAIT}>{tr("在右边选一句台词", "Pick a line on the right")}</div>
        </div>
      </aside>
    );
  }
  const vocals = hasVideo && sound === "vocals";
  /* With vocals only, the picture plays muted and the separated vocals play instead, following the picture's
     play, pause and seek. The vocals' cut is the line itself; the picture's starts `lead` seconds earlier (`pad`,
     or less at the episode's very start), so the vocals wait that long and end that much before the picture. */
  const lead = Math.max(0, clip.start - context) - Math.max(0, clip.start - context - pad);
  const follow = (e: SyntheticEvent<HTMLVideoElement>) => {
    const voice = audioRef.current;
    clearTimeout(voiceTimer.current);
    if (!vocals || !voice) return;
    const picture = e.currentTarget;
    const at = picture.currentTime - lead;
    if (picture.paused || at >= voice.duration) {
      voice.pause();
      return;
    }
    const start = () => {
      voice.currentTime = Math.max(0, picture.currentTime - lead);
      playLog("sound on", picture.currentTime, lead);
      voice.play().catch(() => {});
    };
    if (at >= 0) start();
    else {
      voice.pause();
      voiceTimer.current = window.setTimeout(start, (-at / picture.playbackRate) * 1000);
    }
  };
  const isOther = !!clip.label && !!labelText[clip.label];
  const label = clip.label;
  return (
    <aside className={STAGE}>
      <div className={SCREEN}>
        {fromCopy ? (
          <>
            {!hasVideo && (
              <div className={WAIT}>
                {tr("这一集没有视频，只有人声", "This episode has no video, only vocals")}
              </div>
            )}
            <EpisodePlayer
              clip={clip}
              hasVideo={hasVideo}
              sound={sound}
              context={context}
              pad={pad}
              speed={speed}
              playerRef={playerRef}
              onEnded={onEnded}
              onReady={ready}
              onFail={() => setBroken((b) => [...b, clip.episode])}
              onPlaying={(on) => setPlayingFor(on ? shown : null)}
            />
          </>
        ) : hasVideo ? (
          <>
            <video
              ref={(el) => {
                mediaRef.current = el;
              }}
              key={shown}
              className="block size-full cursor-pointer object-contain"
              src={media("video", clip.id, context, fresh)}
              autoPlay
              playsInline
              muted={vocals}
              onCanPlay={ready}
              onError={() => fail("video")}
              onClick={(e) => {
                if (e.currentTarget.paused) e.currentTarget.play().catch(() => {});
                else e.currentTarget.pause();
              }}
              onPlay={(e) => {
                setPlayingFor(shown);
                follow(e);
              }}
              onPause={(e) => {
                setPlayingFor(null);
                follow(e);
              }}
              onSeeked={follow}
              onEnded={onEnded}
            ></video>
            {vocals && (
              <audio
                ref={audioRef}
                key={`v-${shown}`}
                src={media("audio", clip.id, context, fresh)}
                preload="auto"
                onError={() => fail("audio")}
              ></audio>
            )}
          </>
        ) : (
          <>
            <div className={WAIT}>
              {tr("这一集没有视频，只有人声", "This episode has no video, only vocals")}
            </div>
            <audio
              ref={(el) => {
                audioRef.current = el;
                mediaRef.current = el;
              }}
              key={shown}
              src={media("audio", clip.id, context, fresh)}
              autoPlay
              onCanPlay={ready}
              onError={() => fail("audio")}
              onEnded={onEnded}
            ></audio>
          </>
        )}
        {/* Paused: a see-through triangle. Playing: the two bars. In the bottom right corner, so it does not
            cover the speaker's face. Clicks go through to the video. */}
        {hasVideo && !loading && problem === undefined && (
          <div
            className="pointer-events-none absolute right-2 bottom-2"
            data-playing={playing || undefined}
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 24 24"
              className="block size-7 rounded-full bg-black/40 fill-white/85 p-[5px]"
            >
              {playing ? (
                <>
                  <rect x="6" y="5" width="4" height="14" rx="1" />
                  <rect x="14" y="5" width="4" height="14" rx="1" />
                </>
              ) : (
                <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" />
              )}
            </svg>
          </div>
        )}
        <div className={cn(WAIT, (!hasVideo || !loading) && "hidden")}>
          <Spinner className="size-[22px] text-neutral-300" />
        </div>
        {problem !== undefined && (
          <div className={cn(WAIT, "bg-black/75 text-center text-[13px] text-neutral-300")}>
            <div>
              <div>{tr("这一句放不了", "This line cannot play")}</div>
              <div className="mx-4 mt-1 mb-2.5 text-xs text-neutral-500">
                {problem || tr("正在查原因…", "Finding out why…")}
              </div>
              <Tip
                text={tr(
                  "丢掉存好的片段，从原视频重新切",
                  "Throw away the saved clip and cut it again from the original",
                )}
              >
                {/* The screen is always dark, so its button is too, in both themes. */}
                <Button
                  variant="outline"
                  className="border-neutral-600 bg-neutral-800 text-neutral-100 hover:bg-neutral-700 hover:text-neutral-100 dark:border-neutral-600 dark:bg-neutral-800 dark:hover:bg-neutral-700"
                  onClick={() => setRetry({ for: line, times: fresh + 1 })}
                >
                  {tr("重新切一次", "Cut again")}
                </Button>
              </Tip>
            </div>
          </div>
        )}
      </div>
      {/* The row just below the picture controls which sound is played and how fast. */}
      <div className="mt-2 flex flex-wrap justify-between gap-2">
        {hasVideo && (
          <Choice
            small
            value={sound}
            options={[
              ["vocals", tr("只听人声", "Vocals only")],
              ["original", tr("画面原声", "Original sound")],
            ]}
            onPick={setSound}
          />
        )}
        <Tip
          text={tr(
            "播放速度，点一下就用这个速度从头放；参考音也一样快",
            "Playback speed: a click plays the line again from the start at that speed. Reference clips use it too",
          )}
        >
          <span>
            {/* A cut's players get the new speed here, so the replay starts at it; the episode's copy first moves
                to the line's start, and gets it from its own effect meanwhile. */}
            <Choice
              small
              again
              value={speed}
              options={SPEEDS.map((s) => [s, `${s}×`] as const)}
              onPick={(s) => {
                for (const el of [mediaRef.current, audioRef.current]) {
                  if (el) {
                    el.defaultPlaybackRate = s;
                    el.playbackRate = s;
                  }
                }
                setSpeed(s);
                playerRef.current?.replay();
              }}
            />
          </span>
        </Tip>
      </div>
      <div className="mx-0.5 mt-2.5 mb-1 min-h-7 text-[19px] leading-normal">
        {clip.text || (
          <span className="text-muted-foreground">
            {tr("（字幕里没有这句的文字）", "(no text for this line in the subtitles)")}
          </span>
        )}
      </div>
      {clip.display && clip.display !== clip.text && (
        <Tip text={tr("辅助字幕", "Secondary subtitles")}>
          <div className="mx-0.5 mb-1 text-[15px] leading-normal text-muted-foreground">
            {clip.display}
          </div>
        </Tip>
      )}
      <SpokenLine clip={clip} />
      <div className="flex flex-wrap items-center gap-2.5 text-xs text-muted-foreground tabular-nums">
        <span>{clip.episode}</span>
        <span>{stamp(clip.start)}</span>
        <span>{tr(`${clip.duration.toFixed(2)} 秒`, `${clip.duration.toFixed(2)} s`)}</span>
        <Tip
          text={tr(
            "看不出是谁时，前后各多放一些。选好的会一直用到你改回来",
            "When you can't tell who it is, play more on each side. Your choice stays until you change it",
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            {tr("多放前后文", "More context")}
            <Choice
              small
              value={context}
              options={CONTEXTS.map(
                (c) => [c, c ? tr(`±${c} 秒`, `±${c} s`) : tr("不多放", "None")] as const,
              )}
              onPick={setContext}
            />
            <Kbd>L</Kbd>
          </span>
        </Tip>
      </div>

      {label ? (
        <>
          <div className={ASK}>
            {label === IGNORED ? tr("已经忽略", "Ignored") : tr("已经确认", "Confirmed")}
          </div>
          <div
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-2.5",
              label === IGNORED ? "bg-muted text-muted-foreground" : "bg-success/10 text-success",
            )}
          >
            <Avatar
              role={roles[label]}
              name={label}
              blank={isOther}
              ignored={label === IGNORED}
              size="lg"
              onClick={!isOther && hasVideo ? () => onAvatar(label) : null}
              title={tr("从画面里截一块当头像", "Crop an avatar from the picture")}
            />
            {/* The name and "Clear label" share the top row, so the note below gets the full width. */}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                <div className="font-semibold text-foreground">
                  {isOther ? labelText[label] : <RoleName role={roles[label]} name={label} />}
                  {clip.unusable && !labelText[label] && (
                    <>
                      {" "}
                      <Tag look="unusable" tip={lowTip()}>
                        {tr("质量低", "Low quality")}
                      </Tag>
                    </>
                  )}
                </div>
                <Tip
                  text={tr(
                    "清掉这句的标签，回到机器的猜测",
                    "Clear this line's label and go back to the machine's guess",
                  )}
                >
                  <Button variant="ghost" size="sm" className="-mr-1.5 text-xs" onClick={onClear}>
                    {tr("清掉标签", "Clear label")} <Kbd>Backspace</Kbd>
                  </Button>
                </Tip>
              </div>
              <div className="mt-0.5 text-xs">
                {withKeys(
                  tr(
                    "要改的话，直接按别的数字键或在下面选；[Shift] + 数字是质量低",
                    "To change it, press another number key or pick below. [Shift] + number means low quality",
                  ),
                )}
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className={ASK}>
            {clip.guess.length ? (
              tr("这是谁？机器的猜测概率", "Who is this? The machine's guessed probabilities")
            ) : clip.voiced ? (
              tr("这是谁？", "Who is this?")
            ) : (
              <Tip text={noVoiceprintTip()}>
                <span>
                  {tr(
                    "这句太短，机器认不出是谁，请直接选人",
                    "This line is too short for the machine to tell who it is. Pick the character yourself",
                  )}
                </span>
              </Tip>
            )}
          </div>
          {clip.familiar === false && (
            <div className={cn(STRANGER, "bg-warning/15 text-warning")}>
              {tr(
                <>
                  跟已经确认过的角色都不太像，可能是还没标过的人。是你要收集的人就按 <Kbd>N</Kbd>{" "}
                  新建目标，名字以后再起也行；不是就按 <Kbd>Q</Kbd>。
                </>,
                <>
                  Not much like any confirmed character, so it may be someone not labeled yet. If
                  you want to collect them, press <Kbd>N</Kbd> for a new target and name it later;
                  if not, press <Kbd>Q</Kbd>.
                </>,
              )}
            </div>
          )}
          {clip.low != null && (
            <Tip text={lowHintTip(clip.low)}>
              <div
                className={cn(STRANGER, "border border-dashed border-destructive text-destructive")}
              >
                {tr(
                  <>
                    机器估计这句有 {pct(clip.low)}{" "}
                    的可能质量低，所以放进了「可能质量低」，不算要处理的。听着确实是的话，
                    目标角色按 <Kbd>Shift</Kbd> + 数字标「质量低」。
                  </>,
                  <>
                    The machine puts the chance of low quality at {pct(clip.low)}, so the line is
                    listed under Maybe low quality, not work to do. If it does sound that way, mark
                    a target character "Low quality" with <Kbd>Shift</Kbd> + number.
                  </>,
                )}
              </div>
            </Tip>
          )}
          {/* Targets the machine does not guess yet: too few of their lines confirmed, or no "Not a target" to compare with. */}
          {clip.voiced && !clip.label && waits.length > 0 && (
            <div className={cn(STRANGER, "border bg-muted text-muted-foreground")}>
              {tr(
                <>
                  机器还没开始猜 {waits.join("、")}。
                  {few.length > 0 &&
                    `一个角色确认满 ${minLabels} 句后才开始猜，现在${few.map((n) => `${n} 已确认 ${waiting[n].lines} 句`).join("，")}。`}
                  {lonely && (
                    <>
                      它还得先听过别人的声音：不是你要收集的人，按 <Kbd>Q</Kbd> 标「不是目标」。
                    </>
                  )}
                </>,
                <>
                  The machine is not guessing {waits.join(", ")} yet.{" "}
                  {few.length > 0 &&
                    `It starts once ${minLabels} lines of a character are confirmed; so far ${few.map((n) => `${n} has ${waiting[n].lines}`).join(", ")}. `}
                  {lonely && (
                    <>
                      It also needs to hear other people first: label people you don't want to
                      collect "Not a target" with <Kbd>Q</Kbd>.
                    </>
                  )}
                </>,
              )}
            </div>
          )}
          {clip.familiar === null && clip.guess.length > 0 && (
            <div className={cn(STRANGER, "border bg-muted text-muted-foreground")}>
              {tr(
                <>
                  机器现在只会在底部这几个角色里挑。都不是的话，要收集的人按 <Kbd>N</Kbd>{" "}
                  新建，别人按 <Kbd>Q</Kbd> 标「不是目标」；确认满 20
                  句后，它会自己提醒你哪句像新面孔。
                </>,
                <>
                  For now the machine only picks among the characters at the bottom. If it is none
                  of them, press <Kbd>N</Kbd> for someone you want to collect, or <Kbd>Q</Kbd> for
                  "Not a target". After 20 confirmed lines it will point out lines that sound like
                  someone new.
                </>,
              )}
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            {clip.guess
              .filter((g) => g.p >= 0.02 || g === clip.guess[0])
              .map((g, i) => {
                const k = slot(g.name);
                return (
                  <div
                    key={g.name}
                    className={cn(
                      "grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-x-2.5 gap-y-1 rounded-lg border bg-background px-2.5 py-2 text-left transition-[border-color,box-shadow] hover:border-primary hover:shadow-md",
                      i === 0 && "border-primary/40 bg-accent",
                    )}
                    onClick={() => onAssign(g.name)}
                  >
                    {/* The avatar takes two rows. The probability bar has its own row, running from under the
                        name to the far right, so it does not compete with the buttons for width. */}
                    <div className="row-span-2 @max-sm:row-span-3">
                      <Avatar
                        role={roles[g.name]}
                        name={g.name}
                        blank={g.name === OTHER}
                        size="md"
                      />
                    </div>
                    <div className="truncate font-[560]">
                      {g.name === OTHER ? (
                        labelText[OTHER]
                      ) : (
                        <RoleName role={roles[g.name]} name={g.name} />
                      )}
                    </div>
                    {/* When the stage is narrow, the two buttons move to a line of their own under the
                        name, so the name keeps its room and the row never gets wider than the stage. */}
                    {g.name !== OTHER && (
                      <div className="flex justify-end gap-1.5 @max-sm:col-[2/-1] @max-sm:row-start-2 @max-sm:justify-start">
                        <Tip
                          text={tr(
                            "听这个角色确认过的一句",
                            "Hear a confirmed line of this character",
                          )}
                        >
                          <Button
                            variant="outline"
                            size="xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              onPlayRef(g.name);
                            }}
                          >
                            {tr("参考音", "Reference")}
                            {i === 0 ? (
                              <>
                                {" "}
                                <Kbd>R</Kbd>
                              </>
                            ) : (
                              ""
                            )}
                          </Button>
                        </Tip>
                        <LowButton
                          hotkey={k ?? undefined}
                          tip={lowTip()}
                          onClick={() => onAssign(g.name, true)}
                        />
                      </div>
                    )}
                    {/* The percentage is fixed in the last column. "Not a target" rows, which have no button, are also
                        pushed right, so the rows line up. */}
                    <span className="col-start-[-2] min-w-[34px] text-right text-xs text-muted-foreground tabular-nums">
                      {pct(g.p)}
                    </span>
                    <div className="col-[2/-1] h-1 overflow-hidden rounded-xs bg-border @max-sm:row-start-3">
                      <i className="block h-full bg-primary" style={{ width: pct(g.p) }}></i>
                    </div>
                  </div>
                );
              })}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {clip.guess.length > 0 && (
              <Button onClick={onAccept}>
                {tr("是", "It's")} {labelText[clip.guess[0].name] || clip.guess[0].name}
                <Kbd className="ml-1">Enter</Kbd>
              </Button>
            )}
            {/* The same chip as in the bottom bar and under each group. */}
            <Chip
              small
              tip={newTip()}
              onPick={onNewRole}
              picture={<Avatar plus size="sm" />}
              hotkey="N"
            >
              {tr("新目标", "New target")}
            </Chip>
            <Chip
              small
              tip={ignoredTip()}
              onPick={() => onAssign(IGNORED)}
              picture={<Avatar blank ignored size="sm" />}
              hotkey="X"
            >
              {tr("忽略本条", "Ignore line")}
            </Chip>
          </div>
        </>
      )}

      <div className="mt-4 text-xs leading-[1.9] text-muted-foreground">
        {tr(
          <>
            <Kbd>J</Kbd> <Kbd>K</Kbd> 上下一句 · <Kbd>空格</Kbd> 重播 · 底部角色上标的键直接标 ·{" "}
            <Kbd>?</Kbd> 全部快捷键
          </>,
          <>
            <Kbd>J</Kbd> <Kbd>K</Kbd> next / previous · <Kbd>Space</Kbd> replay · the key on a
            character at the bottom labels the line · <Kbd>?</Kbd> all shortcuts
          </>,
        )}
      </div>
    </aside>
  );
}
