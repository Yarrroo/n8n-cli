# Mind Map — Code Topology

## Entry point → command layer
`n8n_cli/main.py` — mounts 12 Typer sub-apps:
  instance, auth, project, folder, workflow, node, connection,
  pin-data, execution, execution-data, credential, setup
Each sub-app lives in `commands/<resource>.py`.

## Command layer → API layer
`commands/*.py` → `api/public.py` (PublicApi) or `api/frontend.py` (FrontendApi)
Both delegate to `api/transport.py` (Transport) — single httpx.Client per invocation.

## Transport routing
`api/transport.py` auto-selects backend by path prefix:
  `/api/v1/*` → public (API-key header)
  `/rest/*`   → frontend (n8n-auth cookie)
`api/capabilities.py` — capability → backend map; commands never hardcode routing.

## Mutation pattern (fetch → mutate → PUT/PATCH)
`core/patcher.py` (WorkflowPatcher) — owns the atomic edit cycle used by:
  workflow, node, connection, pin-data commands
`core/paths.py` — folder-path ↔ folderId resolver (per-session cache via /tree endpoint)
`core/dotset.py` — dot-notation path writer for `--set a.b.c=v` patches
`core/refs.py` — node/folder reference resolution (--name vs --id)
`core/runpath.py` — execution path helpers
`core/node_types.py`, `core/cred_types.py` — type name helpers

## Output layer
`output/summarize.py` — shared summarizer (2 MB → ≤1 KB); used by execution-data get,
  pin-data get --summarize, workflow get --structure
`output/jsonout.py` — JSON stdout helpers
`output/schema_infer.py` — schema inference for summarizer

## Config / auth
`config/store.py` — reads/writes `~/.config/n8n-cli/config.yaml`
`config/instance.py` — Instance model (url, api_key, email, password)
`config/sessions.py` — session cookie persistence (chmod 600)

## Models
`models/` — hand-written Pydantic v2 models for n8n shapes
`models/_generated/` — auto-generated from n8n OpenAPI (datamodel-code-generator); excluded from mypy/ruff

## Tests
`tests/unit/` — pure unit tests, no network
`tests/integration/` — VCR cassette-based; cassettes in `tests/integration/cassettes/`
`tests/acceptance/` — success-criteria checks; may need live N8N_CLI_TEST_INSTANCE

## Resources embedded in package
`n8n_cli/resources/` — SKILL.md, claude-md-snippet.md, slash-n8n.md (shipped with wheel)

## External dependency
n8n instance over HTTPS — public API (/api/v1) + frontend API (/rest). No other external services.
