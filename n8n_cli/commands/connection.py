"""`n8n-cli connection *` — list/add/delete edges between nodes."""

from __future__ import annotations

from typing import Annotated

import typer

from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core.patcher import WorkflowPatcher
from n8n_cli.output.jsonout import emit

app = typer.Typer(help="Manage connections between workflow nodes.", no_args_is_help=True)

WorkflowOpt = Annotated[str, typer.Option("--workflow", help="Workflow ID.")]
InstanceOpt = Annotated[
    str | None, typer.Option("--instance", help="Instance name (defaults to current).")
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]


@app.command("list")
def list_(
    workflow: WorkflowOpt,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """List all connections as a flat array."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        patcher = WorkflowPatcher(PublicApi(t), workflow)
    emit(patcher.list_connections())


@app.command("add")
def add(
    workflow: WorkflowOpt,
    frm: Annotated[str, typer.Option("--from", help="Source node name.")],
    to: Annotated[str, typer.Option("--to", help="Target node name.")],
    from_output: Annotated[int, typer.Option("--from-output", help="Source output index.")] = 0,
    to_input: Annotated[int, typer.Option("--to-input", help="Target input index.")] = 0,
    conn_type: Annotated[
        str, typer.Option("--type", help="Connection type (main, ai_tool, ...).")
    ] = "main",
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Create a connection from node --from to node --to."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        patcher = WorkflowPatcher(PublicApi(t), workflow)
        patcher.add_connection(
            frm=frm, to=to, from_output=from_output, to_input=to_input, conn_type=conn_type
        )
        patcher.commit()
    emit(
        {
            "added": {
                "from": frm,
                "fromOutput": from_output,
                "to": to,
                "toInput": to_input,
                "type": conn_type,
            }
        }
    )


@app.command("delete")
def delete(
    workflow: WorkflowOpt,
    frm: Annotated[str, typer.Option("--from", help="Source node name.")],
    to: Annotated[str, typer.Option("--to", help="Target node name.")],
    from_output: Annotated[int, typer.Option("--from-output", help="Source output index.")] = 0,
    to_input: Annotated[int, typer.Option("--to-input", help="Target input index.")] = 0,
    conn_type: Annotated[str, typer.Option("--type", help="Connection type.")] = "main",
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Remove one specific connection."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        patcher = WorkflowPatcher(PublicApi(t), workflow)
        patcher.delete_connection(
            frm=frm, to=to, from_output=from_output, to_input=to_input, conn_type=conn_type
        )
        patcher.commit()
    emit(
        {
            "deleted": {
                "from": frm,
                "fromOutput": from_output,
                "to": to,
                "toInput": to_input,
                "type": conn_type,
            }
        }
    )
