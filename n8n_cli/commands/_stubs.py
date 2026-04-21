"""Helpers for generating phase-N command stubs.

Each resource subcommand is a Typer app with a number of actions. Until a phase
implements the action, we mount a stub that prints a consistent message and
exits with `ExitCode.UNIMPLEMENTED` so scripts can tell stubs from real errors.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import typer

from n8n_cli.api.errors import UnimplementedError


def stub(resource: str, action: str, phase: int) -> Callable[..., Any]:
    """Build a no-op Typer command that raises UnimplementedError.

    Accepts arbitrary CLI args so help screens still list them correctly when we
    expand stubs into real commands later — but here we just swallow via context.
    """

    def _cmd(ctx: typer.Context) -> None:
        raise UnimplementedError(
            f"`{resource} {action}` is not implemented yet",
            hint=f"scheduled for Phase {phase}.",
        )

    _cmd.__name__ = f"{resource}_{action}_stub"
    _cmd.__doc__ = f"[stub] `{resource} {action}` — implemented in Phase {phase}."
    return _cmd


def mount_stubs(app: typer.Typer, resource: str, actions: dict[str, int]) -> None:
    """Attach every (action → phase) pair as a stub subcommand on `app`.

    `actions` keys keep their dash-separated form (Typer renders them as CLI names).
    """
    for action, phase in actions.items():
        app.command(
            name=action,
            help=f"[stub] {action} — implemented in Phase {phase}.",
            context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        )(stub(resource, action, phase))
