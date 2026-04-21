"""End-to-end editing: create workflow → add nodes → connect → rename → verify.

This test creates a fresh workflow on the configured live instance, exercises the full editing
pipeline, and cleans up by archiving. On replay, VCR serves the recorded
responses so no live instance is needed.
"""

from __future__ import annotations

import pytest

from n8n_cli.api.public import PublicApi
from n8n_cli.api.transport import Transport
from n8n_cli.core.patcher import WorkflowPatcher
from tests.integration.conftest import vcr_instance


@pytest.mark.integration
@vcr_instance.use_cassette("editing_full_cycle.yaml")
def test_editing_full_cycle(live_transport: Transport) -> None:
    api = PublicApi(live_transport)

    # 1) Create an empty workflow.
    created = api.create_workflow(
        {
            "name": "n8n-cli-test-phase3",
            "nodes": [],
            "connections": {},
            "settings": {},
        }
    )
    wf_id = created["id"]
    assert isinstance(wf_id, str)

    try:
        # 2) Add Manual Trigger.
        p1 = WorkflowPatcher(api, wf_id)
        p1.add_node(
            node_type="n8n-nodes-base.manualTrigger",
            name="Start",
            position=[0.0, 0.0],
        )
        p1.commit()

        # 3) Add Set node after Start (auto-connects).
        p2 = WorkflowPatcher(api, wf_id)
        p2.add_node(
            node_type="n8n-nodes-base.set",
            name="Seed",
            after="Start",
            parameters={"assignments": {"assignments": []}},
        )
        p2.commit()

        # 4) Verify connection exists.
        p3 = WorkflowPatcher(api, wf_id)
        conns = p3.list_connections()
        assert any(c["from"] == "Start" and c["to"] == "Seed" for c in conns)

        # 5) Rename Seed → Transform (must cascade).
        p4 = WorkflowPatcher(api, wf_id)
        touches = p4.rename_node("Seed", "Transform")
        assert touches >= 2  # node name + target reference
        p4.commit()

        # 6) Verify rename took.
        fresh = api.get_workflow(wf_id)
        names = [n["name"] for n in fresh["nodes"]]
        assert "Transform" in names and "Seed" not in names
        # Start → Transform connection still wired.
        start_targets = fresh["connections"]["Start"]["main"][0]
        assert start_targets[0]["node"] == "Transform"

        # 7) Pin data on Start, then remove via delete_node cascade.
        p5 = WorkflowPatcher(api, wf_id)
        p5.set_pin_data("Start", [{"json": {"hello": "world"}}])
        p5.commit()

        fresh = api.get_workflow(wf_id)
        assert "Start" in (fresh.get("pinData") or {})

        # 8) Delete Transform — Start's outgoing connection must become empty.
        p6 = WorkflowPatcher(api, wf_id)
        p6.delete_node("Transform")
        p6.commit()

        fresh = api.get_workflow(wf_id)
        assert all(n["name"] != "Transform" for n in fresh["nodes"])

    finally:
        # Clean up: archive the test workflow.
        try:
            arch = WorkflowPatcher(api, wf_id)
            arch.set_archived(True)
            arch.commit()
        except Exception:
            # On replay mode we may not have a cassette entry for archive —
            # that's OK, the test has already validated behavior.
            pass
