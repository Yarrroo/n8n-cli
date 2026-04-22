"""`n8n-cli execution-data get` — the summarization power tool.

Usage:
    n8n-cli execution-data get <eid> --node "Fetch Users"
    n8n-cli execution-data get <eid> --node N --head 5
    n8n-cli execution-data get <eid> --node N --path "items[0].id"
    n8n-cli execution-data get <eid> --node N --schema-only
    n8n-cli execution-data get <eid> --node N --full   # raw passthrough
"""

from __future__ import annotations

from typing import Annotated

import typer

from n8n_cli.api.errors import UserError
from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core import runpath
from n8n_cli.output.jsonout import emit
from n8n_cli.output.summarize import SummarizeOptions, summarize_items

app = typer.Typer(
    help="Inspect per-node execution output with intelligent summarization.",
    no_args_is_help=True,
)

InstanceOpt = Annotated[
    str | None, typer.Option("--instance", help="Instance name (defaults to current).")
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]


@app.command("get")
def get(
    execution_id: Annotated[str, typer.Argument(help="Execution ID.")],
    node: Annotated[str, typer.Option("--node", help="Node name to inspect.")],
    sample: Annotated[int, typer.Option("--sample", help="Sample item count (default 1).")] = 1,
    head: Annotated[
        int | None, typer.Option("--head", help="First N items (overrides --sample).")
    ] = None,
    path: Annotated[
        str | None, typer.Option("--path", help="JSONPath to extract (e.g. 'items[0].id').")
    ] = None,
    schema_only: Annotated[
        bool, typer.Option("--schema-only", help="Return schema without sample items.")
    ] = False,
    full: Annotated[
        bool, typer.Option("--full", help="Return raw items (escape hatch — may be huge).")
    ] = False,
    max_bytes: Annotated[
        int, typer.Option("--max-bytes", help="Size budget for summary (default 1024).")
    ] = 1024,
    run: Annotated[int, typer.Option("--run", help="Run index (default 0).")] = 0,
    output: Annotated[
        int, typer.Option("--output", help="Output connection index (default 0).")
    ] = 0,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Fetch execution `eid`, extract `node` output, summarize."""
    # Flag-compatibility guards keep the error surface clean for LLMs.
    if full and (schema_only or head is not None or path is not None):
        raise UserError("--full is incompatible with --schema-only/--head/--path")

    _, inst = store.resolve_active(instance_name)
    with Transport(inst, verbose=verbose) as t:
        ex = PublicApi(t).get_execution(execution_id, include_data=True)

    # Surface node-level error cleanly when the node crashed — n8n typically
    # records the error and emits no output items, so `extract_node_items`
    # would otherwise raise "0 outputs out of range" internally.
    node_err = runpath.extract_node_error(ex, node, run_index=run)

    try:
        items, run_meta = runpath.extract_node_items(ex, node, run_index=run, output_index=output)
    except runpath.NodeRunNotFoundError as exc:
        if node_err is not None:
            emit(
                {
                    "execution_id": execution_id,
                    "node": node,
                    "status": ex.get("status"),
                    "run": run,
                    "output_index": output,
                    "error": node_err,
                    "output": None,
                }
            )
            return
        raise UserError(str(exc)) from exc

    opts = SummarizeOptions(
        sample=sample,
        head=head,
        path=path,
        schema_only=schema_only,
        full=full,
        max_bytes=max_bytes,
    )
    output_block = summarize_items(items, opts)

    emit(
        {
            "execution_id": execution_id,
            "node": node,
            "status": ex.get("status"),
            "duration_ms": run_meta.get("executionTime"),
            "run": run,
            "output_index": output,
            "error": node_err,
            "output": output_block,
        }
    )
