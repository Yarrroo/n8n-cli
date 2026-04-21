"""Live-backed integration tests for Phase 1 workflow read commands.

Each test uses VCR.py to record the HTTP interaction once and replay on
subsequent runs. The cassettes are scrubbed of API keys via the filter in
conftest.py.
"""

from __future__ import annotations

import pytest

from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from tests.integration.conftest import vcr_instance


@pytest.mark.integration
@vcr_instance.use_cassette("workflow_list.yaml")
def test_workflow_list_returns_data(live_transport: Transport) -> None:
    api = PublicApi(live_transport)
    first_page = list(api.list_workflows(limit=3))
    assert len(first_page) >= 1
    wf = first_page[0]
    # Spot-check the shape we rely on downstream.
    for field in ("id", "name", "nodes", "connections"):
        assert field in wf, f"{field} missing from workflow response"


@pytest.mark.integration
@vcr_instance.use_cassette("workflow_get.yaml")
def test_workflow_get_structure(live_transport: Transport) -> None:
    api = PublicApi(live_transport)
    first = next(iter(api.list_workflows(limit=1)))
    full = api.get_workflow(first["id"])
    assert full["id"] == first["id"]
    assert "nodes" in full
    # `connections` is always an object, even for empty workflows.
    assert isinstance(full.get("connections", {}), dict)


@pytest.mark.integration
@vcr_instance.use_cassette("workflow_ping.yaml")
def test_ping_succeeds(live_transport: Transport) -> None:
    api = PublicApi(live_transport)
    result = api.ping()
    assert "data" in result
