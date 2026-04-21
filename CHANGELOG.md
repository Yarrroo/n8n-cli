# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] — first public release

### Added
- Full command surface per `task.md`: instances, auth, projects, folders,
  workflows (incl. `execute`, `copy`, `move`, `link`, `projects`), nodes,
  connections, pin-data, executions, execution-data, credentials.
- Dual-API transport: public `/api/v1` (JWT) + frontend `/rest` (session
  cookie) with automatic routing and `--verbose` backend attribution.
- Summarizer: 2 MB+ node output → ≤1 KB stdout by default (schema + sample
  + truncation metadata). Binary payloads render as metadata, never base64.
- `WorkflowPatcher` — atomic fetch → mutate → PUT with rename-cascade
  through connections + pinData.
- Folder support (list / tree / path / content / add / patch / delete /
  move), plus `workflow move --folder-path "A/B/C"`.
- `workflow add --folder` / `--folder-path` / `--project` ergonomics.
- `pin-data set --data '<inline-json>'` (alternative to `--file`).
- `workflow execute --input '{...}'` for `runData` pinned items.
- `workflow move --id` (accepts positional arg or `--id`), plus
  `--to-folder` / `--to-path` aliases.
- `n8n-cli setup install|uninstall|status` — drops a Claude Code skill
  and slash-command into `~/.claude/`, sets up config dirs, optionally
  appends a hint block to `~/.claude/CLAUDE.md`.
- 134 tests: unit + integration (VCR replay) + acceptance covering all
  task.md success criteria.

### Notes
- Workflow edits use PUT (public API has no PATCH).
- Hard `workflow delete --force` is supported but gated — `workflow
  archive` is the default path.
- `workflow unlink` surfaces a clear capability error on community /
  single-project licenses.
