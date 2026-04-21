"""Find and rewrite node-name references inside a workflow.

n8n identifies nodes by their `name` (not id) in every place that links to
them: `connections` uses node names as **top-level keys** (source) AND as
values in the nested `{"node": ...}` objects (target), and `pinData` uses
node names as keys. Miss any location when renaming → workflow breaks.

All functions here operate on a live workflow dict in-place (for the
mutation API) or return a mapping (for the read API).
"""

from __future__ import annotations

from typing import Any


def find_node_references(workflow: dict[str, Any], node_name: str) -> list[str]:
    """Return a list of human-readable locations where `node_name` appears.

    Each entry looks like:
      - "connections[source:Foo]"           (Foo is a source node)
      - "connections[Foo -> main[0] -> node]"  (Foo is a downstream target)
      - "pinData[Foo]"                      (Foo has pinned data)
    """
    out: list[str] = []
    conns = workflow.get("connections") or {}
    for src, buckets in conns.items():
        if src == node_name:
            out.append(f"connections[source:{src}]")
        for conn_type, outputs in (buckets or {}).items():
            for out_idx, targets in enumerate(outputs or []):
                for t in targets or []:
                    if isinstance(t, dict) and t.get("node") == node_name:
                        out.append(f"connections[{src} -> {conn_type}[{out_idx}] -> {node_name}]")
    pin = workflow.get("pinData") or {}
    if node_name in pin:
        out.append(f"pinData[{node_name}]")
    return out


def replace_node_references(workflow: dict[str, Any], old: str, new: str) -> int:
    """In-place rename of `old` → `new` everywhere. Returns count of touches.

    Idempotent: a second call with the same args is a no-op (0 replacements).
    """
    if old == new:
        return 0
    count = 0

    # 1) connections — rekey the outer dict AND rewrite every `"node": old` value.
    conns = workflow.get("connections")
    if isinstance(conns, dict):
        # Rekey source: we need to rewrite in a fresh dict so insertion order is
        # preserved for unchanged neighbors.
        if old in conns:
            rekeyed: dict[str, Any] = {}
            for k, v in conns.items():
                if k == old:
                    rekeyed[new] = v
                    count += 1
                else:
                    rekeyed[k] = v
            workflow["connections"] = rekeyed
            conns = rekeyed
        # Rewrite target references inside every bucket.
        for buckets in conns.values():
            if not isinstance(buckets, dict):
                continue
            for outputs in buckets.values():
                if not isinstance(outputs, list):
                    continue
                for targets in outputs:
                    if not isinstance(targets, list):
                        continue
                    for t in targets:
                        if isinstance(t, dict) and t.get("node") == old:
                            t["node"] = new
                            count += 1

    # 2) pinData — rekey.
    pin = workflow.get("pinData")
    if isinstance(pin, dict) and old in pin:
        pin[new] = pin.pop(old)
        count += 1

    return count


def validate_reference_integrity(workflow: dict[str, Any]) -> list[str]:
    """Return a list of error messages for broken references; empty means OK.

    Used by `WorkflowPatcher._validate` as a dry-run gate before PUT.
    """
    issues: list[str] = []
    node_names = {n.get("name") for n in (workflow.get("nodes") or []) if n.get("name")}
    conns = workflow.get("connections") or {}
    for src, buckets in conns.items():
        if src not in node_names:
            issues.append(f"connections: source {src!r} does not exist in nodes[]")
        for conn_type, outputs in (buckets or {}).items():
            for out_idx, targets in enumerate(outputs or []):
                for t in targets or []:
                    if isinstance(t, dict):
                        tgt = t.get("node")
                        if tgt not in node_names:
                            issues.append(
                                f"connections[{src} -> {conn_type}[{out_idx}]]: "
                                f"target {tgt!r} does not exist in nodes[]"
                            )
    pin = workflow.get("pinData") or {}
    for pinned in pin:
        if pinned not in node_names:
            issues.append(f"pinData[{pinned!r}]: node does not exist in nodes[]")
    # Duplicate node names would silently break connections — catch here.
    seen: set[str] = set()
    for n in workflow.get("nodes") or []:
        name = n.get("name")
        if not name:
            issues.append(f"node with id={n.get('id')!r} has no name")
            continue
        if name in seen:
            issues.append(f"duplicate node name: {name!r}")
        seen.add(name)
    return issues
