"""Config load/save roundtrip + resolve_active behavior.

Uses a per-test temp config dir via monkeypatch so we never touch the real
`~/.config/n8n-cli/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from n8n_cli.api.errors import UserError
from n8n_cli.config import store
from n8n_cli.config.instance import Instance
from n8n_cli.config.store import Config


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setattr(store, "config_dir", lambda: cfg_dir)
    monkeypatch.setattr(store, "config_path", lambda: cfg_dir / "config.yaml")
    monkeypatch.setattr(store, "sessions_dir", lambda: cfg_dir / "sessions")


def test_load_returns_empty_when_missing() -> None:
    cfg = store.load()
    assert cfg.current_instance is None
    assert cfg.instances == {}


def test_save_load_roundtrip_preserves_api_key() -> None:
    cfg = Config(
        current_instance="dev",
        instances={
            "dev": Instance(url="https://n.example.com", api_key="k1", email="a@b.c"),  # type: ignore[arg-type]
        },
    )
    store.save(cfg)
    loaded = store.load()
    assert loaded.current_instance == "dev"
    assert str(loaded.instances["dev"].url) == "https://n.example.com/"
    assert loaded.instances["dev"].api_key is not None
    assert loaded.instances["dev"].api_key.get_secret_value() == "k1"


def test_save_writes_chmod_600() -> None:
    cfg = Config(instances={"d": Instance(url="https://x.example.com", api_key="k")})  # type: ignore[arg-type]
    store.save(cfg)
    mode = store.config_path().stat().st_mode & 0o777
    assert mode == 0o600


def test_resolve_active_prefers_override() -> None:
    cfg = Config(
        current_instance="prod",
        instances={
            "prod": Instance(url="https://p.example.com", api_key="k"),  # type: ignore[arg-type]
            "stg": Instance(url="https://s.example.com", api_key="k"),  # type: ignore[arg-type]
        },
    )
    store.save(cfg)
    name, inst = store.resolve_active("stg")
    assert name == "stg"
    assert str(inst.url) == "https://s.example.com/"


def test_resolve_active_errors_without_target() -> None:
    store.save(Config())  # empty config
    with pytest.raises(UserError):
        store.resolve_active()


def test_get_instance_unknown_raises_user_error() -> None:
    store.save(Config())
    with pytest.raises(UserError):
        store.get_instance("nope")
