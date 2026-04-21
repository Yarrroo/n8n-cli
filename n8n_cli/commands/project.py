"""`n8n-cli project *` — public API for team projects + frontend fallback.

On community / single-team instances, `GET /api/v1/projects` returns
403 "license does not allow for feat:projectRole:admin". We treat that as
expected and fall back to the frontend API to surface at least the personal
project. `project add/patch/delete` surface a clear CapabilityError.
"""

from __future__ import annotations

from typing import Annotated

import typer

from n8n_cli.api.errors import ApiError, CapabilityError, UserError
from n8n_cli.api.frontend import FrontendApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.output.jsonout import emit

app = typer.Typer(
    help="Manage projects (gated by license on many instances).",
    no_args_is_help=True,
)

InstanceOpt = Annotated[
    str | None, typer.Option("--instance", help="Instance name (defaults to current).")
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]


@app.command("list")
def list_(
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """List projects. Falls back to frontend /rest/projects if public is gated."""
    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        try:
            body = t.get("/api/v1/projects")
        except CapabilityError:
            # Community licenses block the public endpoint — try frontend
            # (requires an active session).
            body = t.get("/rest/projects")
    emit(body.get("data") or body)


@app.command("current")
def current(
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show the current user's personal project (resolved via frontend)."""
    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        pid = FrontendApi(t).personal_project_id()
    emit({"personal_project_id": pid})


@app.command("get")
def get(
    project_id: Annotated[str, typer.Argument(help="Project ID.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show a project. Frontend first (has richer detail), public as fallback."""
    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        try:
            body = t.get(f"/rest/projects/{project_id}")
            emit(body.get("data") or body)
            return
        except (ApiError, CapabilityError):
            body = t.get("/api/v1/projects")
    for p in body.get("data") or []:
        if p.get("id") == project_id:
            emit(p)
            return
    raise UserError(f"project {project_id!r} not found")


@app.command("add")
def add(
    project_name: Annotated[str, typer.Option("--name", help="Project name.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Create a new team project (requires enterprise license)."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        body = t.post("/api/v1/projects", json={"name": project_name})
    emit(body.get("data") or body)


@app.command("patch")
def patch(
    project_id: Annotated[str, typer.Argument(help="Project ID.")],
    set_: Annotated[list[str] | None, typer.Option("--set", help="--set name=<new name>.")] = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Update a project (requires enterprise license)."""
    payload: dict[str, str] = {}
    for op in set_ or []:
        if not op.startswith("name="):
            raise UserError(f"only `--set name=...` is supported; got {op!r}")
        payload["name"] = op[len("name=") :]
    if not payload:
        raise UserError("nothing to update — pass --set name=...")
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        t.put(f"/api/v1/projects/{project_id}", json=payload)
    emit({"id": project_id, "updated": True})


@app.command("delete")
def delete(
    project_id: Annotated[str, typer.Argument(help="Project ID.")],
    force: Annotated[bool, typer.Option("--force")] = False,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Delete a project (requires enterprise license)."""
    if not force:
        typer.confirm(f"Delete project {project_id}?", abort=True)
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        t.delete(f"/api/v1/projects/{project_id}")
    emit({"deleted": project_id})
