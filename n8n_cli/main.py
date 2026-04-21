"""Root Typer application for `n8n-cli`.

Mounts one sub-application per resource. Actual command logic lives in the
respective `commands/*.py` modules (Phase 0 mounts stubs; later phases replace
them with real implementations).

Exit code policy: we trap `CliError` subclasses and map them to stable exit
codes (see `api/errors.py`). Everything else propagates as an uncaught
exception so bugs aren't silently swallowed.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from n8n_cli import __version__
from n8n_cli.api.errors import CliError, ExitCode
from n8n_cli.commands import (
    auth,
    connection,
    credential,
    execdata,
    execution,
    folder,
    instance,
    node,
    pindata,
    project,
    setup,
    workflow,
)

app = typer.Typer(
    name="n8n-cli",
    help=(
        "AI-friendly CLI for n8n — node-level workflow ops and summarized execution data. "
        "JSON on stdout by default; pass --human for tables."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=True,
)

# Resource subcommands (grouped semantically).
app.add_typer(instance.app, name="instance")
app.add_typer(auth.app, name="auth")
app.add_typer(project.app, name="project")
app.add_typer(folder.app, name="folder")
app.add_typer(workflow.app, name="workflow")
app.add_typer(node.app, name="node")
app.add_typer(connection.app, name="connection")
app.add_typer(pindata.app, name="pin-data")
app.add_typer(execution.app, name="execution")
app.add_typer(execdata.app, name="execution-data")
app.add_typer(credential.app, name="credential")
app.add_typer(setup.app, name="setup")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=ExitCode.SUCCESS)


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """n8n-cli root callback — shared global flags live here."""


def run() -> None:
    """Console-script entry point.

    Wraps the Typer app so our `CliError` hierarchy maps to stable exit codes
    instead of Typer's default traceback/print behavior.
    """
    err_console = Console(stderr=True)
    try:
        app()
    except CliError as exc:
        err_console.print(f"[red]error:[/red] {exc.message}")
        if exc.hint:
            err_console.print(f"[dim]hint:[/dim] {exc.hint}")
        sys.exit(int(exc.exit_code))


if __name__ == "__main__":
    run()
