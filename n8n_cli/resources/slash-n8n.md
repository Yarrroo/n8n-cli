---
description: Drive n8n-cli for workflow inspection, debugging, and editing
argument-hint: [natural-language task — e.g. "find the failing HTTP node in workflow W and fix its URL"]
---

You have access to `n8n-cli`, an AI-first CLI for n8n.

First-run checks (skip if already confirmed this session):
- `n8n-cli --version`
- `n8n-cli instance current` — must return an active instance
- `n8n-cli auth status` — both public (JWT) and frontend (session) should
  be authenticated; if frontend is false, run
  `n8n-cli auth login --email <e> --password-stdin` (read password
  securely; never echo it back)

For the user's task below, follow the canonical debug loop when
troubleshooting, and default to summarized output. Use `--full` only when
summarization hides relevant detail. Never hard-delete workflows — prefer
`workflow archive`.

Task: $ARGUMENTS
