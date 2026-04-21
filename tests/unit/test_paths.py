"""Folder-path resolver: list_folders → {path ↔ id} bidirectional map."""

from __future__ import annotations

from typing import Any

import pytest

from n8n_cli.api.errors import UserError
from n8n_cli.core.paths import FolderPathResolver


class FakeFrontend:
    """Mock FrontendApi.list_folders for the resolver — just returns the fixture."""

    def __init__(self, folders: list[dict[str, Any]]) -> None:
        self._folders = folders

    def list_folders(self, project_id: str, *, take: int = 1000) -> list[dict[str, Any]]:
        return self._folders


def _fixture_nested() -> list[dict[str, Any]]:
    return [
        {"id": "a", "name": "Ops", "parentFolder": None},
        {"id": "b", "name": "Billing", "parentFolder": {"id": "a"}},
        {"id": "c", "name": "Invoices", "parentFolder": {"id": "b"}},
        {"id": "d", "name": "Support", "parentFolder": None},
    ]


def test_resolve_path_single_segment() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    assert r.resolve_path("Ops") == "a"
    assert r.resolve_path("Support") == "d"


def test_resolve_path_nested() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    assert r.resolve_path("Ops/Billing") == "b"
    assert r.resolve_path("Ops/Billing/Invoices") == "c"


def test_resolve_path_strips_leading_trailing_slashes() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    assert r.resolve_path("/Ops/Billing/") == "b"


def test_resolve_path_missing_raises_user_error() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    with pytest.raises(UserError):
        r.resolve_path("Does/Not/Exist")


def test_resolve_id_to_path() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    assert r.resolve_id("c") == "Ops/Billing/Invoices"
    assert r.resolve_id("a") == "Ops"


def test_ancestors_chain() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    chain = [a.name for a in r.ancestors("c")]
    assert chain == ["Ops", "Billing", "Invoices"]


def test_empty_project_means_no_paths() -> None:
    r = FolderPathResolver(FakeFrontend([]), "proj")  # type: ignore[arg-type]
    with pytest.raises(UserError):
        r.resolve_path("anything")


def test_as_dicts_includes_computed_path() -> None:
    r = FolderPathResolver(FakeFrontend(_fixture_nested()), "proj")  # type: ignore[arg-type]
    by_id = {row["id"]: row for row in r.as_dicts()}
    assert by_id["c"]["path"] == "Ops/Billing/Invoices"
    assert by_id["c"]["parentFolderId"] == "b"
    assert by_id["a"]["parentFolderId"] is None
