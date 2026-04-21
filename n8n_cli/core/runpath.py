"""Navigate n8n execution-data JSON to extract a specific node's items.

Execution shape (relevant slice):
    data.resultData.runData[NodeName] = [
        {                                  # run 0
            "startTime": 1700000000000,
            "executionTime": 123,
            "data": {
                "main": [                  # output connections by index
                    [                      # items of output 0
                        {"json": {...}, "binary": {...}, "pairedItem": ...}
                    ]
                ]
            }
        },
        ...
    ]

For a given (execution, node, run, output) we return the list of item
objects — typically each contains a `json` field with the actual payload.
"""

from __future__ import annotations

from typing import Any


class NodeRunNotFoundError(KeyError):
    """Raised when the requested node / run / output index doesn't exist."""


def extract_node_items(
    execution: dict[str, Any],
    node: str,
    *,
    run_index: int = 0,
    output_index: int = 0,
) -> tuple[list[Any], dict[str, Any]]:
    """Return (items, run_metadata) for one node's output.

    `run_metadata` is the plain run-info dict minus the bulky `data` field.
    """
    run_data = (
        (execution.get("data") or {}).get("resultData", {}).get("runData")
        or (execution.get("data") or {}).get("runData")
        or {}
    )
    if node not in run_data:
        executed = sorted(run_data.keys())
        raise NodeRunNotFoundError(
            f"node {node!r} was not executed (executed nodes: {executed or 'none'})"
        )
    runs = run_data[node] or []
    if run_index >= len(runs):
        raise NodeRunNotFoundError(
            f"node {node!r} has {len(runs)} run(s); run_index={run_index} out of range"
        )
    run = runs[run_index] or {}
    mains = (run.get("data") or {}).get("main") or []
    if output_index >= len(mains):
        raise NodeRunNotFoundError(
            f"node {node!r} run {run_index} has {len(mains)} output(s); output_index={output_index} out of range"
        )
    items = mains[output_index] or []
    run_meta = {k: v for k, v in run.items() if k != "data"}
    return list(items), run_meta


def executed_nodes(execution: dict[str, Any]) -> list[str]:
    run_data = (
        (execution.get("data") or {}).get("resultData", {}).get("runData")
        or (execution.get("data") or {}).get("runData")
        or {}
    )
    return sorted(run_data.keys())
