# n8n-cli

**AI-friendly CLI for n8n.** Node-level workflow operations and summarized
execution data — designed so an LLM (e.g. Claude Code) can read, modify,
execute, and debug n8n workflows without blowing its context window on
multi-megabyte JSON payloads.

- Parses workflow JSON client-side → act at node / connection / pin-data
  granularity.
- Summarizes execution data: **2 MB node output → ≤1 KB** stdout by default
  (schema + sample + truncation metadata).
- Dual-API: public `/api/v1` (JWT) + frontend `/rest` (session cookie),
  routed automatically. `--verbose` reveals which backend handled a call.
- Multi-instance (prod / staging / local) with per-instance auth.
- JSON on stdout by default (pipe to `jq`); `--human` for tables.
- Stable exit codes: 0 / 1 / 2 / 3 / 4 / 5 (success / unimplemented /
  user / api / auth / capability-gated).

## Install

```bash
pipx install n8n-cli          # once per machine
n8n-cli setup install         # once per Claude Code — installs skill + /n8n slash
n8n-cli instance add prod --url https://n8n.your-domain.com --api-key <JWT> --use
n8n-cli auth login --email you@example.com --password-stdin
```

After `setup install`, Claude Code picks up n8n-cli automatically via a
skill (`~/.claude/skills/n8n-cli/SKILL.md`) — no CLAUDE.md edits required.
Pass `--with-claude-md` to also append a hint block to `~/.claude/CLAUDE.md`.

### Developer install

```bash
git clone https://github.com/Yarrroo/n8n-cli
cd n8n-cli
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest                        # 134+ tests, ~5 s offline (VCR replay)
```

## Usage

### Canonical AI debug loop

Every workflow fix follows this 9-step pattern. All outputs are ≤1 KB by
default:

```bash
n8n-cli workflow structure W                           # 1. graph
n8n-cli execution list --workflow W --limit 5          # 2. find failure
n8n-cli execution-data get <EID> --node N              # 3. summarized output
n8n-cli node get --workflow W --name N                 # 4. read config
n8n-cli credential list --for-node "HTTP Request"      # 5. auth context
n8n-cli node patch --workflow W --name N --set parameters.url=...   # 6. fix
n8n-cli pin-data set --workflow W --node Upstream --data '[...]'    # 7. seed
n8n-cli workflow execute W --wait --timeout 60         # 8. re-run
n8n-cli execution-data get <NEW_EID> --node N          # 9. verify
```

### Command surface

```
n8n-cli instance       add | list | get | patch | delete | use | current
n8n-cli auth           login | logout | status
n8n-cli project        list | get | add | patch | delete | current
n8n-cli folder         list | get | tree | content | path | add | patch | delete | move
n8n-cli workflow       list | get | structure | add | patch | archive | unarchive |
                       publish | unpublish | execute | export | import | copy |
                       link | unlink | projects | move | delete
n8n-cli node           list | get | add | patch | delete | enable | disable
n8n-cli connection     list | add | delete
n8n-cli pin-data       list | get | set | delete
n8n-cli execution      list | get | delete
n8n-cli execution-data get --sample / --head / --path / --schema-only / --full
n8n-cli credential     list | get | add | patch | delete | schema
n8n-cli setup          install | uninstall | status
```

`n8n-cli <resource> --help` for the full flag set.

### Summary output shape

```json
{
  "execution_id": "1234",
  "node": "Fetch Users",
  "status": "success",
  "duration_ms": 450,
  "output": {
    "item_count": 250,
    "total_size_bytes": 2400000,
    "schema": {"id": "string", "name": "string", "email": "string"},
    "sample": [{"id": "u_1", "name": "Alice", "email": "alice@x.com"}],
    "truncated": true
  }
}
```

Pass `--full` for the raw payload, `--path "items[0].field"` for JSONPath
extraction, `--schema-only` to skip samples, `--head N` for the first N
items.

## Configuration

| Location | Purpose |
|---|---|
| `~/.config/n8n-cli/config.yaml` | Instances + active selection |
| `~/.config/n8n-cli/sessions/<name>.session` | Frontend session cookies (chmod 600) |
| `$N8N_URL`, `$N8N_API_KEY` | Env overrides (win over config) |
| `$N8N_EMAIL`, `$N8N_PASSWORD` | Optional — enables non-interactive session login in CI |

## Claude Code integration

`n8n-cli setup install` drops two things under `~/.claude/`:

- **Skill** at `skills/n8n-cli/SKILL.md` — Claude activates it whenever
  you mention n8n workflows, executions, nodes, credentials, or folders.
  No context tax on unrelated sessions.
- **Slash-command** at `commands/n8n.md` — run `/n8n <task>` in Claude
  Code to drive the CLI directly.

Removal: `n8n-cli setup uninstall` (leaves the installed Python package
alone — `pipx uninstall n8n-cli` to remove that).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Unimplemented (reserved) |
| 2 | User error — bad flag / missing arg / validation |
| 3 | API error — 4xx / 5xx from n8n |
| 4 | Auth error — missing creds / expired token / no session |
| 5 | Capability gated — feature requires a license tier you don't have |

## Development

```bash
pytest                      # full suite
pytest -m 'not integration' # unit + acceptance only
ruff check . && ruff format --check .
mypy n8n_cli
pre-commit run --all-files
```

Integration tests replay from VCR cassettes (all `X-N8N-API-KEY` headers
are scrubbed). To record against your own instance:

```bash
export N8N_CLI_TEST_INSTANCE=dev
pytest -m integration --vcr-record=new_episodes
```

## Contributing

Issues and PRs welcome. Please keep:

- tests green (`pytest`),
- types clean (`mypy n8n_cli`),
- lint clean (`ruff check . && ruff format --check .`).

Credential secrets, session cookies, and internal URLs must never land in
commits. VCR cassettes should only hit example.com hosts.

## License

MIT — see [LICENSE](LICENSE).
