"""Node reference find/replace across connections + pinData."""

from __future__ import annotations

from n8n_cli.core.refs import (
    find_node_references,
    replace_node_references,
    validate_reference_integrity,
)


def _fresh_workflow() -> dict:
    return {
        "nodes": [
            {"id": "1", "name": "Trigger", "type": "t"},
            {"id": "2", "name": "Middle", "type": "t"},
            {"id": "3", "name": "End", "type": "t"},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Middle", "type": "main", "index": 0}]]},
            "Middle": {"main": [[{"node": "End", "type": "main", "index": 0}]]},
        },
        "pinData": {"Trigger": [{"x": 1}]},
    }


def test_find_references_source_target_pin() -> None:
    wf = _fresh_workflow()
    locs = find_node_references(wf, "Middle")
    assert any("source:Middle" in s for s in locs)
    assert any("-> Middle" in s for s in locs)


def test_replace_cascades_through_source_target_and_pin() -> None:
    wf = _fresh_workflow()
    n = replace_node_references(wf, "Trigger", "Start")
    # 1 source rekey + 1 pinData rekey = 2.
    assert n == 2
    assert "Start" in wf["connections"]
    assert "Trigger" not in wf["connections"]
    assert "Start" in wf["pinData"]
    assert "Trigger" not in wf["pinData"]


def test_replace_when_node_has_no_refs_is_zero() -> None:
    wf = _fresh_workflow()
    # `End` is only a connection target, not source, and has no pin data.
    n = replace_node_references(wf, "End", "Finish")
    assert n == 1  # the "-> End" target reference inside Middle's outputs
    assert wf["connections"]["Middle"]["main"][0][0]["node"] == "Finish"


def test_replace_self_loop_renames_both_sides() -> None:
    wf = {
        "nodes": [{"id": "1", "name": "Loop", "type": "t"}],
        "connections": {
            "Loop": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},
        },
    }
    n = replace_node_references(wf, "Loop", "Cycle")
    # Source rekey + target rewrite.
    assert n == 2
    assert "Cycle" in wf["connections"]
    assert wf["connections"]["Cycle"]["main"][0][0]["node"] == "Cycle"


def test_replace_same_name_is_noop() -> None:
    wf = _fresh_workflow()
    assert replace_node_references(wf, "Middle", "Middle") == 0


def test_validate_detects_broken_connection() -> None:
    wf = _fresh_workflow()
    # Add a dangling target.
    wf["connections"]["Middle"]["main"][0].append({"node": "Ghost", "type": "main", "index": 0})
    issues = validate_reference_integrity(wf)
    assert any("Ghost" in i for i in issues)


def test_validate_detects_orphan_pin_data() -> None:
    wf = _fresh_workflow()
    wf["pinData"]["Phantom"] = [{"x": 1}]
    issues = validate_reference_integrity(wf)
    assert any("Phantom" in i for i in issues)


def test_validate_detects_duplicate_node_names() -> None:
    wf = _fresh_workflow()
    wf["nodes"].append({"id": "dup", "name": "Middle", "type": "t"})
    issues = validate_reference_integrity(wf)
    assert any("duplicate node name" in i for i in issues)


def test_validate_clean_workflow_has_no_issues() -> None:
    wf = _fresh_workflow()
    assert validate_reference_integrity(wf) == []
