"""WorkflowPatcher — atomic mutation engine.

All node/connection/pin-data edits go through this class. Lifecycle:

    patcher = WorkflowPatcher(api, workflow_id)   # GET workflow
    patcher.add_node(...)
    patcher.rename_node("Foo", "Bar")             # cascades refs
    patcher.set_pin_data("Bar", [...])
    patcher.commit()                               # PUT (or raise if no-ops)

Dry-run validation runs before every commit: reference integrity, duplicate
names, pinData pointing at ghost nodes. A failure raises `PatcherError`
BEFORE the network PUT, so the workflow stays unchanged on the server.

The patcher mutates its local `self.wf` dict; it never touches the server
until `commit()`.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from n8n_cli.api.errors import UserError
from n8n_cli.api.public import PublicApi
from n8n_cli.core import refs
from n8n_cli.core.dotset import apply_json_merge, apply_set_ops


class PatcherError(UserError):
    """Raised when a mutation would produce an invalid workflow."""


# Same whitelist as commands/workflow.py::_WRITABLE_WORKFLOW_FIELDS — kept
# in lockstep. Any field not here is dropped before PUT.
_WRITABLE_WORKFLOW_FIELDS = frozenset(
    {"name", "nodes", "connections", "settings", "staticData", "pinData"}
)
_WRITABLE_SETTINGS_FIELDS = frozenset(
    {
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
        "timeSavedPerExecution",
        "availableInMCP",
    }
)


class WorkflowPatcher:
    def __init__(self, api: PublicApi, workflow_id: str) -> None:
        self.api = api
        self.workflow_id = workflow_id
        self.wf: dict[str, Any] = api.get_workflow(workflow_id)
        self._dirty = False

    # --- node-level ops ---

    def find_node(self, name: str) -> dict[str, Any]:
        for n in self.wf.get("nodes") or []:
            if isinstance(n, dict) and n.get("name") == name:
                return n
        raise PatcherError(f"node not found: {name!r}")

    def add_node(
        self,
        *,
        node_type: str,
        name: str,
        parameters: dict[str, Any] | None = None,
        type_version: float | None = None,
        position: list[float] | None = None,
        credentials: dict[str, Any] | None = None,
        after: str | None = None,
        disabled: bool = False,
    ) -> dict[str, Any]:
        nodes = self.wf.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
            self.wf["nodes"] = nodes
        if any(n.get("name") == name for n in nodes):
            raise PatcherError(f"node with name {name!r} already exists")

        anchor: dict[str, Any] | None = None
        if after is not None:
            anchor = self.find_node(after)

        if position is None:
            if anchor is not None and isinstance(anchor.get("position"), list):
                ax, ay = anchor["position"][0], anchor["position"][1]
                position = [float(ax) + 240.0, float(ay)]
            else:
                position = [0.0, 0.0]

        new_node: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": name,
            "type": node_type,
            "typeVersion": type_version if type_version is not None else 1,
            "position": position,
            "parameters": parameters or {},
        }
        if credentials is not None:
            new_node["credentials"] = credentials
        if disabled:
            new_node["disabled"] = True
        nodes.append(new_node)

        # Auto-connect the new node to the anchor's first output.
        if anchor is not None:
            self.add_connection(
                frm=anchor["name"], to=name, from_output=0, to_input=0, conn_type="main"
            )

        self._dirty = True
        return new_node

    def update_node(
        self,
        name: str,
        *,
        set_ops: dict[str, str] | None = None,
        json_merge: dict[str, Any] | None = None,
        replace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if replace is not None and (set_ops or json_merge):
            raise PatcherError("replace is mutually exclusive with --set/--json")
        node = self.find_node(name)
        if replace is not None:
            # Preserve id + name; everything else comes from the new payload.
            preserved_id = node.get("id")
            preserved_name = node.get("name")
            node.clear()
            node.update(replace)
            node.setdefault("id", preserved_id)
            node.setdefault("name", preserved_name)
        if set_ops:
            apply_set_ops(node, set_ops)
        if json_merge:
            apply_json_merge(node, json_merge)
        self._dirty = True
        return node

    def rename_node(self, old: str, new: str) -> int:
        if old == new:
            return 0
        if any(n.get("name") == new for n in self.wf.get("nodes") or []):
            raise PatcherError(f"cannot rename to {new!r}: name already taken")
        node = self.find_node(old)
        node["name"] = new
        cascades = refs.replace_node_references(self.wf, old, new)
        self._dirty = True
        # +1 for the node's own name write (not counted inside refs).
        return cascades + 1

    def delete_node(self, name: str) -> None:
        nodes = self.wf.get("nodes") or []
        idx = next((i for i, n in enumerate(nodes) if n.get("name") == name), -1)
        if idx < 0:
            raise PatcherError(f"node not found: {name!r}")
        nodes.pop(idx)
        # Drop connections where this node is source OR target.
        conns = self.wf.get("connections")
        if isinstance(conns, dict):
            conns.pop(name, None)
            for buckets in list(conns.values()):
                if not isinstance(buckets, dict):
                    continue
                for outputs in buckets.values():
                    if not isinstance(outputs, list):
                        continue
                    for i, targets in enumerate(outputs):
                        if not isinstance(targets, list):
                            continue
                        outputs[i] = [
                            t
                            for t in targets
                            if not (isinstance(t, dict) and t.get("node") == name)
                        ]
        # Drop pinData.
        pin = self.wf.get("pinData")
        if isinstance(pin, dict):
            pin.pop(name, None)
        self._dirty = True

    def enable_node(self, name: str, enabled: bool) -> None:
        node = self.find_node(name)
        if enabled:
            node.pop("disabled", None)
        else:
            node["disabled"] = True
        self._dirty = True

    # --- connection-level ops ---

    def add_connection(
        self,
        *,
        frm: str,
        to: str,
        from_output: int = 0,
        to_input: int = 0,
        conn_type: str = "main",
    ) -> None:
        # Both endpoints must exist.
        self.find_node(frm)
        self.find_node(to)
        conns = self.wf.get("connections")
        if not isinstance(conns, dict):
            conns = {}
            self.wf["connections"] = conns
        bucket = conns.setdefault(frm, {})
        outputs = bucket.setdefault(conn_type, [])
        while len(outputs) <= from_output:
            outputs.append([])
        targets = outputs[from_output]
        if not isinstance(targets, list):
            targets = []
            outputs[from_output] = targets
        if any(
            isinstance(t, dict)
            and t.get("node") == to
            and t.get("index", 0) == to_input
            and t.get("type", "main") == conn_type
            for t in targets
        ):
            raise PatcherError(
                f"connection already exists: {frm}[{from_output}] → {to}[{to_input}] ({conn_type})"
            )
        targets.append({"node": to, "type": conn_type, "index": to_input})
        self._dirty = True

    def delete_connection(
        self,
        *,
        frm: str,
        to: str,
        from_output: int = 0,
        to_input: int = 0,
        conn_type: str = "main",
    ) -> None:
        conns = self.wf.get("connections") or {}
        bucket = conns.get(frm) or {}
        outputs = bucket.get(conn_type) or []
        if from_output >= len(outputs):
            raise PatcherError(f"no output index {from_output} on source {frm!r}")
        targets = outputs[from_output] or []
        before = len(targets)
        outputs[from_output] = [
            t
            for t in targets
            if not (
                isinstance(t, dict)
                and t.get("node") == to
                and t.get("index", 0) == to_input
                and t.get("type", "main") == conn_type
            )
        ]
        if len(outputs[from_output]) == before:
            raise PatcherError(
                f"connection not found: {frm}[{from_output}] → {to}[{to_input}] ({conn_type})"
            )
        self._dirty = True

    def list_connections(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for src, buckets in (self.wf.get("connections") or {}).items():
            for conn_type, outputs in (buckets or {}).items():
                for out_idx, targets in enumerate(outputs or []):
                    for t in targets or []:
                        if isinstance(t, dict):
                            out.append(
                                {
                                    "from": src,
                                    "fromOutput": out_idx,
                                    "to": t.get("node"),
                                    "toInput": t.get("index", 0),
                                    "type": conn_type,
                                }
                            )
        return out

    # --- pin-data ---

    def set_pin_data(self, node_name: str, items: list[Any]) -> None:
        self.find_node(node_name)  # existence check
        pin = self.wf.get("pinData")
        if not isinstance(pin, dict):
            pin = {}
            self.wf["pinData"] = pin
        pin[node_name] = items
        self._dirty = True

    def delete_pin_data(self, node_name: str) -> None:
        pin = self.wf.get("pinData")
        if not isinstance(pin, dict) or node_name not in pin:
            raise PatcherError(f"no pin data for node {node_name!r}")
        del pin[node_name]
        self._dirty = True

    # --- meta ---

    def set_archived(self, value: bool) -> None:
        self.wf["isArchived"] = value
        self._dirty = True

    def set_workflow_fields(
        self,
        *,
        name: str | None = None,
        settings_set: dict[str, str] | None = None,
        settings_merge: dict[str, Any] | None = None,
    ) -> None:
        if name is not None:
            self.wf["name"] = name
        if settings_set or settings_merge:
            settings = self.wf.setdefault("settings", {})
            if settings_set:
                apply_set_ops(settings, settings_set)
            if settings_merge:
                apply_json_merge(settings, settings_merge)
        self._dirty = True

    # --- commit ---

    def commit(self) -> dict[str, Any]:
        if not self._dirty:
            return self.wf
        errors = refs.validate_reference_integrity(self.wf)
        if errors:
            raise PatcherError("workflow integrity check failed:\n  - " + "\n  - ".join(errors))
        payload = self._prepare_payload()
        return self.api.update_workflow(self.workflow_id, payload)

    def _prepare_payload(self) -> dict[str, Any]:
        """Deep-copy + strip read-only fields before we send."""
        out = {k: deepcopy(v) for k, v in self.wf.items() if k in _WRITABLE_WORKFLOW_FIELDS}
        settings = out.get("settings")
        if isinstance(settings, dict):
            out["settings"] = {k: v for k, v in settings.items() if k in _WRITABLE_SETTINGS_FIELDS}
        return out
