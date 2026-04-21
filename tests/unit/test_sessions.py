"""Session file: write → chmod 600 → read → clear."""

from __future__ import annotations

from pathlib import Path

import pytest

from n8n_cli.config import sessions, store
from n8n_cli.config.sessions import Session


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setattr(store, "config_dir", lambda: cfg_dir)
    monkeypatch.setattr(store, "config_path", lambda: cfg_dir / "config.yaml")
    monkeypatch.setattr(store, "sessions_dir", lambda: cfg_dir / "sessions")


def test_roundtrip_preserves_fields() -> None:
    s = Session(
        cookie="n8n-auth=xyz",
        expires_at="2026-05-01T00:00:00+00:00",
        user_id="u1",
        personal_project_id="p1",
    )
    sessions.save("dev", s)
    loaded = sessions.load("dev")
    assert loaded is not None
    assert loaded.cookie == "n8n-auth=xyz"
    assert loaded.user_id == "u1"
    assert loaded.personal_project_id == "p1"


def test_file_is_chmod_600() -> None:
    sessions.save("dev", Session(cookie="n8n-auth=xyz"))
    path = store.sessions_dir() / "dev.session"
    assert (path.stat().st_mode & 0o777) == 0o600


def test_load_missing_returns_none() -> None:
    assert sessions.load("nope") is None


def test_clear_removes_file() -> None:
    sessions.save("dev", Session(cookie="n8n-auth=xyz"))
    path = store.sessions_dir() / "dev.session"
    assert path.exists()
    sessions.clear("dev")
    assert not path.exists()
    # Idempotent: clearing again is fine.
    sessions.clear("dev")
