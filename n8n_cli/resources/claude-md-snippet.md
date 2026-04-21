<!-- n8n-cli:begin -->
## n8n workflow management

`n8n-cli` is installed and available in this environment. Use it whenever
the user asks about n8n workflows, nodes, executions, credentials, or
folders. Full guidance lives in the `n8n-cli` skill at
`~/.claude/skills/n8n-cli/SKILL.md`.

Quick reference:
- Default output is JSON on stdout (pipe to `jq`).
- Exit codes: 0/1/2/3/4/5 (success/unimplemented/user/api/auth/capability).
- Prefer `workflow archive` over `workflow delete --force`.
- Use `--verbose` to see which backend (public `/api/v1` vs frontend
  `/rest`) handled a call.
- Execution data summarizes to ≤1 KB by default; pass `--full` only when
  summarization hides what you need.
<!-- n8n-cli:end -->
