/* Playback speeds to choose from. The choice is kept on this machine. */
export const SPEEDS = [1, 1.25, 1.5, 2];

/* More context: none, 5 more seconds on each side, 15. L steps through them. Matches CONTEXT_SECONDS on the
   server. */
export const CONTEXTS = [0, 5, 15];

/* What plays with the picture: the separated vocals, or the picture's own sound. */
export type Sound = "vocals" | "original";

/* What the rest of the page may do with the stage's player, whether it plays one cut per line or the whole
   episode's copy. */
export interface Player {
  /* Play the line again from its start. */
  replay: () => void;
  pause: () => void;
  /* The picture, to crop an avatar from; null when the episode has no video. */
  frame: () => HTMLVideoElement | null;
}

/* How far the picture may drift from the sound before it is moved to the sound. At double speed the sound's
   reported time trails the picture by about 0.2 seconds, so the bar sits above that. */
export const DRIFT = 0.3;

/* How long after the browser plays a moment of sound it comes out of the speakers: about 0.07 seconds on a
   desktop, more over Bluetooth. A player's time is the moment heard now, so by then this much more has already
   gone to the speakers, and pausing does not take it back: stopping at a line's end played the start of the next
   person's voice. So the episode player stops and mutes this much early. Measured with a Web Audio context, which
   can start only after the person has clicked or pressed a key; again on every later click or key, in case the
   speakers changed, and kept at 0 when the browser cannot tell. */
let lag = 0;
let measuring: AudioContext | null = null;
export const outputLag = () => lag;
async function measureLag() {
  if (typeof AudioContext === "undefined" || measuring?.state === "running") return;
  try {
    measuring ??= new AudioContext();
    await measuring.resume();
    /* The output's latency is known only once its stream runs for a moment. */
    await new Promise((done) => setTimeout(done, 300));
    const seconds = (measuring.baseLatency || 0) + (measuring.outputLatency || 0);
    if (seconds > 0) lag = Math.min(seconds, 0.3);
    await measuring.suspend();
  } catch {
    /* No measure: stop at the line's end as before. */
  }
}
if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", () => void measureLag(), { capture: true });
  window.addEventListener("keydown", () => void measureLag(), { capture: true });
}

/* When the sound starts, is muted and stops, written to the browser's console with the time it aimed for, to
   compare the two ways of playing (PICTURE_PAD in the server's video.py). Turned on in the console with
   localStorage.setItem("avoc-debug-playback", "1"), then a reload; off with removeItem. */
const debugging = (() => {
  try {
    return localStorage.getItem("avoc-debug-playback") === "1";
  } catch {
    return false;
  }
})();
export function playLog(what: string, at: number, aim?: number) {
  if (!debugging) return;
  const off =
    aim === undefined ? "" : ` (aimed ${aim.toFixed(3)}, off by ${(at - aim).toFixed(3)})`;
  console.log(`[playback] ${what} at ${at.toFixed(3)}${off}`);
}
