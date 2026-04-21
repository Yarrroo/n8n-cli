"""`n8n-cli execution *` — list/get/delete/retry + per-node summary rollup."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core import runpath
from n8n_cli.output.jsonout import emit
from n8n_cli.output.summarize import summarize_items

app = typer.Typer(help="List and inspect workflow executions.", no_args_is_help=True)

InstanceOpt = Annotated[
    str | None,
    typer.Option("--instance", help="Instance name (defaults to current)."),
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]


def _exec_row(ex: dict[str, Any]) -> dict[str, Any]:
    started = ex.get("startedAt")
    stopped = ex.get("stoppedAt")
    duration_ms: int | None = None
    if started and stopped:
        from datetime import datetime

        try:
            s = datetime.fromisoformat(started.replace("Z", "+00:00"))
            e = datetime.fromisoformat(stopped.replace("Z", "+00:00"))
            duration_ms = int((e - s).total_seconds() * 1000)
        except (ValueError, AttributeError):
            duration_ms = None
    return {
        "id": ex.get("id"),
        "status": ex.get("status"),
        "mode": ex.get("mode"),
        "workflowId": ex.get("workflowId"),
        "startedAt": started,
        "stoppedAt": stopped,
        "duration_ms": duration_ms,
    }


@app.command("list")
def list_(
    workflow: Annotated[
        str | None, typer.Option("--workflow", help="Filter by workflow id.")
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status (success|error|waiting|running)."),
    ] = None,
    project: Annotated[str | None, typer.Option("--project", help="Filter by project id.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max number of results.")] = 20,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """List executions. Defaults to 20 so stdout stays small by default."""
    _, inst = store.resolve_active(instance_name)
    results: list[dict[str, Any]] = []
    with Transport(inst, verbose=verbose) as t:
        for ex in PublicApi(t).list_executions(
            workflow_id=workflow, status=status, project_id=project, limit=limit
        ):
            results.append(_exec_row(ex))
            if len(results) >= limit:
                break
    emit(results)


@app.command("get")
def get(
    execution_id: Annotated[str, typer.Argument(help="Execution ID.")],
    summarize: Annotated[
        bool,
        typer.Option("--summarize", help="Include per-node output summaries (includeData=true)."),
    ] = False,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show one execution. Default: metadata only; --summarize adds node rollups."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        ex = PublicApi(t).get_execution(execution_id, include_data=summarize)
    row = _exec_row(ex)
    if not summarize:
        emit(row)
        return

    # Per-node rollup: same summarizer as execution-data but at default budget.
    nodes_out: list[dict[str, Any]] = []
    for node_name in runpath.executed_nodes(ex):
        try:
            items, run_meta = runpath.extract_node_items(ex, node_name)
        except runpath.NodeRunNotFoundError:
            continue
        nodes_out.append(
            {
                "name": node_name,
                "duration_ms": run_meta.get("executionTime"),
                "output": summarize_items(items),
            }
        )
    emit({**row, "nodes": nodes_out})


@app.command("delete")
def delete(
    execution_id: Annotated[str, typer.Argument(help="Execution ID.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Delete one execution record."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        PublicApi(t).delete_execution(execution_id)
    emit({"deleted": execution_id})


@app.command("retry")
def retry(
    execution_id: Annotated[str, typer.Argument(help="Execution ID.")],
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Retry a failed execution (creates a new one)."""
    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        new = PublicApi(t).retry_execution(execution_id)
    emit({"original": execution_id, "new": _exec_row(new)})
