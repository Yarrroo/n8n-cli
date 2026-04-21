"""`workflow.list` row and `workflow._structure` shape contracts."""

from __future__ import annotations

from n8n_cli.commands.workflow import _strip_readonly, _structure, _summary_row

_SAMPLE_WORKFLOW = {
    "id": "wf1",
    "name": "My Flow",
    "active": True,
    "isArchived": False,
    "tags": [{"id": "t1", "name": "prod"}, {"id": "t2", "name": "hot"}],
    "updatedAt": "2026-04-21T10:00:00Z",
    "createdAt": "2026-04-01T00:00:00Z",
    "versionId": "v-abc",
    "nodes": [
        {
            "name": "Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 0],
        },
        {
            "name": "Set",
            "type": "n8n-nodes-base.set",
            "typeVersion": 1,
            "disabled": True,
            "position": [200, 0],
        },
    ],
    "connections": {
        "Trigger": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
    },
    "pinData": {"Trigger": [{"json": {"x": 1}}]},
    "settings": {"executionOrder": "v1"},
}


def test_summary_row_shape() -> None:
    row = _summary_row(_SAMPLE_WORKFLOW)
    assert row == {
        "id": "wf1",
        "name": "My Flow",
        "active": True,
        "isArchived": False,
        "tags": ["prod", "hot"],
        "updatedAt": "2026-04-21T10:00:00Z",
    }


def test_structure_flattens_connections() -> None:
    s = _structure(_SAMPLE_WORKFLOW)
    assert s["id"] == "wf1"
    assert [n["name"] for n in s["nodes"]] == ["Trigger", "Set"]
    # Disabled flag preserved.
    assert s["nodes"][1]["disabled"] is True
    assert s["connections"] == [
        {"from": "Trigger", "fromOutput": 0, "to": "Set", "toInput": 0, "type": "main"},
    ]
    assert s["pinnedNodes"] == ["Trigger"]


def test_structure_handles_empty_workflow() -> None:
    s = _structure({"id": "x", "name": "Empty"})
    assert s["nodes"] == []
    assert s["connections"] == []
    assert s["pinnedNodes"] == []


def test_strip_readonly_drops_server_fields() -> None:
    stripped = _strip_readonly(_SAMPLE_WORKFLOW)
    for forbidden in ("id", "active", "isArchived", "createdAt", "updatedAt", "versionId", "tags"):
        assert forbidden not in stripped
    for keep in ("name", "nodes", "connections", "settings", "pinData"):
        assert keep in stripped


def test_strip_readonly_filters_unknown_settings_keys() -> None:
    # `binaryMode` comes back on GET but n8n's create endpoint rejects it with
    # "settings must NOT have additional properties". Real issue hit in Phase 1.
    wf = {
        "name": "X",
        "nodes": [],
        "connections": {},
        "settings": {
            "executionOrder": "v1",
            "binaryMode": "separate",  # unknown — must be dropped
            "availableInMCP": False,
        },
    }
    stripped = _strip_readonly(wf)
    assert stripped["settings"] == {"executionOrder": "v1", "availableInMCP": False}
