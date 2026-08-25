# n8n-cli

A Python CLI that makes n8n workflows AI-manageable. n8n stores workflows as monolithic JSON and
execution data can be multi-MB per node — raw dumps blow an LLM context window. This CLI is a smart
client over n8n's REST API: node/connection/pin-data/folder-level operations (parse client-side,
write back whole), summarized execution data (2 MB node payload → ≤1 KB by default), multiple named
instances with per-instance auth.

**Source of truth is always n8n** — no local workflow cache, live client only. Export/import is
opt-in for backup/git/migration.

## Status
v0.1.0 shipped (see CHANGELOG.md). Verified against n8n public API `1.1.1`.

## Stack
Python 3.11 · Typer · httpx · pydantic · jsonpath-ng · PyYAML · uv.
Config `~/.config/n8n-cli/config.yaml` (multi-instance) + the hub's 4-tier `.env` probe
(env vars → cwd-walk `.env` → `/Volumes/config/.env` → `~/.config/n8n-cli/config.env`).
Sessions `~/.config/n8n-cli/sessions/<instance>.session` (chmod 600). Env overrides:
`N8N_URL`, `N8N_API_KEY`, optional `N8N_EMAIL`/`N8N_PASSWORD` for non-interactive login.

## Structure
- `n8n_cli/api/` — `public.py` + `frontend.py` + `transport.py` (auth, pagination, error mapping,
  backend selection) + `capabilities.py` (capability → backend map; commands never hardcode routing)
- `n8n_cli/commands/` — one Typer sub-app per resource: instance, auth, project, folder, workflow,
  node, connection, pin-data, execution, execution-data, credential, setup, doctor
- `n8n_cli/core/` — `WorkflowPatcher` (fetch → mutate → write, rename-cascade, folder-move),
  folder-path ↔ id resolver
- `n8n_cli/output/` — the one shared summarizer (used by execution-data, pin-data, workflow structure)
- `tests/` — unit + VCR-replay integration + acceptance

## The canonical debug loop (design driver)

Every feature must serve this loop without bloating context:

```
workflow structure W → execution list → execution-data get (summarized)
  → node get → credential list --for-node → node patch → pin-data set
  → workflow execute --wait → execution-data get (verify) → repeat
```

If a command's default output would break this loop (too large, too noisy), it's wrong.
Default to summaries; `--full` is the escape hatch.

## Dual-API reality

n8n has two distinct APIs. The public one is incomplete; **the frontend API is required, not a
fallback.** Routing is automatic in the transport layer; `--verbose` reveals which backend handled
a call.

| Surface | Path | Auth | Role |
|---|---|---|---|
| Public API | `/api/v1/*` | `X-N8N-API-KEY: <JWT>` header | Workflows, executions, tags, basic credential ops. Spec at `/api/v1/openapi.yml` |
| Frontend API | `/rest/*` | `n8n-auth` cookie from `POST /rest/login` | **Required for** folders, credential list/get, workflow execute (`/run`), share, `from-url`, `new` |

License gates seen in the wild: `feat:projectRole:admin` (403s `GET /api/v1/projects` on
community/single-team installs) · `feat:folders` (required for folder endpoints).

### Public API (1.1.1) — confirmed endpoints

- **Workflows**: `GET /workflows` (query: `active`, `tags`, `name`, `projectId`,
  `excludePinnedData`, `limit`, `cursor`) · `POST /workflows` · `GET /workflows/{id}` ·
  **`PUT /workflows/{id}` (FULL REPLACE — no PATCH)** · `DELETE` · `POST …/activate|deactivate` ·
  `PUT …/transfer` · `GET|PUT …/tags` · `GET /workflows/{id}/{versionId}`
- **Executions**: `GET /executions` (`includeData`, `status`, `workflowId`, `projectId`, paging) ·
  `GET /executions/{id}?includeData=true` · `DELETE` · `POST …/retry`
- **Credentials**: `POST` · `DELETE` · `GET /credentials/schema/{type}` · `PUT …/transfer`.
  **No list/get/update** → frontend API mandatory.
- **Tags**: full CRUD. **Projects**: CRUD (license-gated). **Variables**: CRUD.
  **Source-control**: `POST /source-control/pull` (gated). **Audit**: `POST /audit`.
- Cursor pagination everywhere: `?limit=N&cursor=…` → `{"data":[…], "nextCursor":"…"}`; null → done.

### Frontend API (`/rest`) — endpoints the CLI speaks

Discovered via n8n source (`packages/cli/src/controllers/`) + live probe:

- **Folders** (base `/rest/projects/:projectId/folders`, licensed `feat:folders`):
  `POST /` create (`{name, parentFolderId?}`) · `GET /` list · `GET /:id/tree` (path-to-root) ·
  `GET /:id/content` (children) · `GET /:id/credentials` · `PATCH /:id` (rename+retag) ·
  `DELETE /:id?transferToFolderId=…` · `PUT /:id/transfer` (move to another project)
- **Workflow ↔ folder**: `POST /rest/workflows` accepts `parentFolderId`;
  `PATCH /rest/workflows/:id` with `parentFolderId` **is how a workflow moves between folders**
  (the public PUT does not carry the field); `GET /rest/workflows?parentFolderId=<id|0>`.
- **Other frontend-only**: `POST /rest/workflows/:id/run` (public API has no execute endpoint) ·
  `PUT …/share` · `GET /rest/workflows/new` · `GET /rest/workflows/from-url` ·
  `GET /rest/credentials` + `GET|PATCH /rest/credentials/:id` ·
  `POST /rest/login`, `POST /rest/logout`, `GET /rest/login` (session check).

When a frontend capability is unclear: grep the saved spec + read the controller on GitHub, then
log the newly-discovered endpoint here so this map grows.

## Architecture rules

- **Fetch → mutate → PUT (public) / PATCH (frontend)**: all node/connection/pin-data edits fetch
  the full workflow, mutate locally, write back atomically. Renaming a node cascades through
  `connections{}` (node-name is both object key and nested value) AND `pinData{}`.
- **`pinData` is a field inside the workflow JSON**, not a separate resource.
- **No hard delete for workflows** — `workflow archive` sets `isArchived: true`.
- **Concurrency**: last-write-wins, documented and acceptable for a single-AI debug tool.
  On 409/412, surface clearly; never auto-retry silently.
- **Instance scoping**: every IO-touching command accepts `--instance`; falls back to
  `current_instance`; errors clearly if neither.
- `/rest` calls must survive cookie expiry: automatic re-login path, visible in `--verbose`.

## Output contract

- Default: stable JSON on stdout. `--human` for tables.
- Errors on stderr; exit codes: 2 user error · 3 API error · 4 auth error · 5 license-gated.
- Credential secret values never returned. Binary payloads → metadata only, never base64.
- Execution-data summary shape:
  `{"execution_id","node","status","duration_ms","output":{"item_count","total_size_bytes","schema","sample":[…],"truncated"}}`

## Conventions

- Node addressing: prefer `--name`; `--id` fallback. Folder addressing: prefer
  `--folder-path "A/B/C"` (resolved via `/tree`); `--folder <id>` fallback.
- Verbs: `list/get/add/patch/delete/archive/link/publish/execute/export/import/copy/use/current/move/tree/content/path`. Don't invent synonyms.
- Patch modes: dot-notation (`--set parameters.url=…`), JSON merge (`--json`), full replace
  (`--file`) — all end in a single write.

## Anti-patterns

- ❌ Caching workflows locally by default (a per-session folder-path cache is fine; a workflow cache isn't).
- ❌ Dumping raw execution data by default.
- ❌ Hardcoding public-vs-frontend inside command modules — routing lives in transport/capabilities.
- ❌ Echoing credential secrets anywhere.
- ❌ Silent API fallback without `--verbose` visibility.

## Verification

```bash
uv run --extra dev pytest -q   # full suite, offline (VCR replay); pytest lives in the dev extra
n8n-cli doctor --human    # install state, config sources, connectivity
n8n-cli auth status       # both backends against the active instance
```
