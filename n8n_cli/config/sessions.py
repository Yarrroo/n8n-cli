"""Per-instance frontend session storage.

Layout: `~/.config/n8n-cli/sessions/<instance>.session` (YAML, chmod 600).

We only store what's needed to reissue authenticated requests:
  cookie: n8n-auth=<JWT>
  expires_at: ISO-8601 (informational)
  user_id: uuid
  personal_project_id: project id (cached so folder cmds avoid a round-trip)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from n8n_cli.config.store import sessions_dir


class Session(BaseModel):
    model_config = ConfigDict(extra="allow")

    cookie: str
    expires_at: str | None = None
    user_id: str | None = None
    personal_project_id: str | None = None


def _path(instance_name: str) -> Path:
    return sessions_dir() / f"{instance_name}.session"


def save(instance_name: str, session: Session) -> None:
    path = _path(instance_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(session.model_dump(mode="json"), f, default_flow_style=False)
    path.chmod(0o600)


def load(instance_name: str) -> Session | None:
    path = _path(instance_name)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not raw.get("cookie"):
        return None
    return Session.model_validate(raw)


def clear(instance_name: str) -> None:
    path = _path(instance_name)
    if path.exists():
        path.unlink()
