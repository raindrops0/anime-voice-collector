# Scripts and agents

A script or an AI agent can read a workspace, suggest labels, add episodes and start exports, through the command line or over HTTP while `avoc app` runs. Both go through the same checks as the page.

**Who confirms labels.** Suggestions are not labels: the machine does not learn from them and they are not exported until a person accepts them. The operations that write confirmed labels are kept apart: on the command line they need `--confirmed`, and over HTTP they are not in the agent's address (`/api/agent/commands`). This is an agreement, not a lock: the app runs only on this machine and does not check who is calling, so a tool that passes `--confirmed`, or calls the page's own address, can still write labels. Give an agent only the agent operations.

## Revisions and request IDs

- A **revision** is a number that changes when confirmed labels, characters or processed episodes change. Read it first, and pass it back with a change as `--expected-revision`; a change based on older data is refused.
- A **request ID** names one action. Use a new one for each action, and keep it when retrying that same action after a lost response. Reusing an ID for different input is refused.
- A successful retry does not repeat the action: it returns the same step, suggestion or job, with that step's lines and the workspace overview as they are now, even when the workspace has changed since.

## On the command line

`avoc workspace` reads JSON and writes JSON without opening a browser:

```powershell
uv run avoc workspace workspace state
```

The first `workspace` is the command, the second is the workspace folder, the third is the operation. Fields come from a UTF-8 JSON file given with `--input`. Errors are written as JSON, with `code` `revision_conflict` or `invalid_request` and a `detail`.

### Queries

| Operation | Fields | Answer |
| --- | --- | --- |
| `state` | none | The workspace overview and its `revision` |
| `clips` | `episode`, `role` (a character name or fixed ID), `status`, `limit` (1 to 200, default 50), `cursor` | `revision`, `items` and `next`. Pass `next` as `cursor` to continue; if the revision changed, start the list again |
| `clip` | `id`, optional `context` (0 to 5 neighboring lines on either side) | The line, its text, nearby lines and media addresses |
| `suggestions` | none | The newest 100 suggestions, newest first, each with its `status` |
| `jobs` | none | Recent episode adds and exports |

### Suggesting labels

`suggestion.json`:

```json
{"actor": "my-agent", "changes": [{"clip": "CLIP_ID", "label": "CHARACTER_ID"}]}
```

```powershell
uv run avoc workspace workspace suggest --input suggestion.json --request-id my-suggestion-1 --expected-revision 12
```

A person reviews the suggestion and reads the latest state. To accept it, put `{"suggestion": "SUGGESTION_ID"}` in `accept.json`, then give the current revision and `--confirmed`:

```powershell
uv run avoc workspace workspace accept --input accept.json --request-id confirm-1 --expected-revision 12 --confirmed
```

### Changes a person makes

These need `--confirmed`, like `accept`:

| Operation | Fields |
| --- | --- |
| `label` | `clips`, `label`, optional `new_role` and `unusable` (low quality) |
| `changes` | A list under `changes`. Each entry is `clip` with `label`; or `clip` with `reject` and boolean `on`; or `clip` with boolean `unusable` |
| `role` | `name`, optional `new_name`, `color` and `target` |
| `undo` | none |
| `revert` | `batches`: the step numbers to take back, as the history shows them |

### Episodes and exports

| Operation | Fields |
| --- | --- |
| `add` | `video`, `subtitles`, optional `name`, `offset`, `styles`, `spoken` and `display_subtitles` ([what they mean](commands.md#add)) |
| `export` | `roles`, `out`, optional `include_auto` and `form` (`folder` or `gpt-sovits`) |
| `cancel`, `resume` | `{"id": "JOB_ID"}` |

`add` and `export` return a saved job ID; run `jobs` to follow it. Command-line jobs continue after the command exits. Cancelling a command-line add is checked between processing steps, so it may finish the current step first. A failed export can be continued only into the same output folder, still empty, or into its own completed output; to change the selection or output, start a new export.

## Over HTTP

With `avoc app` running, the same operations are available at its address.

- `GET /api/agent/capabilities` gives the version and the input schemas.
- Queries: `GET /api/agent/state`, `/api/agent/clips`, `/api/agent/clips/{id}`, `/api/agent/suggestions`, `/api/agent/jobs` and `/api/agent/jobs/{id}`. Query fields go in the address, as for `clips` above.
- `POST /api/agent/commands` takes `operation` (`suggest`, `add` or `export`), `payload`, `request_id` and optional `expected_revision`.
- The page's own changes use `POST /api/commands`, with the same body and the operation names of [changes a person makes](#changes-a-person-makes).
- Jobs are stopped or continued with `POST /api/jobs/{id}/cancel` or `/resume`.

A revision conflict returns HTTP 409 with code `revision_conflict`; invalid input returns 400 or 422 with code `invalid_request`.

Where the workspace keeps all this, and how to back it up, is in [data files](../HOW_IT_WORKS.md#data-files).
