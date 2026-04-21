"""Dot-notation mutation for `--set key.path=value` CLI UX.

Example:
    apply_set_ops(node, {"parameters.url": "https://x", "disabled": "true"})
    # Mutates node in place:
    #   node["parameters"]["url"] = "https://x"
    #   node["disabled"] = True        (json.loads coerces "true" → bool)

Values are attempted as JSON first (so `true`, `5`, `null`, `[1,2]`, `{...}`
all round-trip properly) and fall back to the raw string if that fails.
Intermediate path segments are auto-created as dicts.
"""

from __future__ import annotations

import json
from typing import Any


def apply_set_ops(target: dict[str, Any], ops: dict[str, str]) -> None:
    """In-place assignment of every `dot.path=value` op on `target`."""
    for path, raw in ops.items():
        _set_one(target, path, _parse_value(raw))


def apply_json_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """RFC-7396-ish recursive merge patch (nulls delete keys).

    n8n's own internals aren't strict about RFC 7396, so this is the
    "shallow + recurse dicts, replace everything else" variant.
    """
    for k, v in patch.items():
        if v is None:
            target.pop(k, None)
            continue
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            apply_json_merge(target[k], v)
        else:
            target[k] = v


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _set_one(obj: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cursor: Any = obj
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if last:
            cursor[part] = value
            return
        # Create intermediate dicts on demand — matches mkdir -p semantics.
        nxt = cursor.get(part) if isinstance(cursor, dict) else None
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
