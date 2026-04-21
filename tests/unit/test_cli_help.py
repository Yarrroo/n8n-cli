"""Phase 0 smoke tests: CLI wiring, help text, stub exit codes."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from n8n_cli import __version__
from n8n_cli.api.errors import ExitCode
from n8n_cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    # mix_stderr=False so we can inspect stderr independently of stdout.
    return CliRunner()


def test_top_level_help_lists_every_resource(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for resource in (
        "instance",
        "auth",
        "project",
        "folder",
        "workflow",
        "node",
        "connection",
        "pin-data",
        "execution",
        "execution-data",
        "credential",
    ):
        assert resource in out, f"resource {resource!r} missing from --help output"


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_unimplemented_error_maps_to_exit_code_one() -> None:
    """The stub infrastructure must raise UnimplementedError with exit code 1.

    After Phase 5 there are no remaining action stubs, so we exercise the
    factory directly. Any regression in stub wiring will still be caught.
    """
    from n8n_cli.api.errors import UnimplementedError
    from n8n_cli.commands._stubs import stub

    fn = stub("demo", "noop", 99)
    with pytest.raises(UnimplementedError) as excinfo:
        fn(ctx=None)  # type: ignore[call-arg]
    assert excinfo.value.exit_code == ExitCode.UNIMPLEMENTED
    assert "Phase 99" in (excinfo.value.hint or "")


def test_unknown_command_is_user_error(runner: CliRunner) -> None:
    result = runner.invoke(app, ["not-a-real-command"])
    # Typer returns 2 for usage errors — matches our USER_ERROR code.
    assert result.exit_code == 2
