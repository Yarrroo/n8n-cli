"""Resolve folder paths like 'Ops/Billing/Invoices' to/from folder ids.

Folders form a tree inside a project. The frontend API exposes only a flat
list (with `parentFolderId`) plus a per-folder `/tree` endpoint. This
resolver loads the flat list once per CLI invocation and builds both
directions (path → id and id → path).

Splitting + joining on `/` — n8n itself doesn't seem to enforce anything
about slashes in folder names in the UI, so if someone gets cute with a
slash in a name our path will ambiguate. We accept that trade-off; the
`--folder <id>` escape hatch covers edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from n8n_cli.api.errors import UserError
from n8n_cli.api.frontend import FrontendApi

_SEP = "/"


@dataclass
class FolderInfo:
    id: str
    name: str
    parent_folder_id: str | None


class FolderPathResolver:
    def __init__(self, api: FrontendApi, project_id: str) -> None:
        self.api = api
        self.project_id = project_id
        self._by_id: dict[str, FolderInfo] = {}
        self._by_path: dict[str, str] = {}  # "A/B/C" → id
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        raw = self.api.list_folders(self.project_id, take=1000)
        for entry in raw:
            fid = entry.get("id")
            name = entry.get("name")
            if not (isinstance(fid, str) and isinstance(name, str)):
                continue
            pf = entry.get("parentFolder")
            parent_id = pf.get("id") if isinstance(pf, dict) else entry.get("parentFolderId")
            if parent_id is not None and not isinstance(parent_id, str):
                parent_id = None
            self._by_id[fid] = FolderInfo(id=fid, name=name, parent_folder_id=parent_id)
        # Build id → path by walking parents.
        for fid in self._by_id:
            path = self._build_path(fid)
            if path:
                self._by_path[path] = fid
        self._loaded = True

    def _build_path(self, fid: str) -> str:
        seen: set[str] = set()
        parts: list[str] = []
        cursor: str | None = fid
        while cursor and cursor not in seen:
            seen.add(cursor)
            node = self._by_id.get(cursor)
            if node is None:
                return ""
            parts.append(node.name)
            cursor = node.parent_folder_id
        return _SEP.join(reversed(parts))

    def resolve_path(self, path: str) -> str:
        """Path string → folder id. Raises UserError if not found."""
        self._load()
        cleaned = path.strip(_SEP)
        if not cleaned:
            raise UserError("folder path is empty")
        fid = self._by_path.get(cleaned)
        if fid is None:
            similar = ", ".join(sorted(self._by_path.keys())[:5]) or "(no folders)"
            raise UserError(
                f"no folder with path {cleaned!r} in project",
                hint=f"known paths (truncated): {similar}",
            )
        return fid

    def resolve_id(self, fid: str) -> str:
        """Folder id → human path ('A/B/C')."""
        self._load()
        info = self._by_id.get(fid)
        if info is None:
            raise UserError(f"folder id {fid!r} not found in project")
        return self._build_path(fid)

    def ancestors(self, fid: str) -> list[FolderInfo]:
        """Root → target chain, inclusive. Useful for breadcrumbs."""
        self._load()
        chain: list[FolderInfo] = []
        cursor: str | None = fid
        seen: set[str] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            node = self._by_id.get(cursor)
            if node is None:
                break
            chain.append(node)
            cursor = node.parent_folder_id
        return list(reversed(chain))

    def all_folders(self) -> list[FolderInfo]:
        self._load()
        return list(self._by_id.values())

    def as_dicts(self) -> list[dict[str, Any]]:
        self._load()
        return [
            {
                "id": f.id,
                "name": f.name,
                "parentFolderId": f.parent_folder_id,
                "path": self._build_path(f.id),
            }
            for f in self._by_id.values()
        ]
