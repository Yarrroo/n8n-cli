"""`n8n-cli pin-data *` — pinned test input per node (lives inside the workflow JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from n8n_cli.api.errors import UserError
from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core.patcher import WorkflowPatcher
from n8n_cli.output.jsonout import emit
from n8n_cli.output.summarize import SummarizeOptions, summarize_items

app = typer.Typer(help="Manage pinned test data on nodes.", no_args_is_help=True)

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
    """List nodes that have pinned data + item counts + approximate size."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        wf = PublicApi(t).get_workflow(workflow)
    rows: list[dict[str, Any]] = []
    pin = wf.get("pinData") or {}
    for node_name, items in pin.items():
        items_list = items if isinstance(items, list) else []
        rows.append(
            {
                "node": node_name,
                "item_count": len(items_list),
                "size_bytes": len(json.dumps(items_list, ensure_ascii=False).encode("utf-8")),
            }
        )
    emit(rows)


@app.command("get")
def get(
    workflow: WorkflowOpt,
    node: Annotated[str, typer.Option("--node", help="Node name.")],
    summarize: Annotated[
        bool, typer.Option("--summarize", help="Apply the same summarizer as execution-data.")
    ] = False,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Return pinned data for one node (raw or summarized)."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        wf = PublicApi(t).get_workflow(workflow)
    pin = wf.get("pinData") or {}
    if node not in pin:
        pinned_nodes = sorted(pin.keys()) or "(none)"
        raise UserError(
            f"no pin data for node {node!r}",
            hint=f"pinned nodes: {pinned_nodes}",
        )
    items = pin[node] if isinstance(pin[node], list) else []
    if summarize:
        emit(
            {
                "workflow": workflow,
                "node": node,
                "output": summarize_items(items, SummarizeOptions()),
            }
        )
    else:
        emit({"workflow": workflow, "node": node, "items": items})


@app.command("set")
def set_(
    workflow: WorkflowOpt,
    node: Annotated[str, typer.Option("--node", help="Node name.")],
    file: Annotated[
        Path | None,
        typer.Option("--file", help="JSON file with an array of items."),
    ] = None,
    data: Annotated[
        str | None,
        typer.Option("--data", help="Inline JSON array of items (alternative to --file)."),
    ] = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Pin a JSON array of items to a node (seed for next execution)."""
    if (file is None) == (data is None):
        raise UserError("pass exactly one of --file or --data")
    if data is not None:
        try:
            items = json.loads(data)
        except json.JSONDecodeError as exc:
            raise UserError(f"--data is not valid JSON: {exc}") from exc
    else:
        assert file is not None
        if not file.exists():
            raise UserError(f"file not found: {file}")
        try:
            items = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UserError(f"--file is not valid JSON: {exc}") from exc
    if not isinstance(items, list):
        raise UserError("pin-data must be a JSON array of items")

    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        patcher = WorkflowPatcher(PublicApi(t), workflow)
        patcher.set_pin_data(node, items)
        patcher.commit()
    emit({"workflow": workflow, "node": node, "item_count": len(items)})


@app.command("delete")
def delete(
    workflow: WorkflowOpt,
    node: Annotated[str, typer.Option("--node", help="Node name.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Remove pinned data for a node."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        patcher = WorkflowPatcher(PublicApi(t), workflow)
        patcher.delete_pin_data(node)
        patcher.commit()
    emit({"workflow": workflow, "node": node, "deleted": True})
