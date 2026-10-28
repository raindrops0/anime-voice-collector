# Contributing

Thanks for helping. Start with [docs/index.md](index.md): it lists every doc and what each one covers. Include the problem and relevant validation when proposing a change.

## Python side

Install [uv](https://docs.astral.sh/uv/) and FFmpeg, then `uv sync --locked`. Before sending a change, run:

```bash
uv run ruff check .
uv run ruff format --check .
uvx ty@0.0.91 check src
uv run pytest -q
```

The type checker is [ty](https://github.com/astral-sh/ty). It is not a project dependency, so `uvx` runs it on the fly, at the version CI uses. Changing only Python needs no Node, except when [shared interface types](#shared-interface-types) change.

## Web app

The labeling app is React and TypeScript, built with Vite, styled with Tailwind CSS and shadcn/ui components. The source is in `web/`. The built files in `src/avoc/app/static/` are committed, so people who only install the tool never need Node. Do not edit the built files by hand.

Set up once: install Node (the current long-term-support version), then

```bash
npm --prefix web ci
```

Day to day, run two terminals:

```bash
uv run avoc app WORKSPACE --no-open --reload
```

```bash
npm --prefix web run dev
```

Open the address Vite prints (it ends in `/static/`). Edits in `web/` show up in the page right away; requests to `/api` and `/media` go to the running `avoc app` on port 8765. If 8765 was taken, `avoc app` moves to another port and says so; then start Vite with that port in `AVOC_PORT` (in PowerShell, `$env:AVOC_PORT = 8766` first), or the page shows the workspace on 8765 instead. `--reload` restarts that server whenever a Python file in `src/avoc/` changes (it watches with watchfiles, from the dev dependency group). Each restart loads the workspace again, takes a few seconds, and stops an episode being added, so it is for development only.

Before committing a change in `web/`:

```bash
npm --prefix web run check
npm --prefix web run build
```

`check` runs oxlint (finds likely mistakes), Prettier (code layout; `npm --prefix web run format` fixes it), the type check and the tests. `build` writes `src/avoc/app/static/`; commit those files with your change. CI builds again and fails if they differ from the source.

If two branches both changed the built files, git shows a conflict there. Take either side, run `npm --prefix web run build`, and commit the result.

Browser tests open the real page in your installed Chrome, against a small made-up workspace, and click through it (Playwright). They need uv too, which starts the server for them. Run them after a change to how the page looks or works:

```bash
npm --prefix web run e2e
```

Style with Tailwind classes in the markup; there is no hand-written stylesheet. Use only the theme's color names (`bg-muted`, `text-success` and so on, set in `web/src/index.css`), never fixed colors. Before writing a new widget, look in `web/src/components/` for a shared one (`Choice`, `Chip`, `Tip`, `Note`…). To add a shadcn component:

```bash
npx --prefix web shadcn@latest add COMPONENT -c web
```

It is copied into `web/src/components/ui/`, where it can be changed like any other file; say so in a comment at the top when you do.

## Pictures and videos

No pictures, GIFs or videos are committed, so `git clone` stays small. Upload them as attachments to a comment on the GitHub issue for media, and link to their addresses from the Markdown.

The demo GIF at the top of the README is recorded by a script, so it can be made again after the interface changes: [web/demo/demo.spec.ts](../web/demo/demo.spec.ts) says how.

## Online demo

The [online demo](https://avoc-online-demo.onrender.com) runs in a small container, built from [raindrops0/avoc-online-demo](https://github.com/raindrops0/avoc-online-demo): every visitor labels their own copy of two short made-up Japanese episodes; adding episodes and exporting are turned off. Only adding episodes needs a graphics card, so the server runs without torch on a tenth of a CPU and in about 150 MB of memory, which fits a free web service on [Render](https://render.com) (a host that runs containers; it sleeps after 15 minutes without visitors and takes about a minute to wake). To make it again:

1. Start the [VOICEVOX engine](https://github.com/VOICEVOX/voicevox_engine/releases) on port 50021, then run `uv run python scripts/demo/make_episodes.py data/demo-episodes`. It reads [scripts/demo/script.json](../scripts/demo/script.json) aloud, lays a little music under it, and writes a video and Japanese subtitles for each episode.
2. Add both to a new workspace with `avoc add` (`--offset 0 --spoken ja`), then run `avoc quality` on it.
3. Run `uv run python scripts/demo/make_deploy.py WORKSPACE OUT`. `OUT` gets the [Dockerfile and README](../scripts/demo/deploy/), the workspace packed as a template with every line's vocals cut and the low-quality hint's starter weights, and a wheel of avoc. Whatever can be made ahead is, so the server only does what a visitor's clicks need: right after it starts, it labels a throwaway copy once (the first training loads its libraries) and keeps one fresh copy ready for the next visitor. Try it with `uv run python -m avoc.app.demo serve OUT/template`.
4. Push `OUT` to the git repository the host builds from. On Render, a web service on that repository (added as a public Git repository, region Singapore) with the Docker language and the Free instance type builds the Dockerfile; Render sets `PORT` itself. A public repository is not deployed again on its own: after a push, choose Manual Deploy, then Deploy latest commit.

The voices' terms ask for a credit, such as "VOICEVOX:ずんだもん". The page and the deploy README give it; keep it when changing either.

## README

The README comes in English (`README.md`) and Simplified Chinese (`README.zh.md`). When you change one, change the other in the same commit. The same holds for the guide pages in `docs/guide/` and their `.zh.md` copies. The other docs are in English only.

## Releases

A release is the Windows download described in [Install](guide/install.md). To make one, set `version` in `pyproject.toml`, commit, and push a tag with the same version, such as `v0.2.0`. The [release workflow](../.github/workflows/release.yml) builds the zip with [make_zip.ps1](../scripts/release/make_zip.ps1), installs it once to check it, and puts it on a draft release; read the draft's notes, then publish it. A push to `dev` or a pull request that changes `scripts/release/`, the workflow, `pyproject.toml` or `uv.lock` runs the same build and check, and keeps the zip for 7 days under the run's artifacts. To try the zip first, run `pwsh scripts/release/make_zip.ps1`, which packages the last commit (`-Ref (git write-tree)` packages what is staged), unzip it to an empty folder and double-click `start.bat`. The uv inside the zip is the version set in the workflow, and the uv on `PATH` when run by hand.

## Text in the web app

Both languages are written side by side as `tr(Chinese, English)` where the text is used. Use the terms in the [glossary](HOW_IT_WORKS.md#glossary), and follow the design rules in [docs/UI_DESIGN.md](UI_DESIGN.md).


## Shared interface types

After changing the main answer models in `src/avoc/contracts.py`, run `uv run python scripts/generate_contracts.py`, then format `web/src/generated.ts` with the web app's formatter. Commit that file and rebuild the front end. CI runs `uv run python scripts/generate_contracts.py --check` so Python and TypeScript cannot silently disagree. Business operations belong in `operations.py` and `service.py`; HTTP routes and command-line parsing call them rather than implementing their own label rules.
