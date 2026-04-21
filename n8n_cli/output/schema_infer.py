"""JSON schema inference for arbitrary items.

The output is NOT a JSON-Schema document — it's a compact human-readable
description ("string", "array<integer>", {"a": "string"}, ...) optimized for
LLM consumption: short, flat, unambiguous.

Union handling: when items have incompatible shapes, return
`{"oneOf": [shape_a, shape_b, ...]}`. Two dict shapes are merged (rather
than made a union) when their key-sets overlap by ≥70% — missing keys are
marked with a trailing `?` to signal "optional".
"""

from __future__ import annotations

import re
from typing import Any

_ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

Schema = Any  # recursive: str | dict[str, "Schema"] | {"oneOf": [Schema, ...]}

_UNION_MERGE_THRESHOLD = 0.7  # ≥70% shared keys → merge with optional marks


def infer_schema(items: list[Any]) -> Schema:
    """Infer a schema describing all items in the list.

    Returns:
      - "empty" if the list is empty
      - a single shape if all items share it (or can be merged)
      - {"oneOf": [shape, ...]} for truly incompatible shapes
    """
    if not items:
        return "empty"
    shapes = [_shape_of(x) for x in items]
    return _merge_shapes(shapes)


def _shape_of(value: Any) -> Schema:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        if _ISO_DATE_RE.match(value):
            return "string (ISO date)"
        if _UUID_RE.match(value):
            return "string (UUID)"
        return "string"
    if isinstance(value, list):
        if not value:
            return "array<empty>"
        inner = _merge_shapes([_shape_of(x) for x in value])
        return f"array<{_render(inner)}>" if isinstance(inner, str) else {"array": inner}
    if isinstance(value, dict):
        return {k: _shape_of(v) for k, v in value.items()}
    return type(value).__name__


def _render(shape: Schema) -> str:
    """Render a scalar shape back to a string (for array<...> composition)."""
    return shape if isinstance(shape, str) else "object"


def _merge_shapes(shapes: list[Schema]) -> Schema:
    """Merge a list of individual shapes into one description."""
    if not shapes:
        return "empty"
    if len(shapes) == 1:
        return shapes[0]

    # De-duplicate by serializable form.
    uniq: list[Schema] = []
    seen: set[str] = set()
    for s in shapes:
        key = repr(s)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    if len(uniq) == 1:
        return uniq[0]

    # If all shapes are string primitives (including `"string (ISO date)"`),
    # collapse into a single union string.
    if all(isinstance(s, str) for s in uniq):
        return {"oneOf": uniq}

    # Try to merge dict shapes with overlapping keys.
    dict_shapes = [s for s in uniq if isinstance(s, dict) and "oneOf" not in s]
    other_shapes = [s for s in uniq if not (isinstance(s, dict) and "oneOf" not in s)]
    if dict_shapes and not other_shapes:
        merged = _try_merge_dicts(dict_shapes)
        if merged is not None:
            return merged

    return {"oneOf": uniq}


def _try_merge_dicts(dicts: list[dict[str, Schema]]) -> dict[str, Schema] | None:
    """Merge dicts that share ≥70% of keys. Optional keys get a `?` suffix."""
    all_keys: set[str] = set()
    for d in dicts:
        all_keys |= set(d.keys())
    shared = set.intersection(*(set(d.keys()) for d in dicts)) if dicts else set()
    if not all_keys or len(shared) / len(all_keys) < _UNION_MERGE_THRESHOLD:
        return None
    merged: dict[str, Schema] = {}
    for key in sorted(all_keys):
        present = [d[key] for d in dicts if key in d]
        value_shape = _merge_shapes(present)
        label = key if key in shared else f"{key}?"
        merged[label] = value_shape
    return merged
