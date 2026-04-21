"""`n8n-cli credential *` — mixed public / frontend backends.

Why split:
  - list / get / patch → public API 1.1.1 does not expose → frontend /rest
  - add / delete / schema → available on public /api/v1

Secret values (`data`) are never returned from n8n to begin with, and the
redactor in `output.jsonout` strips anything that slips through.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from n8n_cli.api.errors import UserError
from n8n_cli.api.frontend import FrontendApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core.cred_types import credential_types_for_node_name
from n8n_cli.output.jsonout import emit

app = typer.Typer(help="Manage n8n credentials.", no_args_is_help=True)

InstanceOpt = Annotated[
    str | None, typer.Option("--instance", help="Instance name (defaults to current).")
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]


def _row(cred: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": cred.get("id"),
        "name": cred.get("name"),
        "type": cred.get("type"),
        "is_managed": cred.get("isManaged", False),
        "home_project_id": (cred.get("homeProject") or {}).get("id"),
    }


@app.command("list")
def list_(
    cred_type: Annotated[
        str | None, typer.Option("--type", help="Filter by exact credential type.")
    ] = None,
    for_node: Annotated[
        str | None,
        typer.Option(
            "--for-node",
            help="Filter to credentials usable by this node (display name or exact type).",
        ),
    ] = None,
    for_node_type: Annotated[
        str | None,
        typer.Option("--for-node-type", help="Exact node type, e.g. n8n-nodes-base.httpRequest."),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap the returned rows.")] = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """List credentials on the instance (frontend API — secrets never returned)."""
    if for_node is not None and for_node_type is not None:
        raise UserError("pass either --for-node or --for-node-type, not both")

    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        creds = FrontendApi(t).list_credentials()

    allowed: set[str] | None = None
    if cred_type is not None:
        allowed = {cred_type}
    if for_node is not None:
        allowed = set(credential_types_for_node_name(for_node))
    if for_node_type is not None:
        from n8n_cli.core.cred_types import credential_types_for_node_type

        allowed = set(credential_types_for_node_type(for_node_type))

    rows = [_row(c) for c in creds if allowed is None or c.get("type") in allowed]
    if limit is not None:
        rows = rows[:limit]
    emit(rows)


@app.command("get")
def get(
    credential_id: Annotated[str, typer.Argument(help="Credential ID.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show credential metadata (secret data never returned by n8n)."""
    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        cred = FrontendApi(t).get_credential(credential_id)
    emit(cred)


@app.command("add")
def add(
    cred_type: Annotated[str, typer.Option("--type", help="Credential type, e.g. slackApi.")],
    cred_name: Annotated[str, typer.Option("--name", help="Display name.")],
    data: Annotated[
        str,
        typer.Option("--data", help="JSON object with credential payload (secret values)."),
    ],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Create a new credential via the public API."""
    try:
        data_obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise UserError(f"--data is not valid JSON: {exc}") from exc
    if not isinstance(data_obj, dict):
        raise UserError("--data must be a JSON object")

    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        body = t.post(
            "/api/v1/credentials",
            json={"type": cred_type, "name": cred_name, "data": data_obj},
        )
    # Redactor strips any echoed `data` automatically.
    emit(body)


@app.command("patch")
def patch(
    credential_id: Annotated[str, typer.Argument(help="Credential ID.")],
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", help="Dot-notation (only name= supported for now)."),
    ] = None,
    data: Annotated[str | None, typer.Option("--data", help="Replace the secret payload.")] = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Rename a credential and/or replace its secret payload (frontend API)."""
    new_name: str | None = None
    for op in set_ or []:
        if not op.startswith("name="):
            raise UserError(f"only `--set name=...` is supported; got {op!r}")
        new_name = op[len("name=") :]
    data_obj: dict[str, Any] | None = None
    if data is not None:
        try:
            data_obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise UserError(f"--data is not valid JSON: {exc}") from exc
        if not isinstance(data_obj, dict):
            raise UserError("--data must be a JSON object")
    if new_name is None and data_obj is None:
        raise UserError("nothing to update — pass --set name=... or --data '...'")

    name, inst = store.resolve_active(instance_name)
    with Transport(inst, instance_name=name, verbose=verbose) as t:
        FrontendApi(t).patch_credential(credential_id, name=new_name, data=data_obj)
    emit({"id": credential_id, "updated": True})


@app.command("delete")
def delete(
    credential_id: Annotated[str, typer.Argument(help="Credential ID.")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Delete a credential (public API)."""
    if not force:
        typer.confirm(f"Delete credential {credential_id}?", abort=True)
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        t.delete(f"/api/v1/credentials/{credential_id}")
    emit({"deleted": credential_id})


@app.command("schema")
def schema(
    credential_type: Annotated[str, typer.Argument(help="Credential type, e.g. slackApi.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Return the input schema for a credential type (public API)."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        body = t.get(f"/api/v1/credentials/schema/{credential_type}")
    emit(body)
