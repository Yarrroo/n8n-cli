"""Dot-notation mutation + JSON-merge patch semantics."""

from __future__ import annotations

from n8n_cli.core.dotset import apply_json_merge, apply_set_ops


def test_scalar_assignment_creates_intermediate_dicts() -> None:
    obj: dict = {}
    apply_set_ops(obj, {"parameters.url": "https://x"})
    assert obj == {"parameters": {"url": "https://x"}}


def test_json_typed_values() -> None:
    obj: dict = {}
    apply_set_ops(
        obj,
        {
            "a.b": "true",
            "a.c": "5",
            "a.d": "null",
            "a.e": '"quoted"',
            "a.f": "[1, 2]",
            "a.g": "plain",  # invalid JSON → kept as string
        },
    )
    assert obj["a"]["b"] is True
    assert obj["a"]["c"] == 5
    assert obj["a"]["d"] is None
    assert obj["a"]["e"] == "quoted"
    assert obj["a"]["f"] == [1, 2]
    assert obj["a"]["g"] == "plain"


def test_overwrites_non_dict_intermediate() -> None:
    obj: dict = {"parameters": "oldstr"}
    apply_set_ops(obj, {"parameters.url": "https://x"})
    assert obj == {"parameters": {"url": "https://x"}}


def test_json_merge_recurses_into_dicts() -> None:
    obj = {"settings": {"timezone": "UTC", "retries": 3}}
    apply_json_merge(obj, {"settings": {"retries": 5, "extra": True}})
    assert obj == {"settings": {"timezone": "UTC", "retries": 5, "extra": True}}


def test_json_merge_null_deletes_key() -> None:
    obj = {"a": 1, "b": 2}
    apply_json_merge(obj, {"b": None})
    assert obj == {"a": 1}


def test_json_merge_replaces_non_dict() -> None:
    obj = {"list": [1, 2, 3]}
    apply_json_merge(obj, {"list": [9]})
    assert obj == {"list": [9]}
