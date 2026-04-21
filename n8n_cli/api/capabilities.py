"""Capability → backend mapping.

This module exists so command modules never hardcode "public vs frontend".
When the map changes (a new n8n release moves an endpoint from /rest to
/api/v1), only this file is touched.

For Phase 1 we only list capabilities backed by `/api/v1/*`. Later phases
expand the map with `/rest/*` routes (folders, workflow run, credential
list/get/update, share, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Backend = Literal["public", "frontend"]


@dataclass(frozen=True)
class Capability:
    name: str
    backend: Backend
    path: str
    method: str = "GET"


CAPABILITIES: dict[str, Capability] = {
    # --- workflows (Phase 1) ---
    "workflow.list": Capability("workflow.list", "public", "/api/v1/workflows"),
    "workflow.get": Capability("workflow.get", "public", "/api/v1/workflows/{id}"),
    "workflow.create": Capability("workflow.create", "public", "/api/v1/workflows", method="POST"),
    "workflow.update": Capability(
        "workflow.update", "public", "/api/v1/workflows/{id}", method="PUT"
    ),
    "workflow.delete": Capability(
        "workflow.delete", "public", "/api/v1/workflows/{id}", method="DELETE"
    ),
    "workflow.activate": Capability(
        "workflow.activate", "public", "/api/v1/workflows/{id}/activate", method="POST"
    ),
    "workflow.deactivate": Capability(
        "workflow.deactivate", "public", "/api/v1/workflows/{id}/deactivate", method="POST"
    ),
    "workflow.transfer": Capability(
        "workflow.transfer", "public", "/api/v1/workflows/{id}/transfer", method="PUT"
    ),
    "workflow.tags.get": Capability("workflow.tags.get", "public", "/api/v1/workflows/{id}/tags"),
    "workflow.tags.set": Capability(
        "workflow.tags.set", "public", "/api/v1/workflows/{id}/tags", method="PUT"
    ),
    # --- executions (Phase 2 will add .get_data / .retry) ---
    "execution.list": Capability("execution.list", "public", "/api/v1/executions"),
    "execution.get": Capability("execution.get", "public", "/api/v1/executions/{id}"),
    "execution.delete": Capability(
        "execution.delete", "public", "/api/v1/executions/{id}", method="DELETE"
    ),
    "execution.retry": Capability(
        "execution.retry", "public", "/api/v1/executions/{id}/retry", method="POST"
    ),
    # --- tags, projects, variables — listed so help is accurate ---
    "tag.list": Capability("tag.list", "public", "/api/v1/tags"),
    "project.list": Capability("project.list", "public", "/api/v1/projects"),
}


def get(name: str) -> Capability:
    try:
        return CAPABILITIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown capability: {name!r}") from exc
