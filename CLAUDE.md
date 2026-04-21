# n8n CLI — Project Context

## What this is

A Python CLI that makes n8n workflows AI-manageable. n8n stores workflows as monolithic JSON and execution data can be multi-MB per node — feeding that raw into an LLM context blows the window. This CLI is a smart client over n8n's REST API that:

- Offers **node-level, connection-level, pin-data-level, folder-level** operations (parses JSON client-side, PUTs full workflow back).
- **Summarizes** execution data (schema + sample, not raw dumps). Goal: ≤1KB default output for a 2MB node payload.
- Manages **multiple named instances** (prod/staging/local) with per-instance auth.

**Source of truth is always n8n** — no local workflow cache. Live client only. Export/import is opt-in for backup/git/migration.

## Instance-specific context

- **Target instance**: configured via `.env` or `n8n-cli instance add`. See [`.env.example`](.env.example) for the required variables.
- **Public API version**: verified against n8n `1.1.1`.
- **JWT expiry**: `auth status` surfaces a warning when <7 days remain.
- **License gates observed in the wild**: `feat:projectRole:admin` (blocks `GET /api/v1/projects` with 403 on community/single-team installs), `feat:folders` (required for folder endpoints — present on most current n8n builds). Folder support is a hard requirement, not nice-to-have.

## Canonical debug loop (design driver)

Every feature must serve this loop without bloating context:

```
workflow structure W → execution list → execution-data get (summarized)
  → node get → credential list --for-node → node patch → pin-data set
  → workflow execute --wait → execution-data get (verify) → repeat
```

If a command's default output would break this loop (too large, too noisy), it's wrong. Default to summaries, require `--full` as escape hatch.

## Dual-API reality (updated after live probe)

n8n has two distinct APIs. The public one is incomplete for our purposes; **frontend API is required, not a fallback.**

| Surface | Path | Auth | Role |
|---|---|---|---|
| Public API | `/api/v1/*` | `X-N8N-API-KEY: <JWT>` header | Primary for workflows, executions, tags, basic credential ops. Documented at `/api/v1/openapi.yml`. |
| Frontend API | `/rest/*` | `n8n-auth` cookie from `POST /rest/login` with `{email,password}` | **Required for** folders, credential list/get, workflow execute (`/run`), share, `from-url`, `new`. |

Routing is automatic in the CLI transport layer; `--verbose` reveals which backend handled a call. If a frontend-only command is invoked without a session, auto-trigger `auth login` or fail with a clear fix-up message naming the missing capability.

## Public API (1.1.1) — confirmed endpoints

**Workflows**: `GET /workflows` (query: `active`, `tags`, `name`, `projectId`, `excludePinnedData`, `limit`, `cursor`) · `POST /workflows` · `GET /workflows/{id}` · **`PUT /workflows/{id}` (FULL REPLACE — no PATCH)** · `DELETE /workflows/{id}` · `POST /workflows/{id}/activate` · `POST /workflows/{id}/deactivate` · `PUT /workflows/{id}/transfer` · `GET|PUT /workflows/{id}/tags` · `GET /workflows/{id}/{versionId}`

**Executions**: `GET /executions` (query: `includeData`, `status`, `workflowId`, `projectId`, `limit`, `cursor`) · `GET /executions/{id}?includeData=true` · `DELETE /executions/{id}` · `POST /executions/{id}/retry`

**Credentials**: `POST /credentials` · `DELETE /credentials/{id}` · `GET /credentials/schema/{type}` · `PUT /credentials/{id}/transfer`. **No list/get/update** → frontend API mandatory.

**Tags**: full CRUD at `/tags`.
**Projects**: CRUD at `/projects` (gated by `feat:projectRole:admin` on our instance).
**Variables**: CRUD.
**Source-control**: `POST /source-control/pull` (gated).
**Audit**: `POST /audit`.

Cursor pagination everywhere: request `?limit=N&cursor=...`; response `{"data":[...], "nextCursor":"..."}`; null → done.

## Frontend API (`/rest`) — endpoints the CLI must speak

Discovered via n8n source (`folder.controller.ts`, `workflows.controller.ts`) + live probe. These are the ones we need:

**Folders** (base path `/rest/projects/:projectId/folders`, licensed `feat:folders`):
- `POST /rest/projects/:projectId/folders/` — create (body: `{name, parentFolderId?}`)
- `GET /rest/projects/:projectId/folders/` — list (query: `ListFolderQueryDto`: filter, sort, page)
- `GET /rest/projects/:projectId/folders/:folderId/tree` — path-to-root for breadcrumbs
- `GET /rest/projects/:projectId/folders/:folderId/content` — children (sub-folders + workflows)
- `GET /rest/projects/:projectId/folders/:folderId/credentials` — credentials in folder
- `PATCH /rest/projects/:projectId/folders/:folderId` — rename + retag
- `DELETE /rest/projects/:projectId/folders/:folderId?transferToFolderId=...` — remove (optional content transfer)
- `PUT /rest/projects/:projectId/folders/:folderId/transfer` — move folder to another project

**Workflow ↔ folder** (via frontend `/rest/workflows`):
- `POST /rest/workflows` accepts `parentFolderId` on create.
- `PATCH /rest/workflows/:id` accepts `parentFolderId` → **this is how we move a workflow between folders**. Public API's `PUT` does not carry this field.
- `GET /rest/workflows?parentFolderId=<id|0>` — list workflows in a folder (`0` or root alias for top-level).

**Other frontend-only**:
- `POST /rest/workflows/:id/run` — trigger execution (public API 1.1.1 has no execute endpoint).
- `PUT /rest/workflows/:id/share` — share with projects.
- `GET /rest/workflows/new` — generate a unique name.
- `GET /rest/workflows/from-url` — import from URL.
- `GET /rest/credentials` + `GET /rest/credentials/:id` — full credential list/get.
- `PATCH /rest/credentials/:id` — update (public API PR #18082 will add this later; until then, frontend only).
- `POST /rest/login`, `POST /rest/logout`, `GET /rest/login` (session check).

## Architecture rules

- **Fetch → mutate → PUT (public) / PATCH (frontend)**: all node/connection/pin-data/folder-assignment edits fetch the full workflow, mutate locally, write back atomically in one call. Renaming a node cascades through `connections{}` (where node-name is the object key *and* a nested value) AND `pinData{}`.
- **`pinData` is a field inside the workflow JSON**, not a separate resource. `pin-data *` commands manipulate `workflow.pinData[nodeName]`.
- **`workflow archive`**: set `isArchived: true` via PUT. Don't hard-delete.
- **Concurrency**: last-write-wins. Documented, acceptable for single-AI debug tool. On 409/412 from n8n, surface clearly; don't auto-retry silently.
- **Instance scoping**: every IO-touching command accepts `--instance <name>`; falls back to `current_instance`; errors clearly if neither.
- **Automatic transport selection**: command → high-level API method → transport decides public vs frontend based on a capability map. Commands stay backend-agnostic.

## Command surface delta (vs. task.md)

Additions required by folder support on this instance:

```
folder list --project P [--parent ID]
folder get --project P --id F                    # metadata + breadcrumb via /tree
folder tree --project P --id F                   # full subtree (for AI navigation)
folder content --project P --id F                # children (sub-folders + workflows)
folder add --project P --name "..." [--parent ID]
folder patch --project P --id F --set name="..." [--tags ...]
folder delete --project P --id F [--transfer-to G]
folder move --project P --id F --to-project P2   # PUT /transfer
folder path --project P --id F                   # resolve human-readable path

workflow list ... [--folder F | --folder-path "Ops/Billing"]   # add folder filter
workflow move --id W --to-folder F               # PATCH parentFolderId
workflow move --id W --to-path "Ops/Billing"     # human-friendly alias
workflow add ... [--folder F | --folder-path "..."]
```

**Folder addressing**: prefer human-readable `--folder-path "A/B/C"` (resolved via `/tree`), with `--folder <id>` as escape hatch. Mirrors our `--name` preference for nodes.

## Tech stack (locked)

- Python 3.11 · Typer · httpx · pydantic · jsonpath-ng · PyYAML
- Config: `~/.config/n8n-cli/config.yaml`
- Sessions: `~/.config/n8n-cli/sessions/<instance>.session` (chmod 600, holds `n8n-auth` cookie + CSRF if needed)
- Env overrides: `N8N_URL`, `N8N_API_KEY` (+ optional `N8N_EMAIL`/`N8N_PASSWORD` for non-interactive session login in CI)

## Output contract

- **Default: JSON on stdout** (AI-friendly, stable schema). `--human` for pretty tables.
- Errors on stderr, proper exit codes (2 = user error, 3 = API error, 4 = auth error, 5 = capability/license gated).
- Credential secret values **never** returned from `get`.
- Binary payloads → metadata only (`mime_type`, `file_name`, `size_bytes`) — never base64.

Execution-data summary shape (default):
```json
{"execution_id","node","status","duration_ms",
 "output":{"item_count","total_size_bytes","schema","sample":[...],"truncated"}}
```

## Conventions

- **Node addressing**: prefer `--name` (human-readable); `--id` as fallback.
- **Folder addressing**: prefer `--folder-path "A/B/C"`; `--folder <id>` as fallback.
- **Verbs**: `list/get/add/patch/delete/archive/link/publish/execute/export/import/copy/use/current/move/tree/content/path`. Don't invent synonyms.
- **Patch modes**: dot-notation (`--set parameters.url=...`), JSON merge (`--json '{...}'`), or full replace (`--file`). Dot-notation writes to the in-memory workflow then sends a single PUT.
- **Workflow ↔ project** is many-to-many (but our instance API enforces single project per workflow via `PUT /workflows/{id}/transfer`). Keep `link`/`unlink` API surface; implementation may collapse to transfer when M:N isn't granted by license.
- **No hard delete for workflows** — archive only.

## Resource model

```
instance
  └── project
       ├── folder (tree; nested)
       │    └── folder…
       ├── workflow (has parentFolderId)
       │    ├── node
       │    ├── connection
       │    ├── pin-data  (inline on workflow.pinData)
       │    └── execution
       │         └── execution-data (per node, summarized)
       └── credential (list/get require /rest)
```

## Development guidance

- **Package layout** (when scaffolded): `n8n_cli/{cli,api,models,commands,config,output}`.
  - `api/public.py` + `api/frontend.py` + `api/transport.py` — transport owns auth, pagination, error mapping, backend selection.
  - `api/capabilities.py` — map of "capability → backend" so commands never hardcode routing.
  - `commands/` — one Typer sub-app per resource (project, folder, workflow, node, connection, pin-data, execution, execution-data, credential, instance, auth).
  - `models/` — pydantic, ideally generated from the upstream n8n OpenAPI spec (`GET /api/v1/openapi.yml` on any instance) with hand-written extensions for frontend-only shapes (folder, `parentFolderId`, run response).
  - `output/summarize.py` — **one** shared summarizer reused by `execution-data get`, `pin-data get --summarize`, `workflow get --structure`.
  - `core/patcher.py` — `WorkflowPatcher` class owning fetch → mutate → write, rename-cascade, folder-move.
  - `core/paths.py` — folder-path ↔ folderId resolver with small per-session cache (it's cheap to look up via `/tree`).
- **Exploration tactic for frontend API**: when a capability is unclear, grep the saved spec + read the relevant controller on GitHub (`n8n-io/n8n/packages/cli/src/controllers/`). Log every newly-discovered endpoint in this file under the frontend section above so the spec grows as we go.
- **Success criterion reminder**: `pip install` works; covers all listed commands incl. folders; dual-API routing works; 2MB+ node output summarizes to ≤1KB by default; debug loop works end-to-end against 2+ instances.

## Anti-patterns to avoid

- ❌ Caching workflows locally by default (breaks "n8n is source of truth"). A folder-path cache per session is fine; a workflow cache isn't.
- ❌ Dumping raw execution data by default (breaks the whole reason this tool exists).
- ❌ Hardcoding "public vs frontend" inside command modules — all routing lives in the transport/capability layer.
- ❌ Echoing credential secrets anywhere.
- ❌ Silent fallback between APIs without `--verbose` visibility.
- ❌ Inventing verbs outside the reference list.
- ❌ Building MCP/RBAC/webhook features now.
- ❌ Using `/rest` without a session-refresh check — cookies expire, re-login path must be automatic & visible in `--verbose`.

## Status

v0.1.0 — first public release. Full command surface implemented, 134 tests green, dual-API routing live, summarizer meets 2 MB → ≤1 KB budget, canonical debug loop works end-to-end. See [CHANGELOG.md](CHANGELOG.md) for details.
