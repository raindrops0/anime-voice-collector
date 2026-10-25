import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  call,
  media,
  warm,
  type Adding,
  type ChangeResult,
  type Clip,
  type Group,
  type Roles,
  type Summary,
} from "./api";
import {
  DONE_PARTS,
  IGNORED,
  NEEDS_WORK,
  otherName,
  OTHER,
  PARTS,
  partOf,
  pendingOf,
  ROLE_PARTS,
  ROLE_PARTS_FIRST,
  roleOrder,
  rolePartOf,
  type LabelText,
  type Part,
  type RolePart,
  whoOf,
  WORK_PARTS,
} from "./clips";
import { RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import { Cropper } from "./components/Cropper";
import { Divider } from "./components/Divider";
import { Dock } from "./components/Dock";
import { type Flash, LOW_KEY, NEW_KEY, UNDO_KEY } from "./flash";
import { Guide, GUIDE_SEEN } from "./components/Guide";
import { autoText, heldText } from "./held";
import { Help } from "./components/Help";
import { History } from "./components/History";
import { RenameDialog } from "./components/RenameDialog";
import { LanguageButton } from "./components/LanguageButton";
import { withKeys } from "./components/Keys";
import { Empty } from "./components/Notes";
import { Stage } from "./components/Stage";
import { TopBar, type View } from "./components/TopBar";
import { currentLanguage, lines, setLanguage, tr, type Language } from "./language";
import { CONTEXTS, SPEEDS, type Player, type Sound } from "./playback";
import { currentPurpose, setPurpose, type Purpose } from "./purpose";
import { fitStage, savedStageWidth } from "./stageWidth";
import { AddDialog } from "./views/AddEpisode";
import { ExportView } from "./views/ExportView";
import { GroupsView, type KeyedGroup, type Picked } from "./views/GroupsView";
import { RoleView } from "./views/RoleView";
import { SceneView } from "./views/SceneView";
import { Welcome } from "./views/Welcome";

const VIEWS: View[] = ["groups", "scene", "roles", "export"];
/* A list request was overtaken by a later one. Its result is dropped; this is not an error. */
const STALE = new Error("stale");
/* The position saved after # in the address when the page opened; see where App writes it back. */
const saved = new URLSearchParams(location.hash.slice(1));

/* Shortcuts stay off while the keys go into a text box or an open menu. A tick box is not typed into, so they still
   work after ticking a line. */
const typing = (el: EventTarget | null) => {
  if (!(el instanceof HTMLElement)) return false;
  return (
    el.tagName === "SELECT" ||
    el.tagName === "TEXTAREA" ||
    !!el.closest("[role=menu]") ||
    (el instanceof HTMLInputElement && !["checkbox", "radio", "button", "range"].includes(el.type))
  );
};

/* The avatar dialog: whose avatar, what to do after it closes, and for a new character, the name box. */
interface Crop {
  name: string;
  then: (() => void) | null;
  naming?: boolean;
  /* Whether the picture on the stage belongs to the new character's lines. */
  frame?: boolean;
}

/* The lines of the ticked parts of a character's list, in the order it shows them. */
const roleIds = (clips: Clip[], role: string | null, parts: Set<RolePart>) =>
  roleOrder(clips, role)
    .filter((c) => {
      const part = rolePartOf(c, role);
      return !!part && parts.has(part);
    })
    .map((c) => c.id);

/* Whether a line belongs in a character's list by its newest guess, as the server picks them (role_clips): labeled
   as them, listed as maybe missed, or not labeled (or ignored) and given to them by the machine. */
const belongs = (c: Clip, role: string | null) =>
  c.label === role || !!c.maybe || ((!c.label || c.label === IGNORED) && c.guess[0]?.name === role);

/* ───────────── Main ───────────── */

export function App() {
  const [state, setState] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("scene");
  const [episode, setEpisode] = useState<string | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [focus, setFocusState] = useState<string | null>(() => saved.get("clip"));
  /* The newest focus, set at once. Keys pressed faster than the page draws read it, so each press acts on the
     line the press before moved to, not on the one still on screen. */
  const focusNow = useRef(focus);
  const setFocus = useCallback(
    (next: string | null | undefined | ((f: string | null) => string | null | undefined)) => {
      const value = typeof next === "function" ? next(focusNow.current) : next;
      focusNow.current = value ?? null;
      setFocusState(focusNow.current);
    },
    [],
  );
  /* The parts of the episode Scenes shows, see Part; only the lines still to do at first. Kept on this machine. */
  const [parts, setPartsState] = useState<Set<Part>>(() => {
    try {
      const kept = JSON.parse(localStorage.getItem("scene-parts") ?? "null") as unknown;
      if (Array.isArray(kept)) {
        /* "work" and "done" were the kinds of To do and Confirmed before they had boxes of their own. */
        if (kept.includes("work")) kept.push(...WORK_PARTS);
        if (kept.includes("done")) kept.push(...DONE_PARTS);
        /* "machine" was the set-aside lines alone, before the hinted ones joined them as "aside". */
        if (kept.includes("machine")) kept.push("aside");
        return new Set(PARTS.filter((p) => kept.includes(p)));
      }
    } catch {
      /* A broken value starts over. */
    }
    return new Set(WORK_PARTS);
  });
  /* The parts of a character's lines Characters shows, see RolePart. Kept on this machine. */
  const [roleParts, setRoleParts] = useState<Set<RolePart>>(() => {
    try {
      const kept = JSON.parse(localStorage.getItem("role-parts") ?? "null") as unknown;
      if (Array.isArray(kept)) {
        /* "pending" was the two kinds "review" and "auto" before they had boxes of their own. */
        if (kept.includes("pending")) kept.push("review", "auto");
        return new Set(ROLE_PARTS.filter((p) => kept.includes(p)));
      }
    } catch {
      /* A broken value starts over. */
    }
    return new Set(ROLE_PARTS_FIRST);
  });
  /* The ticks now, for picking the first line of a list just fetched without fetching again on every tick. */
  const ticksNow = useRef({ parts, roleParts });
  ticksNow.current = { parts, roleParts };
  /* What F goes back to from "only to do": the parts ticked before, or the whole episode but Skipped. */
  const partsBefore = useRef<Set<Part>>(new Set([...WORK_PARTS, "auto", ...DONE_PARTS]));
  const [role, setRole] = useState<string | null>(null);
  const roleNow = useRef(role);
  roleNow.current = role;
  const viewNow = useRef(view);
  viewNow.current = view;
  const [groups, setGroups] = useState<KeyedGroup[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  /* The ticked lines in Groups, per group. Kept here because the keys label them too. Like focusNow, the newest
     ticks are kept in a ref as well, so a second quick key press doesn't label the same lines again. */
  const [picked, setPickedState] = useState<Picked>({});
  const pickedNow = useRef(picked);
  const setPicked = useCallback((next: Picked | ((p: Picked) => Picked)) => {
    pickedNow.current = typeof next === "function" ? next(pickedNow.current) : next;
    setPickedState(pickedNow.current);
  }, []);
  const [help, setHelp] = useState(false);
  const [flash, setFlash] = useState<Flash>();
  const pulse = (key: string) => setFlash((f) => ({ key, n: (f?.n ?? 0) + 1 }));
  const [guide, setGuide] = useState(false);
  /* The server's job that adds an episode (see AddEpisode), and whether its dialog is open. */
  const [adding, setAdding] = useState<Adding | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sound, setSound] = useState<Sound>(() =>
    localStorage.getItem("sound") === "original" ? "original" : "vocals",
  );
  const [speed, setSpeed] = useState(() => {
    const s = Number(localStorage.getItem("speed"));
    return SPEEDS.includes(s) ? s : 1;
  });
  /* Extra seconds played around each line, see CONTEXTS. The choice is kept on this machine. */
  const [context, setContext] = useState(() => {
    const c = Number(localStorage.getItem("context"));
    return CONTEXTS.includes(c) ? c : 0;
  });
  const nextContext = () =>
    setContext((c) => CONTEXTS[(CONTEXTS.indexOf(c) + 1) % CONTEXTS.length]);
  const [flashes, setFlashes] = useState(() => new Set<string>());
  const [playing, setPlaying] = useState(false);
  const [crop, setCrop] = useState<Crop | null>(null);
  /* The Name / Rename or merge dialog for the open character is showing. */
  const [renaming, setRenaming] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [stageWidth, setStageWidth] = useState(savedStageWidth);
  /* Only here to re-render everything when the language changes; the strings read the module's language. */
  const [language, setLanguageState] = useState(currentLanguage());
  /* Also only here to re-render: the views read the module's purpose (see purpose.ts). Only the add form changes it,
     before the workspace has one. */
  const [, setPurposeState] = useState(currentPurpose());
  const choosePurpose = (next: Purpose) => {
    setPurpose(next);
    setPurposeState(next);
  };
  /* The workspace's choice, once made, is what every view goes by. Set before the views below read it. */
  if (state?.purpose && state.purpose !== currentPurpose()) setPurpose(state.purpose);
  const dockOrder = useRef<string[]>([]);
  const playerRef = useRef<Player | null>(null);
  /* What to do when the stage's line plays to its end: in continuous play, go on to the next line. */
  const lineEnded = useRef<() => void>(() => {});
  /* Episodes whose whole copy the server said is ready since the overview was loaded. */
  const [copies, setCopies] = useState<Record<string, boolean>>({});
  const refAudio = useRef<HTMLAudioElement>(null);
  const stableOrder = useRef<string[] | null>(null);
  /* After retraining, the machine's new guesses show on the lines at once, but the lists do not move under your hand:
     lines don't join, leave or change places until you load the change. `placed` is, for each line whose guess
     changed since the list was laid out, the line as it was then, which decides where it sits; `incoming` the lines
     the machine has given to the open character since, not in the list yet. A line you labeled yourself moves at
     once, as before. */
  const [placed, setPlaced] = useState<Record<string, Clip>>({});
  const [incoming, setIncoming] = useState<Clip[]>([]);
  const loadSeq = useRef(0);

  const roles: Roles = useMemo(
    () => Object.fromEntries((state?.roles || []).map((r) => [r.name, r])),
    [state],
  );
  /* How labels that are not character names are shown; for now only "other". `tr` reads the language, which
     `language` follows. */
  const labelText: LabelText = useMemo(
    () => ({ [OTHER]: tr("不是目标", "Not a target"), [IGNORED]: tr("已忽略", "Ignored") }),
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- see above
    [language],
  );
  const episodeInfo = state?.episodes.find((e) => e.name === episode);
  /* The order of the bottom bar stays fixed for the session, with new characters added at the end, so number keys
     don't move under your hand. It is filled in while rendering, so a new character shows up at once without
     waiting for the next refresh. Names that are gone can stay in the order. On a rename the new name first takes
     the place right after the old one; see renameRole. */
  if (state) {
    const known = new Set(dockOrder.current);
    for (const r of state.roles) if (!known.has(r.name)) dockOrder.current.push(r.name);
  }
  /* The bottom bar holds only target characters; number keys follow its order. */
  const dock = dockOrder.current.filter((n) => roles[n]?.target);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);
  useEffect(() => {
    localStorage.setItem("scene-parts", JSON.stringify([...parts]));
    /* The choices these parts replaced. */
    localStorage.removeItem("short-lines");
    localStorage.removeItem("show-short");
  }, [parts]);
  useEffect(() => {
    localStorage.setItem("role-parts", JSON.stringify([...roleParts]));
  }, [roleParts]);
  useEffect(() => {
    localStorage.setItem("sound", sound);
  }, [sound]);
  useEffect(() => {
    localStorage.setItem("speed", String(speed));
  }, [speed]);
  useEffect(() => {
    localStorage.setItem("context", String(context));
  }, [context]);
  /* Write where you are after # in the address, so a refresh comes back to the same view, episode, character
     and line. */
  useEffect(() => {
    if (!state) return;
    const at = new URLSearchParams({
      view,
      ep: episode || "",
      role: role || "",
      clip: focus || "",
    });
    for (const [k, v] of [...at]) if (!v) at.delete(k);
    history.replaceState(null, "", `#${at}`);
  }, [state, view, episode, role, focus]);

  /* A short message at the bottom. One at a time: a new one takes the place of the last. `extra` adds an Undo
     button, `refresh` an Update list button, which also stays longer to give time to read. */
  const undoNow = useRef(() => {});
  const loadHeldNow = useRef(() => {});
  const showToast = useCallback(
    (message: string, isError = false, extra = false, refresh = false) => {
      const action = extra
        ? {
            label: (
              <>
                {tr("撤销", "Undo")} <Kbd>Z</Kbd>
              </>
            ),
            onClick: () => undoNow.current(),
          }
        : undefined;
      const cancel = refresh
        ? {
            label: (
              <span className="flex items-center gap-1">
                <RefreshCwIcon className="size-3.5" />
                {tr("更新列表", "Update list")}
              </span>
            ),
            onClick: () => loadHeldNow.current(),
          }
        : undefined;
      (isError ? toast.error : toast)(message, {
        id: "note",
        duration: isError ? 6000 : refresh ? 5000 : 3800,
        action,
        cancel,
      });
    },
    [],
  );

  /* Switch the page language. The overview is fetched again because it holds a few messages from the server,
     such as why an episode was not loaded. */
  const switchLanguage = () => pickLanguage(currentLanguage() === "en" ? "zh" : "en");
  const pickLanguage = (next: Language) => {
    setLanguage(next);
    setLanguageState(next);
    call<Summary>("/api/state")
      .then(setState)
      .catch(() => {});
  };

  useEffect(() => {
    call<Summary>("/api/state")
      .then((s) => {
        setState(s);
        const ep = saved.get("ep");
        if (s.episodes.length)
          setEpisode(ep && s.episodes.some((e) => e.name === ep) ? ep : s.episodes[0].name);
        const r = saved.get("role");
        if (r === OTHER || s.roles.some((x) => x.name === r)) setRole(r);
        const v = saved.get("view") as View | null;
        if (v && VIEWS.includes(v)) setView(v);
        else if (!s.roles.some((r) => r.confirmed > 0)) setView("groups");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  /* Follow an episode being added. When it ends, the overview is fetched again, since the server has reloaded the
     workspace with the new episode. */
  useEffect(() => {
    call<Adding>("/api/add")
      .then(setAdding)
      .catch(() => {});
  }, []);
  const addingState = adding?.state;
  /* Between two episodes of a queue the job is briefly not running; it is still followed while some wait. */
  const following =
    addingState === "running" || !!adding?.queue?.some((q) => q.state === "waiting");
  useEffect(() => {
    if (!following) return;
    const timer = setInterval(
      () =>
        call<Adding>("/api/add")
          .then(setAdding)
          .catch(() => {}),
      1500,
    );
    return () => clearInterval(timer);
  }, [following]);
  /* However it ended (done, failed, or stopped from the dialog), fetch the overview again: a new episode, or one
     left unfinished, shows up only then. */
  const addingBefore = useRef(addingState);
  /* In a queue the next episode starts as soon as one ends, so the job may never be seen stopped: a new episode
     means the one before it ended. */
  const addingEpisode = adding?.episode;
  const episodeBefore = useRef(addingEpisode);
  useEffect(() => {
    const before = addingBefore.current;
    const previous = episodeBefore.current;
    addingBefore.current = addingState;
    episodeBefore.current = addingEpisode;
    if (before === "running" && addingState === "running" && previous !== addingEpisode) {
      call<Summary>("/api/state")
        .then(setState)
        .catch(() => {});
      const ended = adding?.queue?.find((q) => q.episode === previous)?.state;
      if (ended === "done") showToast(tr(`${previous} 加好了`, `${previous} is added`));
      else if (ended === "failed")
        showToast(
          tr(
            `${previous} 没加成，接着加下一集`,
            `${previous} failed; going on with the next episode`,
          ),
          true,
        );
      return;
    }
    if (before !== "running" || addingState === "running" || !adding) return;
    call<Summary>("/api/state")
      .then(setState)
      .catch(() => {});
    if (addingState === "done")
      showToast(tr(`${adding.episode} 加好了`, `${adding.episode} is added`));
    else if (addingState === "failed")
      showToast(
        tr(
          `${adding.episode} 没加成，点「加一集」看原因`,
          `${adding.episode} failed; open "Add an episode" to see why`,
        ),
        true,
      );
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when the job's state or episode changes
  }, [addingState, addingEpisode]);
  /* The first episode added from the welcome page: open it, starting in Groups. */
  useEffect(() => {
    if (state && !episode && state.episodes.length) {
      setEpisode(state.episodes[0].name);
      if (!state.roles.some((r) => r.confirmed > 0)) setView("groups");
    }
  }, [state, episode]);
  const openEpisode = (name: string) => {
    setAddOpen(false);
    setEpisode(name);
  };

  /* Fetch the list again on a new episode, view or character. Once fetched its order stays fixed: labeled lines
     stay where they are instead of jumping away. */
  const hasState = !!state;
  /* Which list `clips` holds, Scenes' episode or Characters' character. Until the one shown has come, its counts
     would all read 0 and Scenes would say the episode is done, so the views wait instead. */
  const [listFor, setListFor] = useState<string | null>(null);
  const listLoading = listFor !== (view === "scene" ? `scene|${episode}` : `roles|${role}`);
  const load = useCallback(async () => {
    if (!hasState) return;
    /* Use only the latest request: an earlier one that comes back later must not overwrite an episode, view
       or character that has already changed. */
    const seq = ++loadSeq.current;
    const get = async <T,>(url: string) => {
      const result = await call<T>(url);
      if (seq !== loadSeq.current) throw STALE;
      return result;
    };
    if (view === "scene" && episode) {
      const list = await get<Clip[]>(`/api/clips?episode=${encodeURIComponent(episode)}`);
      setClips(list);
      setPlaced({});
      setIncoming([]);
      setListFor(`scene|${episode}`);
      stableOrder.current = null;
      /* The first line to do among the ticked parts, so the stage is not empty when the episode opens. */
      const shown = list.filter((c) => ticksNow.current.parts.has(partOf(c)));
      setFocus((f) =>
        list.some((c) => c.id === f)
          ? f
          : (shown.find((c) => WORK_PARTS.includes(partOf(c))) || shown[0] || list[0])?.id,
      );
    } else if (view === "roles" && role) {
      const list = await get<Clip[]>(`/api/clips?role=${encodeURIComponent(role)}`);
      setClips(list);
      setPlaced({});
      setIncoming([]);
      setListFor(`roles|${role}`);
      const first = roleOrder(list, role).find((c) =>
        ticksNow.current.roleParts.has(rolePartOf(c, role) as RolePart),
      );
      setFocus((f) => (list.some((c) => c.id === f) ? f : (first || list[0])?.id));
    } else if (view === "roles") {
      /* No character open, for example after the open one was undone: no list, and no line on the stage. */
      setClips([]);
    } else if (view === "groups" && episode) {
      setGroupsLoading(true);
      let found: KeyedGroup[];
      try {
        found = (await get<Group[]>(`/api/groups?episode=${encodeURIComponent(episode)}`)).map(
          (g, i) => ({ ...g, key: i }),
        );
      } finally {
        if (seq === loadSeq.current) setGroupsLoading(false);
      }
      setGroups(found);
      setPicked({});
      setClips(found.flatMap((g) => g.clips));
      setPlaced({});
      setIncoming([]);
      setFocus((f) =>
        found.some((g) => g.clips.some((c) => c.id === f)) ? f : found[0]?.clips[0]?.id,
      );
    }
  }, [view, episode, role, hasState, setFocus, setPicked]);
  const reload = () =>
    load().catch((e: Error) => {
      if (e !== STALE) showToast(e.message, true);
    });
  /* Clear the old list when the view, episode or character changes: its lines don't always fit the new view (for
     example lines without a guess in the Characters view), and until the new list comes, keys and "Confirm the
     rest" must not act on the old one under the new name. */
  useEffect(() => {
    /* Keep the same empty list when it is already empty, so React has nothing to draw again. */
    setClips((c) => (c.length ? [] : c));
    setGroups((g) => (g.length ? [] : g));
    setPlaced((p) => (Object.keys(p).length ? {} : p));
    setIncoming((c) => (c.length ? [] : c));
  }, [view, episode, role]);
  useEffect(() => {
    reload();
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- `load` changes exactly when the list must be fetched
  }, [load]);
  useEffect(() => {
    /* Also when the open character is gone, for example after undoing the step that made or renamed it. */
    const gone = role && role !== OTHER && state && !state.roles.some((r) => r.name === role);
    if (view === "roles" && (!role || gone) && state?.roles.length) setRole(state.roles[0].name);
    else if (gone) setRole(null);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when the view or the overview changes
  }, [view, state]);

  /* The lines as they were when the list was laid out, which decide where each one sits (see `placed`). */
  const laidOut = useMemo(() => clips.map((c) => placed[c.id] ?? c), [clips, placed]);
  /* The order "next / previous line" follows in the current view */
  const order = useMemo(() => {
    if (view === "scene") {
      /* The ticked parts, in episode order. Picked once and kept until the ticks or the episode change, so a
         line just labeled stays where it is, even when its label moves it to a part not ticked. */
      if (!stableOrder.current)
        stableOrder.current = clips.filter((c) => parts.has(partOf(c))).map((c) => c.id);
      return stableOrder.current;
    }
    if (view === "roles") return roleIds(laidOut, role, roleParts);
    if (view === "groups")
      return groups.flatMap((g) => g.clips.filter((c) => !c.label).map((c) => c.id));
    return [];
  }, [view, clips, laidOut, parts, roleParts, role, groups]);
  /* What loading the machine's new guesses would change in the list: lines that would join it, leave it, or only
     move. Only lines whose guess changed count, so a line you labeled, which stays put in Scenes, does not. */
  const held = useMemo(() => {
    const changed = Object.keys(placed);
    if ((view !== "scene" && view !== "roles") || (!changed.length && !incoming.length))
      return null;
    const fresh =
      view === "scene"
        ? clips.filter((c) => parts.has(partOf(c))).map((c) => c.id)
        : roleIds(
            [...clips, ...incoming].filter((c) => belongs(c, role)),
            role,
            roleParts,
          );
    const now = new Set(order);
    const next = new Set(fresh);
    const join = changed.filter((id) => next.has(id) && !now.has(id)).length + incoming.length;
    const leave = changed.filter((id) => now.has(id) && !next.has(id)).length;
    const keptNext = fresh.filter((id) => now.has(id));
    const moved = order.filter((id) => next.has(id)).some((id, i) => id !== keptNext[i]);
    return join || leave || moved ? { join, leave } : null;
  }, [placed, incoming, view, clips, parts, role, roleParts, order]);
  /* Lay the list out again with the new guesses. The open line stays open if it is still in the list, else the
     next one after it that is. */
  const loadHeld = () => {
    const before = order;
    const at = focusNow.current ? before.indexOf(focusNow.current) : -1;
    const fresh =
      view === "roles" ? [...clips, ...incoming].filter((c) => belongs(c, role)) : clips;
    const next =
      view === "scene"
        ? fresh.filter((c) => parts.has(partOf(c))).map((c) => c.id)
        : roleIds(fresh, role, roleParts);
    stableOrder.current = view === "scene" ? next : null;
    setClips(fresh);
    setPlaced({});
    setIncoming([]);
    if (focusNow.current && !next.includes(focusNow.current)) {
      const keep = new Set(next);
      setFocus(before.slice(at + 1).find((id) => keep.has(id)) ?? next[0]);
    }
  };
  loadHeldNow.current = loadHeld;
  /* The message of a label change waits here until the page has drawn the answer, so it can also say, in the same
     message, what the machine's new guesses would change in the list. */
  const note = useRef<{ text: string; ripple: string; undo: boolean } | null>(null);
  const [noteSeq, setNoteSeq] = useState(0);
  /* The message on screen speaks of changes waiting in the list. */
  const heldSaid = useRef(false);
  const heldKey = held ? `${held.join}|${held.leave}` : null;
  /* "Auto" beside Update list: the list updates as soon as the machine guesses again. Kept on this machine. */
  const [autoRefresh, setAutoRefreshState] = useState(
    () => localStorage.getItem("auto-update") === "1",
  );
  const setAutoRefresh = (on: boolean) => {
    localStorage.setItem("auto-update", on ? "1" : "0");
    setAutoRefreshState(on);
  };
  useEffect(() => {
    if (autoRefresh && held) {
      /* Update at once, and say what changed; there is nothing left to click. */
      loadHeld();
      const said = note.current;
      note.current = null;
      showToast(
        said ? tr(`${said.text}。`, `${said.text}. `) + autoText(held) : autoText(held),
        false,
        !!said?.undo,
      );
      /* The message on screen says the list already changed: the next run must not close it. */
      heldSaid.current = false;
      return;
    }
    const said = note.current;
    note.current = null;
    if (said) {
      heldSaid.current = !!held;
      showToast(
        held ? tr(`${said.text}。`, `${said.text}. `) + heldText(held) : said.text + said.ripple,
        false,
        said.undo,
        !!held,
      );
    } else if (held) {
      /* Changes waiting that came without a label change, or became different. */
      heldSaid.current = true;
      showToast(heldText(held), false, false, true);
    } else if (heldSaid.current) {
      heldSaid.current = false;
      toast.dismiss("note");
    }
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- on a new label message, when what would change is different, or when Auto is turned on
  }, [noteSeq, heldKey, autoRefresh]);
  /* Drop the old order right when the ticks change, so the next computed order is the one that stays. Doing it in
     an effect clears it only after the order is computed: labeling the first line recomputes the order, and the
     line just labeled disappears from the list. */
  const setParts = (next: Set<Part>) => {
    stableOrder.current = null;
    setPartsState(next);
  };
  const onlyWork = parts.size === WORK_PARTS.length && WORK_PARTS.every((p) => parts.has(p));
  /* F: only the lines still to do, and back to the parts ticked before. */
  const toggleOnlyWork = () => {
    if (onlyWork) setParts(partsBefore.current);
    else {
      if (parts.size) partsBefore.current = parts;
      setParts(new Set(WORK_PARTS));
    }
  };

  const byId = useMemo(() => Object.fromEntries(clips.map((c) => [c.id, c])), [clips]);
  /* When the tick boxes of Scenes filter out the focused line, the stage stays empty, so shortcuts can't change a
     line you can't see in the list. */
  const shownClip = (id: string | null): Clip | null => {
    const clip = id ? byId[id] : undefined;
    if (!clip) return null;
    if (view === "scene") return order.includes(clip.id) ? clip : null;
    /* The same in Characters for a part not ticked, by the part it sits in. A line just labeled as someone else is
       in no part and stays. */
    const part = view === "roles" ? rolePartOf(placed[clip.id] ?? clip, role) : null;
    return part && !roleParts.has(part) ? null : clip;
  };
  const current = shownClip(focus);
  /* The open line's episode has its whole copy ready, so the stage plays from it instead of one cut per line. */
  const whole =
    !!current &&
    (copies[current.episode] ?? !!state?.episodes.find((e) => e.name === current.episode)?.player);
  /* What the shortcuts and buttons act on; see focusNow. */
  const now = () => shownClip(focusNow.current);

  useEffect(() => {
    if (!focus) return;
    const at = order.indexOf(focus);
    if (at < 0) return;
    const next = order.slice(at + 1, at + 4).map((id) => byId[id]);
    if (!whole && episodeInfo?.video) warm(next, "video", context);
    if (!whole && (!episodeInfo?.video || sound === "vocals")) warm(next, "audio", context);
    /* The server makes the episode's whole copy in the background, and until it is ready first cuts the clips
       within a minute of this line, then on to the end of the episode. The answer says when the copy is ready.
       While J/K is held down to flip fast, only the line you stop on is sent. */
    const wait = setTimeout(() => {
      const ep = byId[focus]?.episode;
      call<{ player?: { ready: boolean } }>("/api/prefetch", { clip: focus })
        .then((r) => {
          if (ep && r.player?.ready) setCopies((c) => (c[ep] ? c : { ...c, [ep]: true }));
        })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(wait);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only on moving to another line, not on every save
  }, [focus, order, context]);

  /* The Groups order only has unlabeled lines. When a labeled one is open, find next and previous by its place
     in the group. */
  const groupIds = useMemo(() => groups.flatMap((g) => g.clips.map((c) => c.id)), [groups]);
  /* What the number keys, Q, N and the bottom bar label: in Groups the ticked lines if there are any, else the
     line playing. The ticks are used up, so the next press goes to the line playing. */
  const keyTargets = () => {
    if (view !== "groups") return undefined;
    const ticked = groups.flatMap((g) =>
      g.clips.filter((c) => !c.label && pickedNow.current[g.key]?.has(c.id)),
    );
    if (!ticked.length) return undefined;
    setPicked({});
    return ticked.map((c) => c.id);
  };
  const besides = (id: string) => {
    const at = groupIds.indexOf(id);
    return {
      after: order.filter((o) => groupIds.indexOf(o) > at),
      before: order.filter((o) => groupIds.indexOf(o) < at),
    };
  };
  /* Step from the newest focus, not the one this render saw: two quick presses of J come before the page has
     drawn again, and each must move one line. */
  const move = (step: number) =>
    setFocus((f) => {
      const at = f ? order.indexOf(f) : -1;
      if (f && at < 0 && view === "groups" && groupIds.includes(f)) {
        const { after, before } = besides(f);
        return (step > 0 ? (after[0] ?? before.at(-1)) : (before.at(-1) ?? after[0])) ?? f;
      }
      return order[Math.min(Math.max(at + step, 0), order.length - 1)] ?? f;
    });

  /* Move on after labeling a line. The Scenes view jumps to the next line that still needs work, instead of
     going through confirmed lines one by one. */
  const advance = (fromId: string | null, list = order) => {
    const at = fromId ? list.indexOf(fromId) : -1;
    for (let i = at + 1; i < list.length; i++) {
      const c = byId[list[i]];
      if (c && (view !== "scene" || NEEDS_WORK.has(c.status) || c.status === "auto")) {
        setFocus(list[i]);
        return;
      }
    }
    if (list[at + 1]) setFocus(list[at + 1]);
  };

  /* Move on after labeling a batch in Groups: the first unlabeled line after the batch, else from the top. */
  const nextUnlabeled = (ids: string[]) => {
    const rest = (id: string) => !ids.includes(id);
    const last = ids.reduce(
      (a, id) => (groupIds.indexOf(id) > groupIds.indexOf(a) ? id : a),
      ids[0],
    );
    return besides(last).after.find(rest) ?? order.find(rest);
  };

  const applyResult = (result: ChangeResult, label: string) => {
    setState(result.state);
    const updated: Record<string, Clip | undefined> = Object.fromEntries(
      result.updated.map((c) => [c.id, c]),
    );
    /* "Maybe missed" is decided when the Characters view fetches its list, and updated lines don't carry it, so
       keep it; a line labeled as this character is no longer missed. */
    /* The answer may come after you switched view or character, so read the ones open now. */
    /* `updated` lists the lines changed by hand first, then the ones whose guess changed along with them. */
    const byHand = new Set(
      result.updated.slice(0, result.updated.length - result.ripple).map((c) => c.id),
    );
    setClips((list) => {
      const old: Record<string, Clip> = {};
      const kept = list.map((c) => {
        const next = updated[c.id];
        if (!next) return c;
        if (!byHand.has(c.id)) old[c.id] = c;
        return c.maybe && next.label !== roleNow.current ? { ...next, maybe: true } : next;
      });
      /* A line changed by machine keeps the place it had when the list was laid out; one you changed moves. Both
         updates give the same result when run twice, as React may do. */
      setPlaced((p) => {
        const out = { ...p };
        for (const id of byHand) delete out[id];
        for (const [id, c] of Object.entries(old)) out[id] ??= c;
        return out;
      });
      /* In Characters, a line the machine now gives to the open character waits outside the list until loaded. */
      if (viewNow.current === "roles" && roleNow.current) {
        const have = new Set(list.map((c) => c.id));
        const mine = (c: Clip) => !have.has(c.id) && whoOf(c)?.name === roleNow.current;
        setIncoming((cur) => {
          const out = cur.filter((c) => !updated[c.id]);
          out.push(...result.updated.filter(mine));
          return out.length || cur.length ? out : cur;
        });
      }
      return kept;
    });
    /* In Groups, labeled lines stay where they are, marked as labeled, instead of leaving the group: the
       unlabeled line next to it doesn't vanish with it, and undo puts things back exactly. Done in every view:
       with no groups loaded it changes nothing. */
    setGroups((gs) => gs.map((g) => ({ ...g, clips: g.clips.map((c) => updated[c.id] ?? c) })));
    const flashing = new Set(result.updated.map((c) => c.id));
    setFlashes(flashing);
    setTimeout(() => setFlashes(new Set()), 900);
    /* After taking steps back: the lines a later step changed again, which keep that, and steps left out. */
    const kept = result.kept
      ? tr(
          `；${result.kept} 句之后又改过，保持后来的样子`,
          `; ${lines(result.kept)} changed again later kept that`,
        )
      : "";
    const skipped = (result.skipped ?? [])
      .map((s) =>
        tr(
          `；第 ${s.batch} 步没有撤销：名字「${s.name}」现在已被占用或已不存在`,
          `; step ${s.batch} not taken back: the name "${s.name}" is taken now or gone`,
        ),
      )
      .join("");
    if (result.batch !== null) {
      const ripple = result.ripple
        ? tr(
            `，另有 ${result.ripple} 句的猜测随之改变`,
            `; guesses changed for ${lines(result.ripple)} more`,
          )
        : "";
      /* Said once the page has drawn the answer, together with what the new guesses would change (see `note`). */
      note.current = { text: `${label}${kept}${skipped}`, ripple, undo: !result.undo };
      setNoteSeq((n) => n + 1);
    } else if (skipped) {
      showToast(tr(`没有撤销${skipped}`, `Nothing taken back${skipped}`), true);
    }
  };

  /* Changes are queued, so no key press is lost: when your hands are faster than a round trip, the first press
     is saved first. The page moves on without waiting for the answer; if saving fails, it says so and moves the
     focus back to that line. */
  const queue = useRef<Promise<void>>(Promise.resolve());
  const pendingCount = useRef(0);
  /* Lines with a label change still on its way, and how many changes each has queued. */
  const saving = useRef(new Map<string, number>());
  const send = (
    url: string,
    body: { clips?: string[] } & Record<string, unknown>,
    label: string,
    onFail?: () => void,
  ): Promise<ChangeResult | null> => {
    setBusy(true);
    pendingCount.current += 1;
    const ids = body.clips || [];
    for (const id of ids) saving.current.set(id, (saving.current.get(id) || 0) + 1);
    const run = queue.current.then(async () => {
      try {
        const result = await call<ChangeResult>(url, body);
        applyResult(result, label);
        return result;
      } catch (e) {
        showToast(
          tr(`没有保存：${(e as Error).message}`, `Not saved: ${(e as Error).message}`),
          true,
        );
        onFail?.();
        return null;
      } finally {
        for (const id of ids) {
          const left = (saving.current.get(id) ?? 1) - 1;
          if (left > 0) saving.current.set(id, left);
          else saving.current.delete(id);
        }
        pendingCount.current -= 1;
        if (pendingCount.current === 0) setBusy(false);
      }
    });
    queue.current = run.then(() => {});
    return run;
  };

  /* One choice sets both who it is and whether it is low quality: low means "them, low quality"; otherwise it is
     clean, and an earlier low quality mark is turned off. */
  const assign = (name: string, ids?: string[], low = false) => {
    const clip = now();
    const targets = ids ?? (clip ? [clip.id] : []);
    if (!targets.length || !name) return;
    const from = focusNow.current;
    const who = labelText[name] ? tr(`「${labelText[name]}」`, `"${labelText[name]}"`) : name;
    const what = low ? tr(`${who}·质量低，不导出`, `${who}, low quality, left out on export`) : who;
    const label =
      targets.length > 1
        ? tr(`${targets.length} 句已标为 ${what}`, `${lines(targets.length)} labeled ${what}`)
        : tr(`已标为 ${what}`, `Labeled ${what}`);
    send("/api/label", { clips: targets, label: name, unusable: low }, label, () => setFocus(from));
    if (view === "groups") setFocus(nextUnlabeled(targets));
    else if (targets.length === 1) advance(from);
  };
  const accept = () => {
    const clip = now();
    if (!clip) return;
    if (clip.label) {
      move(1);
      return;
    }
    if (clip.guess.length) assign(clip.guess[0].name);
  };
  const clear = () => {
    const clip = now();
    if (clip?.label)
      send(
        "/api/label",
        { clips: [clip.id], label: null },
        tr("已清掉这句的标签", "Label cleared"),
      );
  };
  /* A save still on its way can be undone too, though the overview doesn't know of it yet. Afterwards go back to
     the line that was undone, if it is in this list. */
  const undo = async () => {
    if (!state?.can_undo && pendingCount.current === 0) {
      showToast(tr("没有可以撤销的操作", "Nothing to undo"));
      return;
    }
    goBack(await send("/api/undo", {}, tr("已撤销", "Undone")));
  };
  /* Take back chosen steps from the history list. */
  const revert = async (batches: number[], what: string) =>
    goBack(await send("/api/revert", { batches }, what));
  /* `updated` lists the lines undone first, then the ones whose guess changed along with them. */
  const goBack = (result: ChangeResult | null) => {
    const back = result?.updated
      .slice(0, result.updated.length - result.ripple)
      .map((c) => c.id)
      .filter((id) => order.includes(id) || groupIds.includes(id));
    if (back?.length) setFocus(back.sort((a, b) => order.indexOf(a) - order.indexOf(b))[0]);
  };

  const playRef = async (name: string) => {
    const asked = focusNow.current;
    try {
      const refs = await call<Clip[]>(`/api/references?name=${encodeURIComponent(name)}`);
      if (focusNow.current !== asked) return; // Moved on while waiting.
      if (!refs.length) {
        showToast(
          tr(
            `${name} 还没有确认过的台词可以当参考`,
            `${name} has no confirmed lines to use as a reference yet`,
          ),
        );
        return;
      }
      const pick = refs[Math.floor(Math.random() * refs.length)];
      playerRef.current?.pause();
      const audio = refAudio.current;
      if (!audio) return;
      audio.src = media("audio", pick.id);
      audio.defaultPlaybackRate = speed;
      audio.playbackRate = speed;
      audio.play().catch(() => {});
      showToast(
        tr(`参考音：${name}「${pick.text || "…"}」`, `Reference: ${name} "${pick.text || "…"}"`),
      );
    } catch (e) {
      showToast((e as Error).message, true);
    }
  };

  const confirmRest = async () => {
    /* Leave out lines you just labeled whose answer hasn't come back: confirming them here would undo your fix. */
    /* And only lines the machine gave to the character open now: right after switching character, for a moment
       the list on hand can still be the last one's. And only the kinds ticked: Shift+Enter must not confirm lines
       you can't see. */
    /* Only the lines in the list as you see it, and whose newest guess is still this character. */
    const pending = pendingOf(laidOut).filter(
      (c) =>
        !saving.current.has(c.id) &&
        byId[c.id]?.guess[0]?.name === role &&
        roleParts.has(rolePartOf(c, role) as RolePart),
    );
    if (!pending.length) return;
    const changes = pending.map((c) => ({ clip: c.id, label: role }));
    const result = await send(
      "/api/changes",
      { changes },
      tr(
        `确认了 ${pending.length} 句是${role === OTHER ? "「不是目标」" : ` ${role}`}`,
        `Confirmed ${lines(pending.length)} as ${role === OTHER ? '"Not a target"' : role}`,
      ),
    );
    if (result) {
      setPlaying(false);
      reload();
    }
  };
  const renameRole = async (typed: string) => {
    setRenaming(false);
    const next = typed.trim();
    if (!role || !next || next === role) return;
    /* A rename keeps the number key: the new name takes the old name's place. On a merge the old name leaves the bar. */
    const renamed = !roles[next];
    if (renamed)
      dockOrder.current = dockOrder.current.flatMap((n) => (n === role ? [n, next] : [n]));
    const result = await send(
      "/api/roles",
      { name: role, new_name: next },
      renamed
        ? tr(`已改名为 ${next}`, `Renamed to ${next}`)
        : tr(`已并进 ${next}`, `Merged into ${next}`),
    );
    if (result) {
      setRole(next);
    }
  };
  const toggleTarget = async () => {
    const info = role ? roles[role] : undefined;
    if (!role || !info) return;
    const message = info.target
      ? tr(
          `${role} 不再是目标角色，已标的留着`,
          `${role} is no longer a target character; their labels stay`,
        )
      : tr(`${role} 设为目标角色了`, `${role} is now a target character`);
    /* Target settings don't change labels, so the server records no batch and the page shows the message itself. */
    const result = await send("/api/roles", { name: role, target: !info.target }, message);
    if (result) {
      showToast(message);
      reload();
    }
  };
  /* Cropping an avatar uses the video playing on the stage. `then` runs after cropping or cancelling, for example
     moving on after labeling a new character. */
  const stageVideo = () => playerRef.current?.frame() ?? null;
  const hasFrame = () => !!stageVideo()?.videoWidth;
  const openCrop = (name: string | null, then: (() => void) | null = null) => {
    if (!hasFrame() || !name) {
      showToast(
        episodeInfo?.video
          ? tr("画面还没出来", "The picture hasn't loaded yet")
          : tr(
              "这一集没有视频，截不了头像",
              "This episode has no video, so there is nothing to crop",
            ),
        true,
      );
      then?.();
      return;
    }
    setCrop({ name, then });
  };
  const closeCrop = () => {
    const then = crop?.then;
    setCrop(null);
    then?.();
  };
  /* A name for a new character must not be taken: that would be a merge, which belongs in the Characters view. */
  const nameTaken = (typed: string) =>
    otherName(typed)
      ? tr("「不是目标」是标签，不能当名字", '"Not a target" is a label, not a name')
      : roles[typed]
        ? tr(
            `已经有叫「${typed}」的角色了。换一个名字；是同一个人的话，以后在「角色」里合并`,
            `There is already a character called "${typed}". Pick another name; if it is the same person, merge them later in Characters`,
          )
        : "";
  /* Cancel in the New target dialog takes the new character back: the lines return to how they were. */
  const cancelNew = () => {
    setCrop(null);
    undo();
  };
  const saveCrop = async (image: string | null, typed: string) => {
    if (!crop) return;
    let name = crop.name;
    closeCrop();
    if (typed && typed !== name) {
      /* Like a rename in the Characters view: the new name keeps the number key. */
      const old = name;
      dockOrder.current = dockOrder.current.flatMap((n) => (n === old ? [n, typed] : [n]));
      if (
        !(await send(
          "/api/roles",
          { name, new_name: typed },
          tr(`已起名为 ${typed}`, `Named ${typed}`),
        ))
      )
        return;
      name = typed;
    }
    if (!image) return;
    try {
      setState(await call<Summary>("/api/roles/avatar", { name, image }));
      showToast(tr(`已换好 ${name} 的头像`, `Avatar of ${name} updated`));
    } catch (e) {
      showToast((e as Error).message, true);
    }
  };
  /* Label as a new character, then ask for a name (optional). If the current line is in the batch and there is a
     picture, the same dialog also crops an avatar from this frame. */
  /* Each request makes a fresh character, so a second press before the answer would make an empty second one. */
  const makingRole = useRef(false);
  const newRole = async (ids?: string[]) => {
    const clip = now();
    const targets = ids ?? (clip ? [clip.id] : []);
    if (!targets.length || makingRole.current) return;
    makingRole.current = true;
    const from = focusNow.current;
    let result: ChangeResult | null;
    try {
      result = await send(
        "/api/label",
        { clips: targets, new_role: true },
        targets.length > 1
          ? tr(
              `${targets.length} 句标成了一个新目标`,
              `${lines(targets.length)} labeled as a new target`,
            )
          : tr("已标成一个新目标", "Labeled as a new target"),
      );
    } finally {
      makingRole.current = false;
    }
    /* If you moved to another line while waiting, stay there: no cropping from that line's frame. */
    if (!result?.role || focusNow.current !== from) return;
    const onward = () => {
      if (view === "groups") setFocus(nextUnlabeled(targets));
      else if (targets.length === 1) advance(from);
    };
    setCrop({
      name: result.role,
      then: onward,
      naming: true,
      frame: !!from && targets.includes(from) && hasFrame(),
    });
  };

  /* Replay this line from the start. Clicking a line in the list selects it if not selected (it then plays by
     itself), or replays it if it already is, like Space. */
  const replay = () => playerRef.current?.replay();
  const pick = (id: string) => (id === focus ? replay() : setFocus(id));

  /* The lines still to check in the ticked parts of To do: continuous play goes only through lines on the list. */
  const shownPending = (list: Clip[]) =>
    pendingOf(list).filter((c) => roleParts.has(rolePartOf(c, role) as RolePart));
  /* Continuous play in the Characters view: when a line ends, jump to the next one to check. Playing stops after
     the last line still to check; the lines below it are already settled. */
  useEffect(() => {
    if (!playing || view !== "roles") return;
    let timer = 0;
    lineEnded.current = () => {
      timer = setTimeout(() => {
        const toCheck = shownPending(clips).map((c) => c.id);
        const at = focusNow.current ? toCheck.indexOf(focusNow.current) : -1;
        if (at >= 0 && at + 1 < toCheck.length) setFocus(toCheck[at + 1]);
        else setPlaying(false);
      }, 250);
    };
    return () => {
      lineEnded.current = () => {};
      clearTimeout(timer);
    };
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- shownPending reads the ticks and the role
  }, [playing, focus, view, clips, roleParts, role, setFocus]);
  useEffect(() => {
    setPlaying(false);
  }, [view, role]);
  /* Playing starts from the first line to check, or replays the open one if it is one of them: it may have
     finished already, and then no end would come to move on from. */
  useEffect(() => {
    if (!playing) return;
    const toCheck = shownPending(clips);
    if (toCheck.some((c) => c.id === focusNow.current)) replay();
    else if (toCheck.length) setFocus(toCheck[0].id);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- only when playing starts
  }, [playing]);
  /* A reference clip belongs to the line it was asked on. */
  useEffect(() => {
    refAudio.current?.pause();
  }, [focus]);

  /* All shortcuts */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (crop || renaming) return;
      if (help || addOpen || guide) {
        if (e.key === "Escape") {
          setHelp(false);
          setAddOpen(false);
          closeGuide();
        }
        return;
      }
      if (typing(e.target) || (e.ctrlKey && e.key !== "z") || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      /* Holding a key down repeats only moving between lines; a held Enter, digit or Z would label or undo a
         whole run of lines. */
      if (e.repeat && !["j", "k", "arrowdown", "arrowup"].includes(k)) {
        e.preventDefault();
        return;
      }
      const handled = () => e.preventDefault();
      const clip = now();
      if (k === "j" || e.key === "ArrowDown") {
        handled();
        move(1);
      } else if (k === "k" || e.key === "ArrowUp") {
        handled();
        move(-1);
      } else if (e.key === " ") {
        handled();
        replay();
      } else if (e.key === "Enter" && e.shiftKey && view === "roles") {
        handled();
        confirmRest();
      } else if (e.key === "Enter") {
        handled();
        accept();
      } else if (/^(Digit|Numpad)[1-9]$/.test(e.code)) {
        /* Read the digit from e.code: with Shift held, e.key is "!", "@" and so on. Shift + number is the same
           character, low quality. */
        const name = dock[Number(e.code.at(-1)) - 1];
        if (name) {
          handled();
          pulse(e.shiftKey ? name + LOW_KEY : name);
          assign(name, keyTargets(), e.shiftKey);
        }
      } else if (k === "q") {
        handled();
        pulse(OTHER);
        assign(OTHER, keyTargets());
      } else if (k === "x" && view !== "export") {
        handled();
        pulse(IGNORED);
        assign(IGNORED, keyTargets());
      } else if (k === "n" && clip && view !== "export") {
        handled();
        pulse(NEW_KEY);
        newRole(keyTargets());
      } else if (e.key === "?") {
        handled();
        setHelp(true);
      } else if (k === "z") {
        handled();
        pulse(UNDO_KEY);
        undo();
      } else if (e.key === "Backspace" || e.key === "Delete") {
        handled();
        clear();
      } else if (k === "r" && clip?.guess.length && clip.guess[0].name !== OTHER) {
        handled();
        playRef(clip.guess[0].name);
      } else if (k === "l" && current) {
        handled();
        nextContext();
      } else if (k === "f" && view === "scene") {
        handled();
        toggleOnlyWork();
      } else if (k === "p" && view === "roles") {
        handled();
        setPlaying(!playing);
      } else if (k === "g") {
        handled();
        setView("groups");
      } else if (k === "s") {
        handled();
        setView("scene");
      } else if (k === "o") {
        handled();
        setView("roles");
      } else if (k === "e") {
        handled();
        setView("export");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  /* The guide opens by itself once: the first time there are episodes but nothing is labeled. */
  const firstLook = !!state?.episodes.length && !state.model.labels;
  useEffect(() => {
    if (firstLook && !localStorage.getItem(GUIDE_SEEN)) setGuide(true);
  }, [firstLook]);
  const closeGuide = () => {
    localStorage.setItem(GUIDE_SEEN, "1");
    setGuide(false);
  };

  undoNow.current = undo;
  const [dockHeight, setDockHeight] = useState(0);
  const dockRef = useCallback((bar: HTMLElement | null) => {
    if (!bar) return;
    const watch = new ResizeObserver(() => setDockHeight(bar.offsetHeight));
    watch.observe(bar);
    return () => watch.disconnect();
  }, []);
  /* Messages show above everything. At the bottom they would cover a dialog's buttons, so while one is open they
     move to the top of the window. Otherwise they sit just above the bottom bar, whose height changes when its
     chips wrap to a second row. */
  const dialog = !!crop || renaming || help || guide || addOpen;
  const toaster = (
    <Toaster
      theme={theme === "dark" ? "dark" : "light"}
      position={dialog ? "top-center" : "bottom-center"}
      offset={dialog || view === "export" ? 12 : dockHeight + 12}
    />
  );
  /* The language button on pages without the top bar (empty workspace, can't connect). */
  const corner = (
    <div className="fixed top-3 right-4">
      <LanguageButton onSwitch={switchLanguage} />
    </div>
  );
  if (error)
    return (
      <>
        {corner}
        <Empty title={tr("连不上本地服务", "Can't reach the local server")}>
          <p>{error}</p>
        </Empty>
      </>
    );
  if (!state)
    return (
      <Empty>
        <Spinner className="mx-auto size-6" />
        <p>{tr("正在载入…", "Loading…")}</p>
      </Empty>
    );
  const addProps = {
    state,
    setState,
    adding,
    setAdding,
    onOpen: openEpisode,
    toast: showToast,
    onPurpose: choosePurpose,
  };
  if (!state.episodes.length) {
    return (
      <>
        {corner}
        <Welcome {...addProps} onLanguage={pickLanguage} />
        {toaster}
      </>
    );
  }

  const counts = episodeInfo?.counts || {};
  /* Short lines skipped by default, lines the machine set aside as low quality, and lines a person ignored need
     no labeling and don't count toward progress. */
  const total =
    Object.values(counts).reduce((a: number, b) => a + (b ?? 0), 0) -
      (counts.skipped || 0) -
      (counts.likely_low || 0) -
      (counts.ignored || 0) || 1;
  const progress = { done: (counts.confirmed || 0) / total, auto: (counts.auto || 0) / total };
  const work = episodeInfo?.work ?? 0;
  const showStage = view !== "export";
  const cropRole = crop ? roles[crop.name] : undefined;

  /* Overall layout: top bar, stage on the left, list on the right, character bar at the bottom. The whole page
     does not scroll, only the list does. */
  return (
    <div className="flex h-screen flex-col">
      <TopBar
        episodes={state.episodes.map((e) => e.name)}
        toCheck={state.roles.filter((r) => r.target).reduce((n, r) => n + r.to_check, 0)}
        todo={Object.fromEntries(state.episodes.map((e) => [e.name, e.work]))}
        episode={episode}
        setEpisode={setEpisode}
        onAdd={() => setAddOpen(true)}
        unfinished={Object.keys(state.skipped || {}).length}
        view={view}
        setView={setView}
        work={work}
        adding={addingState === "running" && !addOpen ? (adding?.episode ?? "") : null}
        onShowAdding={() => setAddOpen(true)}
        busy={busy}
        trainedOn={state.model.labels || 0}
        targets={state.roles.filter((r) => r.target).length}
        dark={theme === "dark"}
        onTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
        onLanguage={switchLanguage}
        onGuide={() => setGuide(true)}
        onHelp={() => setHelp(true)}
      />
      {state.outdated !== false && (
        <div className="border-b bg-warning/15 px-[18px] py-2 text-[13px] text-warning">
          {withKeys(
            tr(
              "avoc 已经更新，但正在运行的服务还是旧的，有些内容会显示不出来。关掉运行 avoc app 的窗口（或按 [Ctrl]+[C]），再重新运行它，然后刷新这个页面。",
              "avoc was updated, but the running server is still the old one, so some things will not show. Close the window running avoc app (or press [Ctrl]+[C]), run it again, then refresh this page.",
            ),
          )}
        </div>
      )}

      <div
        className="grid min-h-0 flex-1"
        style={{
          gridTemplateColumns: showStage ? `${fitStage(stageWidth)}px auto minmax(0, 1fr)` : "1fr",
        }}
      >
        {showStage && (
          <Stage
            clip={current}
            roles={roles}
            labelText={labelText}
            sound={sound}
            setSound={setSound}
            speed={speed}
            setSpeed={setSpeed}
            hasVideo={!!episodeInfo?.video}
            whole={whole}
            playerRef={playerRef}
            onEnded={() => lineEnded.current()}
            onAssign={(n, low) => assign(n, undefined, low)}
            onAccept={accept}
            onPlayRef={playRef}
            onAvatar={(name) => openCrop(name)}
            onNewRole={() => newRole()}
            onClear={clear}
            context={context}
            setContext={setContext}
            pad={state.picture_pad ?? 0}
            dock={dock}
            waiting={state.model.waiting ?? {}}
            minLabels={state.model.min_labels ?? 0}
          />
        )}
        {showStage && <Divider width={fitStage(stageWidth)} setWidth={setStageWidth} />}
        {/* The scrollbar's room is kept even when the list is short, so the width does not change when lines are
            ticked into view; it did, and boxes near the right edge jumped to the next line. */}
        <main className="@container min-h-0 scroll-pt-20 [scrollbar-gutter:stable] overflow-y-auto px-5 pt-2 pb-10">
          {view === "scene" && (
            <SceneView
              clips={clips}
              order={order}
              focus={focus}
              setFocus={pick}
              roles={roles}
              labelText={labelText}
              parts={parts}
              setParts={setParts}
              onlyWork={onlyWork}
              toggleOnlyWork={toggleOnlyWork}
              loading={listLoading}
              flashes={flashes}
              episode={episode}
              progress={progress}
            />
          )}
          {view === "roles" && (
            <RoleView
              state={state}
              roles={roles}
              labelText={labelText}
              role={role}
              setRole={setRole}
              clips={laidOut}
              live={byId}
              loading={listLoading}
              focus={focus}
              setFocus={pick}
              onConfirmRest={confirmRest}
              parts={roleParts}
              setParts={setRoleParts}
              onRename={() => setRenaming(true)}
              onToggleTarget={toggleTarget}
              flashes={flashes}
              onAvatar={() => openCrop(role)}
              canCrop={!!current && !!episodeInfo?.video}
              playing={playing}
              setPlaying={setPlaying}
            />
          )}
          {view === "groups" && (
            <GroupsView
              key={episode}
              groups={groups}
              loading={groupsLoading}
              roles={roles}
              labelText={labelText}
              focus={focus}
              setFocus={pick}
              picked={picked}
              setPicked={setPicked}
              episode={episode}
              progress={progress}
              work={work}
              onGo={setView}
            />
          )}
          {view === "export" && <ExportView state={state} setState={setState} toast={showToast} />}
        </main>
      </div>

      {view !== "export" && (
        <Dock
          ref={dockRef}
          dock={dock}
          roles={roles}
          labelText={labelText}
          canNew={!!current}
          canLabel={
            !!current ||
            (view === "groups" &&
              groups.some((g) => g.clips.some((c) => !c.label && picked[g.key]?.has(c.id))))
          }
          onName={(name, low) => assign(name, keyTargets(), low)}
          onNew={() => current && newRole(keyTargets())}
          canUndo={!!state.can_undo}
          onUndo={undo}
          canRefresh={!!held}
          autoRefresh={autoRefresh}
          setAutoRefresh={setAutoRefresh}
          onRefresh={loadHeld}
          history={
            <History roles={roles} labelText={labelText} version={state} onRevert={revert} />
          }
          flash={flash}
        />
      )}

      <audio ref={refAudio} hidden></audio>
      {crop && (
        <Cropper
          source={!crop.naming || crop.frame ? stageVideo() : null}
          name={crop.name}
          role={cropRole}
          naming={crop.naming}
          taken={nameTaken}
          onSave={saveCrop}
          onClose={crop.naming ? cancelNew : closeCrop}
        />
      )}
      {renaming && role && roles[role] && (
        <RenameDialog
          name={role}
          unnamed={roles[role].named === false}
          others={Object.keys(roles).filter((n) => n !== role && n !== OTHER)}
          onSave={renameRole}
          onClose={() => setRenaming(false)}
        />
      )}
      {help && (
        <Help
          onClose={() => setHelp(false)}
          onGuide={() => {
            setHelp(false);
            setGuide(true);
          }}
        />
      )}
      {guide && (
        <Guide
          onClose={closeGuide}
          onStart={() => {
            closeGuide();
            setView("groups");
          }}
        />
      )}
      {addOpen && <AddDialog onClose={() => setAddOpen(false)} {...addProps} />}
      {toaster}
    </div>
  );
}
