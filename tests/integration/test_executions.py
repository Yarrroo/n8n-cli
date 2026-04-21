"""Integration: executions + end-to-end summarizer on a real n8n run.

The cassette captures one real execution's data (scrubbed of API key). The
test verifies:
  1. `execution list` round-trips
  2. `get_execution(include_data=True)` returns runData
  3. summarizer keeps simple-shape output under 1 KB default budget
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.core import runpath
from n8n_cli.output.summarize import SummarizeOptions, summarize_items
from tests.integration.conftest import vcr_instance


@pytest.mark.integration
@vcr_instance.use_cassette("execution_list.yaml")
def test_execution_list(live_transport: Transport) -> None:
    api = PublicApi(live_transport)
    execs = list(api.list_executions(limit=5))
    assert len(execs) >= 1
    assert "id" in execs[0]
    assert "status" in execs[0]


@pytest.mark.integration
@pytest.mark.skipif(
    not (Path(__file__).parent / "cassettes" / "execution_get_with_data.yaml").exists(),
    reason="large execution cassette not committed to the public repo; "
    "record locally with VCR_RECORD=all to exercise this path",
)
def test_execution_get_includes_run_data(live_transport: Transport) -> None:
    with vcr_instance.use_cassette("execution_get_with_data.yaml"):
        api = PublicApi(live_transport)
        first = next(iter(api.list_executions(limit=1)))
        full = api.get_execution(first["id"], include_data=True)
        nodes = runpath.executed_nodes(full)
        assert len(nodes) >= 1, "real executions always have at least one run node"

        items, _ = runpath.extract_node_items(full, nodes[0])
        summary = summarize_items(items, SummarizeOptions())
        for key in ("item_count", "total_size_bytes", "schema", "sample", "truncated"):
            assert key in summary


@pytest.mark.integration
def test_summarizer_hits_one_kb_budget_for_simple_shape() -> None:
    """Headline success criterion on a synthetic but realistic payload."""
    items = [
        {
            "json": {
                "id": f"u_{i}",
                "name": f"User {i}",
                "email": f"u{i}@example.com",
                "score": i * 1.5,
            }
        }
        for i in range(5000)
    ]
    raw = json.dumps(items, ensure_ascii=False).encode()
    assert len(raw) > 400_000  # ≫ 1 KB
    out = summarize_items(items)
    serialized = json.dumps(out, ensure_ascii=False)
    assert len(serialized.encode()) <= 1024, (
        f"default summary exceeded 1 KB: {len(serialized)} bytes"
    )
    assert out["item_count"] == 5000
