"""Thin wrappers over `/api/v1/*` endpoints.

Each method maps one-to-one to an HTTP call. No business logic here — that
belongs to `core/` (patcher, summarizer) and to command handlers. Return
types are plain dicts for Phase 1; later phases may migrate hot paths to
pydantic models once the shapes stabilize across n8n versions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from n8n_cli.api import capabilities as caps
from n8n_cli.api.transport import Transport


def _as_dict(value: Any) -> dict[str, Any]:
    """Narrow transport's `Any` return to a dict (n8n always returns objects here)."""
    return cast(dict[str, Any], value)


class PublicApi:
    """High-level client for the n8n public REST API (/api/v1).

    Methods are grouped by resource. Pagination is abstracted away for list
    endpoints — they return iterators that transparently follow `nextCursor`.
    """

    def __init__(self, transport: Transport) -> None:
        self.t = transport

    # --- workflows ---

    def list_workflows(
        self,
        *,
        active: bool | None = None,
        tags: str | None = None,
        name: str | None = None,
        project_id: str | None = None,
        exclude_pin_data: bool = False,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        cap = caps.get("workflow.list")
        return self.t.paginate(
            cap.path,
            active=active,
            tags=tags,
            name=name,
            projectId=project_id,
            excludePinnedData=exclude_pin_data,
            limit=limit,
        )

    def get_workflow(self, workflow_id: str, *, exclude_pin_data: bool = False) -> dict[str, Any]:
        cap = caps.get("workflow.get")
        return _as_dict(
            self.t.get(cap.path.format(id=workflow_id), excludePinnedData=exclude_pin_data)
        )

    def create_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        cap = caps.get("workflow.create")
        return _as_dict(self.t.post(cap.path, json=workflow))

    def update_workflow(self, workflow_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
        cap = caps.get("workflow.update")
        return _as_dict(self.t.put(cap.path.format(id=workflow_id), json=workflow))

    def delete_workflow(self, workflow_id: str) -> dict[str, Any]:
        cap = caps.get("workflow.delete")
        return _as_dict(self.t.delete(cap.path.format(id=workflow_id)))

    def activate_workflow(self, workflow_id: str) -> dict[str, Any]:
        cap = caps.get("workflow.activate")
        return _as_dict(self.t.post(cap.path.format(id=workflow_id)))

    def deactivate_workflow(self, workflow_id: str) -> dict[str, Any]:
        cap = caps.get("workflow.deactivate")
        return _as_dict(self.t.post(cap.path.format(id=workflow_id)))

    # --- executions ---

    def list_executions(
        self,
        *,
        workflow_id: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        include_data: bool = False,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        cap = caps.get("execution.list")
        return self.t.paginate(
            cap.path,
            workflowId=workflow_id,
            status=status,
            projectId=project_id,
            includeData=include_data,
            limit=limit,
        )

    def get_execution(
        self, execution_id: int | str, *, include_data: bool = False
    ) -> dict[str, Any]:
        cap = caps.get("execution.get")
        return _as_dict(self.t.get(cap.path.format(id=execution_id), includeData=include_data))

    def delete_execution(self, execution_id: int | str) -> dict[str, Any]:
        cap = caps.get("execution.delete")
        return _as_dict(self.t.delete(cap.path.format(id=execution_id)))

    def retry_execution(self, execution_id: int | str) -> dict[str, Any]:
        cap = caps.get("execution.retry")
        return _as_dict(self.t.post(cap.path.format(id=execution_id)))

    # --- smoke-probe used by `auth status` ---

    def ping(self) -> dict[str, Any]:
        """Cheapest call that actually exercises auth: one workflow, any state."""
        return _as_dict(self.t.get("/api/v1/workflows", limit=1))
