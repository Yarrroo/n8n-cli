"""Navigate execution JSON to pull one node's output items."""

from __future__ import annotations

import pytest

from n8n_cli.core.runpath import (
    NodeRunNotFoundError,
    executed_nodes,
    extract_node_error,
    extract_node_items,
)


def test_extract_node_error_returns_none_on_success() -> None:
    ex = {"data": {"resultData": {"runData": {"A": [{"data": {"main": [[{"json": {}}]]}}]}}}}
    assert extract_node_error(ex, "A") is None


def test_extract_node_error_surfaces_error_record() -> None:
    ex = {
        "data": {
            "resultData": {
                "runData": {
                    "HTTP Request": [
                        {
                            "error": {
                                "message": "404 Not Found",
                                "description": "bad path",
                                "httpCode": "404",
                                "name": "NodeApiError",
                            }
                        }
                    ]
                }
            }
        }
    }
    err = extract_node_error(ex, "HTTP Request")
    assert err is not None
    assert err["message"] == "404 Not Found"
    assert err["httpCode"] == "404"


def test_extract_node_error_missing_node_returns_none() -> None:
    ex = {"data": {"resultData": {"runData": {}}}}
    assert extract_node_error(ex, "nope") is None


_EXECUTION = {
    "id": 1,
    "status": "success",
    "data": {
        "resultData": {
            "runData": {
                "Trigger": [
                    {
                        "startTime": 1000,
                        "executionTime": 10,
                        "data": {"main": [[{"json": {"x": 1}}]]},
                    }
                ],
                "Code": [
                    {
                        "startTime": 1020,
                        "executionTime": 42,
                        "data": {
                            "main": [
                                [{"json": {"a": 1}}, {"json": {"a": 2}}],
                                [{"json": {"side": "alt"}}],
                            ]
                        },
                    }
                ],
            }
        }
    },
}


def test_executed_nodes_sorted() -> None:
    assert executed_nodes(_EXECUTION) == ["Code", "Trigger"]


def test_extracts_default_run_and_output() -> None:
    items, meta = extract_node_items(_EXECUTION, "Code")
    assert len(items) == 2
    assert items[0]["json"] == {"a": 1}
    assert meta["executionTime"] == 42
    assert "data" not in meta


def test_extracts_alternate_output() -> None:
    items, _ = extract_node_items(_EXECUTION, "Code", output_index=1)
    assert items == [{"json": {"side": "alt"}}]


def test_missing_node_raises_with_list() -> None:
    with pytest.raises(NodeRunNotFoundError) as excinfo:
        extract_node_items(_EXECUTION, "Nonexistent")
    assert "Code" in str(excinfo.value)
    assert "Trigger" in str(excinfo.value)


def test_out_of_range_output_raises() -> None:
    with pytest.raises(NodeRunNotFoundError):
        extract_node_items(_EXECUTION, "Code", output_index=5)


def test_empty_execution_is_fine() -> None:
    assert executed_nodes({}) == []
    assert executed_nodes({"data": {}}) == []
