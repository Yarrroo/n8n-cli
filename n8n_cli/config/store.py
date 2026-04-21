"""Config file I/O at ~/.config/n8n-cli/config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field

from n8n_cli.api.errors import UserError
from n8n_cli.config.instance import Instance


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_instance: str | None = None
    instances: dict[str, Instance] = Field(default_factory=dict)


def config_dir() -> Path:
    return user_config_path("n8n-cli")


def config_path() -> Path:
    return config_dir() / "config.yaml"


def sessions_dir() -> Path:
    return config_dir() / "sessions"


def load() -> Config:
    """Load config from disk. Returns empty Config if file missing."""
    path = config_path()
    if not path.exists():
        return Config()
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Config.model_validate(raw)


def save(cfg: Config) -> None:
    """Write config, creating parent dir if needed. File mode 600."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _to_yaml_safe(cfg)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    path.chmod(0o600)


def get_instance(name: str, cfg: Config | None = None) -> Instance:
    cfg = cfg or load()
    if name not in cfg.instances:
        known = ", ".join(sorted(cfg.instances)) or "(none)"
        raise UserError(
            f"instance '{name}' not found",
            hint=f"known instances: {known}. Add one with `n8n-cli instance add`.",
        )
    return cfg.instances[name]


def resolve_active(
    name_override: str | None = None, cfg: Config | None = None
) -> tuple[str, Instance]:
    """Return (name, instance) for the active instance.

    Resolution order: explicit override → cfg.current_instance → error.
    """
    cfg = cfg or load()
    chosen = name_override or cfg.current_instance
    if chosen is None:
        raise UserError(
            "no active instance",
            hint="Set one with `n8n-cli instance use <name>` or pass --instance <name>.",
        )
    return chosen, get_instance(chosen, cfg)


def _to_yaml_safe(cfg: Config) -> dict[str, object]:
    """Model → plain dict, unwrapping SecretStr for storage."""
    out: dict[str, object] = {"current_instance": cfg.current_instance, "instances": {}}
    instances: dict[str, object] = {}
    for name, inst in cfg.instances.items():
        instances[name] = {
            "url": str(inst.url),
            "api_key": inst.api_key.get_secret_value() if inst.api_key else None,
            "email": inst.email,
            "api_key_expires": inst.api_key_expires,
        }
    out["instances"] = instances
    return out
