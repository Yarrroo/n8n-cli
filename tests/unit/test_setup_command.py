"""Tests for `n8n-cli setup install/uninstall/status`.

Uses CLAUDE_HOME override so nothing touches the real ~/.claude.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from n8n_cli.main import app


@pytest.fixture
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".claude"
    monkeypatch.setenv("CLAUDE_HOME", str(home))
    return home


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_install_drops_skill_and_slash_command(runner: CliRunner, claude_home: Path) -> None:
    result = runner.invoke(app, ["setup", "install"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["ok"] is True
    assert (claude_home / "skills" / "n8n-cli" / "SKILL.md").exists()
    assert (claude_home / "commands" / "n8n.md").exists()
    # CLAUDE.md not touched without --with-claude-md.
    assert body["claude_md"] is None


def test_install_is_idempotent(runner: CliRunner, claude_home: Path) -> None:
    runner.invoke(app, ["setup", "install"])
    second = runner.invoke(app, ["setup", "install"])
    assert second.exit_code == 0
    steps = json.loads(second.stdout)["steps"]
    # Second run must report 'unchanged' for both files.
    unchanged_count = sum(1 for s in steps if s.startswith("unchanged:"))
    assert unchanged_count == 2


def test_install_with_claude_md_adds_marker_block(runner: CliRunner, claude_home: Path) -> None:
    result = runner.invoke(app, ["setup", "install", "--with-claude-md"])
    assert result.exit_code == 0
    claude_md = claude_home / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "<!-- n8n-cli:begin -->" in content
    assert "<!-- n8n-cli:end -->" in content
    assert "n8n workflow management" in content


def test_install_with_claude_md_updates_existing_block(
    runner: CliRunner, claude_home: Path
) -> None:
    claude_home.mkdir(parents=True)
    pre_existing = "# User preferences\n\nAlways be concise.\n"
    (claude_home / "CLAUDE.md").write_text(pre_existing)

    runner.invoke(app, ["setup", "install", "--with-claude-md"])
    first = (claude_home / "CLAUDE.md").read_text()
    assert pre_existing.strip() in first
    assert "<!-- n8n-cli:begin -->" in first

    # Second run should report unchanged.
    second = runner.invoke(app, ["setup", "install", "--with-claude-md"])
    body = json.loads(second.stdout)
    assert body["claude_md"] == "unchanged"


def test_uninstall_removes_everything_it_added(runner: CliRunner, claude_home: Path) -> None:
    runner.invoke(app, ["setup", "install", "--with-claude-md"])
    assert (claude_home / "skills" / "n8n-cli" / "SKILL.md").exists()

    result = runner.invoke(app, ["setup", "uninstall"])
    assert result.exit_code == 0
    assert not (claude_home / "skills" / "n8n-cli").exists()
    assert not (claude_home / "commands" / "n8n.md").exists()
    # CLAUDE.md remains but block is gone.
    claude_md = claude_home / "CLAUDE.md"
    if claude_md.exists():
        assert "<!-- n8n-cli:begin -->" not in claude_md.read_text()


def test_uninstall_preserves_unrelated_claude_md_content(
    runner: CliRunner, claude_home: Path
) -> None:
    claude_home.mkdir(parents=True)
    original = "# User rules\n\nAlways test before commit.\n"
    (claude_home / "CLAUDE.md").write_text(original)

    runner.invoke(app, ["setup", "install", "--with-claude-md"])
    runner.invoke(app, ["setup", "uninstall"])

    remaining = (claude_home / "CLAUDE.md").read_text()
    assert "Always test before commit." in remaining
    assert "<!-- n8n-cli:begin -->" not in remaining


def test_status_reports_installed_state(runner: CliRunner, claude_home: Path) -> None:
    before = runner.invoke(app, ["setup", "status"])
    body = json.loads(before.stdout)
    assert body["installed"]["skill"] is False

    runner.invoke(app, ["setup", "install"])
    after = json.loads(runner.invoke(app, ["setup", "status"]).stdout)
    assert after["installed"]["skill"] is True
    assert after["installed"]["slash_command"] is True
