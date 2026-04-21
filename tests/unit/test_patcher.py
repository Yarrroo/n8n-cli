"""WorkflowPatcher — the atomic mutation engine.

We bypass the network by swapping in a tiny fake API that records
`update_workflow` calls; the patcher still thinks it's talking to n8n.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from n8n_cli.core.patcher import PatcherError, WorkflowPatcher


def _chain_workflow() -> dict:
    """Trigger → Code → IF. Classic rename-cascade fodder."""
    return {
        "id": "wf1",
        "name": "Chain",
        "nodes": [
            {"id": "a", "name": "Trigger", "type": "t", "position": [0, 0]},
            {"id": "b", "name": "Code", "type": "code", "position": [240, 0]},
            {"id": "c", "name": "IF", "type": "if", "position": [480, 0]},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Code", "type": "main", "index": 0}]]},
            "Code": {"main": [[{"node": "IF", "type": "main", "index": 0}]]},
        },
        "pinData": {"Trigger": [{"json": {"x": 1}}]},
        "settings": {"executionOrder": "v1"},
    }


class FakeApi:
    """Minimal PublicApi surface the patcher needs."""

    def __init__(self, workflow: dict) -> None:
        self.initial = deepcopy(workflow)
        self.last_put: dict | None = None

    def get_workflow(self, _id: str) -> dict:
        return deepcopy(self.initial)

    def update_workflow(self, _id: str, wf: dict) -> dict:
        self.last_put = deepcopy(wf)
        # Server echoes the workflow back with its id preserved.
        return {**wf, "id": _id}


def _make_patcher(workflow: dict | None = None) -> tuple[WorkflowPatcher, FakeApi]:
    api = FakeApi(workflow or _chain_workflow())
    p = WorkflowPatcher(api, "wf1")  # type: ignore[arg-type]
    return p, api


# --- add_node -------------------------------------------------------------


def test_add_node_after_creates_connection_and_positions() -> None:
    p, api = _make_patcher()
    p.add_node(node_type="n8n-nodes-base.set", name="Set", after="Code")
    p.commit()
    assert api.last_put is not None
    # Position offset by 240 on x.
    set_node = next(n for n in api.last_put["nodes"] if n["name"] == "Set")
    assert set_node["position"] == [240.0 + 240.0, 0.0]
    # Connection added.
    assert api.last_put["connections"]["Code"]["main"][0][-1]["node"] == "Set"


def test_add_node_rejects_duplicate_name() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="already exists"):
        p.add_node(node_type="t", name="Code")


# --- rename_node — the 4 required edge cases ------------------------------


def test_rename_full_chain_cascades_everywhere() -> None:
    p, api = _make_patcher()
    count = p.rename_node("Code", "Transform")
    # node name + source rekey + target rewrite = 3.
    assert count == 3
    p.commit()
    assert api.last_put is not None
    names = [n["name"] for n in api.last_put["nodes"]]
    assert "Transform" in names and "Code" not in names
    assert "Transform" in api.last_put["connections"]
    assert api.last_put["connections"]["Trigger"]["main"][0][0]["node"] == "Transform"


def test_rename_node_without_connections() -> None:
    wf = {
        "id": "w",
        "name": "w",
        "nodes": [{"id": "1", "name": "Orphan", "type": "t"}],
        "connections": {},
        "settings": {},
    }
    p, api = _make_patcher(wf)
    assert p.rename_node("Orphan", "Isolated") == 1
    p.commit()
    assert api.last_put is not None
    assert api.last_put["nodes"][0]["name"] == "Isolated"


def test_rename_self_loop() -> None:
    wf = {
        "id": "w",
        "name": "w",
        "nodes": [{"id": "1", "name": "Loop", "type": "t"}],
        "connections": {"Loop": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]}},
        "settings": {},
    }
    p, api = _make_patcher(wf)
    assert p.rename_node("Loop", "Cycle") == 3  # name + source + target
    p.commit()
    assert api.last_put is not None
    assert api.last_put["connections"] == {
        "Cycle": {"main": [[{"node": "Cycle", "type": "main", "index": 0}]]}
    }


def test_rename_node_with_pin_data() -> None:
    p, api = _make_patcher()
    assert p.rename_node("Trigger", "Start") == 3  # name + source + pin
    p.commit()
    assert api.last_put is not None
    assert "Start" in api.last_put["pinData"]
    assert "Trigger" not in api.last_put["pinData"]


def test_rename_conflict_raises_before_put() -> None:
    p, api = _make_patcher()
    with pytest.raises(PatcherError, match="already taken"):
        p.rename_node("Trigger", "Code")
    assert api.last_put is None


# --- delete_node ----------------------------------------------------------


def test_delete_node_drops_connections_and_pin() -> None:
    p, api = _make_patcher()
    p.delete_node("Code")
    p.commit()
    assert api.last_put is not None
    assert all(n["name"] != "Code" for n in api.last_put["nodes"])
    assert "Code" not in api.last_put["connections"]
    # Trigger's outgoing connection to Code should be gone.
    assert api.last_put["connections"]["Trigger"]["main"][0] == []


def test_delete_unknown_node_raises() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="node not found"):
        p.delete_node("Ghost")


# --- add_connection / delete_connection ----------------------------------


def test_add_connection_to_unknown_target_raises_before_put() -> None:
    p, api = _make_patcher()
    with pytest.raises(PatcherError, match="node not found"):
        p.add_connection(frm="Trigger", to="Ghost")
    assert api.last_put is None


def test_delete_nonexistent_connection_raises() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="connection not found"):
        p.delete_connection(frm="Trigger", to="IF")


def test_duplicate_connection_raises() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="already exists"):
        p.add_connection(frm="Trigger", to="Code")


# --- update_node ---------------------------------------------------------


def test_update_node_set_parameters() -> None:
    p, api = _make_patcher()
    p.update_node("Code", set_ops={"parameters.url": '"https://x"'})
    p.commit()
    assert api.last_put is not None
    code = next(n for n in api.last_put["nodes"] if n["name"] == "Code")
    assert code["parameters"] == {"url": "https://x"}


def test_update_node_replace_preserves_id_and_name() -> None:
    p, api = _make_patcher()
    p.update_node("Code", replace={"type": "new-type", "parameters": {"a": 1}})
    p.commit()
    code = next(n for n in api.last_put["nodes"] if n["name"] == "Code")
    assert code["id"] == "b"  # preserved
    assert code["name"] == "Code"  # preserved
    assert code["type"] == "new-type"


def test_update_node_replace_mutex_with_set() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="mutually exclusive"):
        p.update_node("Code", set_ops={"a": "1"}, replace={"type": "x"})


# --- pin-data ------------------------------------------------------------


def test_set_pin_data_on_unknown_node_raises() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="node not found"):
        p.set_pin_data("Ghost", [{"x": 1}])


def test_delete_pin_data_on_unpinned_node_raises() -> None:
    p, _ = _make_patcher()
    with pytest.raises(PatcherError, match="no pin data"):
        p.delete_pin_data("Code")


# --- commit guardrails ---------------------------------------------------


def test_commit_no_op_is_safe() -> None:
    p, api = _make_patcher()
    result = p.commit()  # no mutations
    assert api.last_put is None
    assert result.get("id") == "wf1"


def test_commit_strips_readonly_and_unknown_settings() -> None:
    wf = _chain_workflow()
    wf["updatedAt"] = "2026-04-01T00:00:00Z"  # read-only, must not go back
    wf["settings"]["binaryMode"] = "separate"  # unknown, must be stripped
    p, api = _make_patcher(wf)
    p.set_archived(False)  # any mutation to force commit
    p.commit()
    assert api.last_put is not None
    assert "updatedAt" not in api.last_put
    assert "binaryMode" not in api.last_put["settings"]
    assert api.last_put["settings"]["executionOrder"] == "v1"


def test_commit_fails_on_broken_reference() -> None:
    """A manual poke at the dict that creates a dangling reference must be caught."""
    p, api = _make_patcher()
    # Inject a dangling target without going through the public API.
    p.wf["connections"]["Code"]["main"][0].append({"node": "Ghost", "type": "main", "index": 0})
    p._dirty = True
    with pytest.raises(PatcherError, match="Ghost"):
        p.commit()
    assert api.last_put is None  # nothing was sent


# --- add_node with position override -------------------------------------


def test_add_node_explicit_position_overrides_after() -> None:
    p, api = _make_patcher()
    p.add_node(
        node_type="t",
        name="Custom",
        after="Code",
        position=[999.0, 888.0],
    )
    p.commit()
    assert api.last_put is not None
    custom = next(n for n in api.last_put["nodes"] if n["name"] == "Custom")
    assert custom["position"] == [999.0, 888.0]


# --- enable/disable ------------------------------------------------------


def test_disable_then_enable_clears_flag() -> None:
    p, api = _make_patcher()
    p.enable_node("Code", False)
    p.enable_node("Code", True)
    p.commit()
    assert api.last_put is not None
    code = next(n for n in api.last_put["nodes"] if n["name"] == "Code")
    assert "disabled" not in code  # cleared, not false


# --- list_connections ----------------------------------------------------


def test_list_connections_flattens() -> None:
    p, _ = _make_patcher()
    rows = p.list_connections()
    assert len(rows) == 2
    kinds: set[tuple[Any, Any]] = {(r["from"], r["to"]) for r in rows}
    assert kinds == {("Trigger", "Code"), ("Code", "IF")}
