"""Schema inference for arbitrary JSON items."""

from __future__ import annotations

from n8n_cli.output.schema_infer import infer_schema


def test_empty_list_returns_empty() -> None:
    assert infer_schema([]) == "empty"


def test_primitives() -> None:
    assert infer_schema([1, 2, 3]) == "integer"
    assert infer_schema([1.5]) == "number"
    assert infer_schema([True, False]) == "boolean"
    assert infer_schema([None]) == "null"
    assert infer_schema(["a", "b"]) == "string"


def test_iso_date_and_uuid_detection() -> None:
    assert infer_schema(["2026-04-21T10:00:00Z"]) == "string (ISO date)"
    assert infer_schema(["2026-04-21"]) == "string (ISO date)"
    assert infer_schema(["550e8400-e29b-41d4-a716-446655440000"]) == "string (UUID)"


def test_uniform_object_shape() -> None:
    items = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert infer_schema(items) == {"id": "integer", "name": "string"}


def test_overlapping_objects_merge_with_optional_marker() -> None:
    # 3/4 shared keys = 75% >= threshold → merge with `?` for missing.
    items = [
        {"id": 1, "name": "a", "email": "x@y", "tag": "hot"},
        {"id": 2, "name": "b", "email": "x@y"},
    ]
    schema = infer_schema(items)
    assert isinstance(schema, dict)
    assert set(schema.keys()) == {"id", "name", "email", "tag?"}


def test_divergent_objects_yield_oneof() -> None:
    items = [{"id": 1}, {"name": "a"}, {"foo": True}]
    schema = infer_schema(items)
    assert "oneOf" in schema


def test_nested_arrays() -> None:
    items = [[1, 2], [3, 4]]
    # Outer is array, inner all integers.
    schema = infer_schema(items)
    # The top-level list has a single shape (array<integer>).
    assert schema == "array<integer>"


def test_mixed_primitives_union() -> None:
    items = ["a", 1, True]
    schema = infer_schema(items)
    assert schema == {"oneOf": ["string", "integer", "boolean"]}
