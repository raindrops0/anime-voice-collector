import { cn } from "cn";
import { useEffect, useRef, useState, type RefObject } from "react";
import { episodeMedia, media, type Clip } from "../api";
import { DRIFT, outputLag, playLog, type Player, type Sound } from "../playback";

/* Seconds before the line's start and end at which the sound turns on, is muted or stops: a timer may wake a few
   milliseconds before the sound's clock gets there. */
const EARLY = 0.01;

interface EpisodePlayerProps {
  clip: Clip;
  hasVideo: boolean;
  sound: Sound;
  context: number;
  /* Seconds of picture before and after the line, with the vocals muted there (see Summary.picture_pad). */
  pad: number;
  speed: number;
  playerRef: RefObject<Player | null>;
  /* The line has played to its end. */
  onEnded: () => void;
  /* The line is ready and starts playing. */
  onReady: () => void;
  onFail: () => void;
  onPlaying: (playing: boolean) => void;
}

/* ───────────── Episode player ─────────────
   Plays lines from the episode's whole copy, as a video player does: the files stay loaded while you move from
   line to line in the same episode, and each line is a jump to its start, which is instant since the copy has a
   keyframe every second. The picture and the chosen sound (vocals or the original sound) are two players with
   two clocks, so a line starts only once both have reached its start and can play; then the sound starts and
   the picture follows. The sound leads: it is never moved while playing, since a jump in the sound is heard as a click. The
   muted picture follows it: it pauses while the sound waits for data, and is moved to the sound when they get
   more than DRIFT apart. With no video, the vocals play alone. Each line stops at its end, as a cut would. */
export function EpisodePlayer({
  clip,
  hasVideo,
  sound,
  context,
  pad,
  speed,
  playerRef,
  onEnded,
  onReady,
  onFail,
  onPlaying,
}: EpisodePlayerProps) {
  const video = useRef<HTMLVideoElement | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const track = hasVideo ? sound : "vocals";
  /* As the cuts do: the line itself, with the extra context when there is some, and `pad` more picture at each
     end. The vocals are heard only within the line; the original sound plays all of it. */
  const heardFrom = Math.max(0, clip.start - context);
  const heardTo = clip.end + context;
  const extra = hasVideo ? pad : 0;
  const from = Math.max(0, heardFrom - extra);
  const to = heardTo + extra;
  const muteOutside = extra > 0 && track === "vocals";
  /* The vocals come from the line's own cut, which the server makes in a few hundredths of a second: it holds
     exactly the line (with any extra context), so nothing before or after it is heard, however late the speakers
     are, and it ends by itself. The picture still comes from the copy and follows it. With the padded picture the
     vocals play through the pad muted, so then they come from the copy. `shift` is the episode time of the
     sound's start. */
  const ownCut = track === "vocals" && extra === 0;
  const shift = ownCut ? heardFrom : 0;
  const soundKey = ownCut ? `${clip.id}-${context}` : `${clip.episode}-${track}`;
  /* What the event handlers below read: the line now, and whether both players should start once there. */
  const now = useRef({
    from,
    to,
    heardFrom,
    heardTo,
    muteOutside,
    ownCut,
    shift,
    onEnded,
    onReady,
    onPlaying,
  });
  const startWhenThere = useRef(false);
  /* The players already sent to the line's start; a player made anew (another sound) is sent again. */
  const moved = useRef(new WeakSet<HTMLMediaElement>());
  const picture = () => (hasVideo ? video.current : null);
  /* The moment of sound going to the speakers now: ahead of the time heard by the output's lag (see outputLag),
     so stopping and muting by it take effect when the line's end is heard, not that lag later. */
  const sent = (a: HTMLMediaElement) =>
    a.currentTime + now.current.shift + outputLag() * a.playbackRate;
  /* Whether the sound at this time is heard: always, unless the vocals are muted outside the line. */
  const heard = (t: number) => {
    const n = now.current;
    return !n.muteOutside || (t >= n.heardFrom - EARLY && t < n.heardTo - EARLY);
  };

  /* Move both players to the line's start if they are not there yet, and start the sound once both can play; the
     picture starts when the sound does (follow, below). If the browser does not let the sound play, as Chrome
     does on a page just loaded that has not been clicked, the picture stays still too. Called again by each
     player's events until it starts. Before a file's length is known it cannot be moved, so each player is moved
     as soon as its own length is known: a new episode's picture used to wait for the sound and showed the
     episode's first frame for about a second. */
  const tryStart = () => {
    if (!startWhenThere.current) return;
    const a = audio.current;
    const v = picture();
    const players = v ? [a, v] : [a];
    let there = true;
    for (const m of players) {
      if (!m || m.readyState < HTMLMediaElement.HAVE_METADATA) {
        there = false;
        continue;
      }
      if (!moved.current.has(m)) {
        moved.current.add(m);
        m.currentTime = now.current.from - (m === a ? now.current.shift : 0);
      }
      if (m.seeking || m.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) there = false;
    }
    if (!there || !a) return;
    startWhenThere.current = false;
    a.muted = !heard(a.currentTime + now.current.shift);
    playLog(
      a.muted ? "start, muted," : "start",
      a.currentTime + now.current.shift,
      now.current.from,
    );
    now.current.onReady();
    a.play().catch(() => {});
  };

  const jump = () => {
    audio.current?.pause();
    picture()?.pause();
    startWhenThere.current = true;
    moved.current = new WeakSet();
    tryStart();
  };

  useEffect(() => {
    now.current = {
      from,
      to,
      heardFrom,
      heardTo,
      muteOutside,
      ownCut,
      shift,
      onEnded,
      onReady,
      onPlaying,
    };
  });

  /* A new line, more context or another sound: go to the line's start and play it. */
  useEffect(() => {
    jump();
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when the line itself changes
  }, [clip.id, context, track, pad]);

  /* Another episode or sound makes new players, which start at normal speed; so does each line's own cut. A sound
     slower than the picture makes the picture run ahead and be pulled back again and again. */
  useEffect(() => {
    for (const el of [video.current, audio.current]) {
      if (el) {
        el.defaultPlaybackRate = speed;
        el.playbackRate = speed;
      }
    }
  }, [speed, soundKey, clip.episode]);

  useEffect(() => {
    playerRef.current = {
      replay: jump,
      pause: () => audio.current?.pause(),
      frame: () => (hasVideo ? video.current : null),
    };
    return () => {
      playerRef.current = null;
    };
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- jump only reads refs
  }, [playerRef, hasVideo]);

  /* While playing: stop at the line's end, mute the vocals outside the line, and bring the picture back to the
     sound when it drifts. Checked on every frame drawn; at each of those moments, by a timer (see `plan`); and on
     the sound's own time updates, which keep coming when the page is in the background and neither frames nor
     timers run on time. */
  const check = () => {
    const a = audio.current;
    if (!a || a.paused) return;
    const n = now.current;
    const t = sent(a);
    /* The line's own cut ends by itself, exactly at the line's end. */
    if (!n.ownCut && t >= n.to - EARLY) {
      a.pause();
      playLog(`stop, heard now ${a.currentTime.toFixed(3)}, sent`, t, n.to);
      n.onEnded();
      return;
    }
    const muted = !heard(t);
    if (a.muted !== muted) {
      a.muted = muted;
      playLog(muted ? "muted" : "sound on", t, muted ? n.heardTo : n.heardFrom);
    }
    const v = picture();
    const at = a.currentTime + n.shift;
    if (v && !v.seeking && Math.abs(v.currentTime - at) > DRIFT) v.currentTime = at;
  };
  const checkNow = useRef(check);
  useEffect(() => {
    checkNow.current = check;
  });
  /* A frame comes only every 16 ms or so, and a time update every quarter second, so a timer is set for the next
     moment the sound turns on, is muted or stops. Set again whenever the sound starts, moves or changes speed,
     and by the timer itself: the sound's clock can start late or run behind the timer (once a mute came 0.29
     seconds late), so a timer that wakes too early waits again for what is left. */
  const timer = useRef(0);
  const plan = () => {
    clearTimeout(timer.current);
    const a = audio.current;
    if (!a || a.paused) return;
    const n = now.current;
    if (n.ownCut) return;
    const t = sent(a);
    const moments = n.muteOutside ? [n.heardFrom, n.heardTo, n.to] : [n.to];
    const next = moments.find((m) => m - EARLY > t);
    if (next === undefined) return;
    const wait = ((next - EARLY - t) / a.playbackRate) * 1000;
    if (wait > 0)
      timer.current = window.setTimeout(() => {
        checkNow.current();
        plan();
      }, wait);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    let frame = 0;
    const watch = () => {
      checkNow.current();
      frame = requestAnimationFrame(watch);
    };
    frame = requestAnimationFrame(watch);
    return () => cancelAnimationFrame(frame);
  }, []);

  /* The picture follows the sound's play and pause. While the sound waits for data it holds still. */
  const follow = () => {
    const a = audio.current;
    const v = picture();
    if (!a || !v || startWhenThere.current) return;
    if (a.paused) v.pause();
    else v.play().catch(() => {});
  };
  const loading = {
    onLoadedMetadata: tryStart,
    onSeeked: tryStart,
    onCanPlay: tryStart,
    onError: onFail,
  };
  /* Clicking the picture pauses or plays; after the line's end, or away from it, it plays the line again. */
  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    const at = a.currentTime + shift;
    if (!a.paused) a.pause();
    else if (a.ended || at >= to - 0.05 || at < from - 0.5) jump();
    else a.play().catch(() => {});
  };
  const sounds = (
    <audio
      ref={audio}
      key={soundKey}
      src={ownCut ? media("audio", clip.id, context) : episodeMedia(clip.episode, track)}
      preload="auto"
      {...loading}
      onTimeUpdate={check}
      onPlay={() => {
        follow();
        plan();
        now.current.onPlaying(true);
      }}
      onPause={() => {
        follow();
        plan();
        now.current.onPlaying(false);
      }}
      onSeeked={() => {
        plan();
        tryStart();
      }}
      onRateChange={plan}
      /* The line's own cut ends here. So may the copy, when the last line of an episode reaches past the file's
         end (with more context, or the padded picture): that is the line's end too. */
      onEnded={() => {
        playLog("file end", (audio.current?.currentTime ?? 0) + now.current.shift, now.current.to);
        now.current.onEnded();
      }}
      onWaiting={() => picture()?.pause()}
      onPlaying={() => {
        follow();
        plan();
      }}
    ></audio>
  );
  /* A new episode's picture stays hidden until it has first been moved to a line, so its first frame is not shown. */
  const [placedIn, setPlacedIn] = useState<string | null>(null);
  return hasVideo ? (
    <>
      <video
        ref={video}
        key={clip.episode}
        className={cn(
          "block size-full cursor-pointer object-contain",
          placedIn !== clip.episode && "invisible",
        )}
        src={episodeMedia(clip.episode, "video")}
        preload="auto"
        playsInline
        muted
        onClick={toggle}
        {...loading}
        onSeeked={() => {
          setPlacedIn(clip.episode);
          tryStart();
        }}
      ></video>
      {sounds}
    </>
  ) : (
    sounds
  );
}
