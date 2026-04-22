"""Tests for core.node_types — latest-version resolution."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from n8n_cli.api.frontend import latest_node_versions
from n8n_cli.core import node_types


def test_latest_node_versions_int_and_list_shapes() -> None:
    catalog = [
        {"name": "n8n-nodes-base.set", "version": [3, 3.1, 3.2, 3.3, 3.4]},
        {"name": "n8n-nodes-base.set", "version": [1, 2]},
        {"name": "n8n-nodes-base.httpRequest", "version": [3, 4, 4.1, 4.2, 4.3, 4.4]},
        {"name": "n8n-nodes-base.httpRequest", "version": 2},
        {"name": "n8n-nodes-base.manualTrigger", "version": 1},
        {"name": "n8n-nodes-base.garbage"},  # no version — ignored
        {"name": None, "version": 5},  # invalid name — ignored
    ]
    out = latest_node_versions(catalog)
    assert out["n8n-nodes-base.set"] == 3.4
    assert out["n8n-nodes-base.httpRequest"] == 4.4
    assert out["n8n-nodes-base.manualTrigger"] == 1.0
    assert "n8n-nodes-base.garbage" not in out
    assert None not in out


def test_resolve_latest_version_falls_back_to_builtin(tmp_path: Path, monkeypatch) -> None:
    # Wipe both process and disk caches for isolation.
    node_types._PROCESS_CACHE.clear()
    monkeypatch.setattr(node_types, "_cache_path", lambda _inst: tmp_path / "x.yaml")
    # httpRequest must default to the modern v4.x, not v1
    v = node_types.resolve_latest_version("n8n-nodes-base.httpRequest", fapi=None)
    assert v >= 4.0, f"builtin must point at modern httpRequest, got {v}"


def test_resolve_latest_version_hits_live_api_and_persists_cache(
    tmp_path: Path, monkeypatch
) -> None:
    node_types._PROCESS_CACHE.clear()
    cache_file = tmp_path / "node-types-ams.yaml"
    monkeypatch.setattr(node_types, "_cache_path", lambda _inst: cache_file)

    fapi = MagicMock()
    fapi.fetch_node_types_catalog.return_value = [
        {"name": "n8n-nodes-base.httpRequest", "version": [3, 4, 4.2]},
        {"name": "custom.myNode", "version": 2.5},
    ]
    v1 = node_types.resolve_latest_version("custom.myNode", fapi=fapi, instance_name="ams")
    assert v1 == 2.5
    fapi.fetch_node_types_catalog.assert_called_once()
    assert cache_file.exists(), "map should be persisted for next run"

    # Second call reuses the process cache — no second fetch.
    v2 = node_types.resolve_latest_version(
        "n8n-nodes-base.httpRequest", fapi=fapi, instance_name="ams"
    )
    assert v2 == 4.2
    fapi.fetch_node_types_catalog.assert_called_once()


def test_resolve_latest_version_uses_disk_cache_across_processes(
    tmp_path: Path, monkeypatch
) -> None:
    node_types._PROCESS_CACHE.clear()
    cache_file = tmp_path / "node-types-ams.yaml"
    monkeypatch.setattr(node_types, "_cache_path", lambda _inst: cache_file)
    # Pre-seed disk cache with a fresh timestamp.
    node_types.save_cached_map("ams", {"custom.fromDisk": 7.0})
    # Clear process cache to simulate a new process.
    node_types._PROCESS_CACHE.clear()

    # No fapi supplied — must still find the value from disk.
    v = node_types.resolve_latest_version("custom.fromDisk", instance_name="ams")
    assert v == 7.0


def test_resolve_latest_version_ignores_stale_cache(tmp_path: Path, monkeypatch) -> None:
    node_types._PROCESS_CACHE.clear()
    cache_file = tmp_path / "node-types-ams.yaml"
    monkeypatch.setattr(node_types, "_cache_path", lambda _inst: cache_file)
    import yaml as _yaml

    cache_file.write_text(
        _yaml.safe_dump(
            {"_cached_at": time.time() - (node_types._CACHE_TTL_SECONDS + 60), "map": {"x": 9}}
        )
    )
    assert node_types.load_cached_map("ams") is None


def test_fetch_node_types_catalog_propagates_http_errors() -> None:
    import httpx

    from n8n_cli.api.errors import ApiError
    from n8n_cli.api.frontend import FrontendApi
    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    t._client = httpx.Client(
        base_url="https://n8n.example.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ApiError):
        FrontendApi(t).fetch_node_types_catalog()


def test_trigger_node_types_from_catalog() -> None:
    from n8n_cli.api.frontend import trigger_node_types

    catalog = [
        {"name": "n8n-nodes-base.webhook", "group": ["trigger"]},
        {"name": "n8n-nodes-base.scheduleTrigger", "group": ["trigger", "schedule"]},
        {"name": "n8n-nodes-base.httpRequest", "group": ["output"]},
        {"name": "n8n-nodes-base.set", "group": ["input"]},
        {"name": "n8n-nodes-base.customTrigger", "group": ["trigger"]},
        {"name": "no-group-node"},  # missing group — not a trigger
        {"group": ["trigger"]},  # missing name — ignored
    ]
    out = trigger_node_types(catalog)
    assert "n8n-nodes-base.webhook" in out
    assert "n8n-nodes-base.scheduleTrigger" in out
    assert "n8n-nodes-base.customTrigger" in out
    assert "n8n-nodes-base.httpRequest" not in out
    assert "n8n-nodes-base.set" not in out
    assert "no-group-node" not in out


def test_is_trigger_type_falls_back_to_builtins() -> None:
    node_types._TRIGGERS_PROCESS_CACHE.clear()
    # webhook is in BUILTIN_TRIGGERS — must classify even without fapi
    assert node_types.is_trigger_type("n8n-nodes-base.webhook") is True
    assert node_types.is_trigger_type("n8n-nodes-base.manualTrigger") is True
    assert node_types.is_trigger_type("n8n-nodes-base.httpRequest") is False


def test_is_trigger_type_hits_live_catalog_and_caches() -> None:
    node_types._TRIGGERS_PROCESS_CACHE.clear()
    fapi = MagicMock()
    fapi.fetch_node_types_catalog.return_value = [
        {"name": "custom.slackTrigger", "group": ["trigger"]},
        {"name": "custom.notATrigger", "group": ["output"]},
    ]
    assert node_types.is_trigger_type("custom.slackTrigger", fapi=fapi, instance_name="x") is True
    # Second call — cached, no re-fetch.
    assert node_types.is_trigger_type("custom.notATrigger", fapi=fapi, instance_name="x") is False
    fapi.fetch_node_types_catalog.assert_called_once()


def test_classify_workflow_triggers_extracts_triggers_only() -> None:
    node_types._TRIGGERS_PROCESS_CACHE.clear()
    wf = {
        "nodes": [
            {"name": "A", "type": "n8n-nodes-base.webhook", "typeVersion": 2},
            {"name": "B", "type": "n8n-nodes-base.scheduleTrigger"},
            {"name": "C", "type": "n8n-nodes-base.httpRequest"},
            {"name": "D", "type": "n8n-nodes-base.webhook", "disabled": True},
        ]
    }
    rows = node_types.classify_workflow_triggers(wf)
    names = [r["name"] for r in rows]
    assert names == ["A", "B", "D"]
    assert rows[-1]["disabled"] is True


def test_run_workflow_raises_on_multiple_active_triggers() -> None:
    import httpx

    from n8n_cli.api.errors import ApiError
    from n8n_cli.api.frontend import FrontendApi
    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    node_types._TRIGGERS_PROCESS_CACHE.clear()

    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(
        base_url="https://n8n.example.com",
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
    )
    full = {
        "id": "wf",
        "name": "X",
        "nodes": [
            {"name": "Webhook A", "type": "n8n-nodes-base.webhook"},
            {"name": "Webhook B", "type": "n8n-nodes-base.webhook"},
        ],
        "connections": {},
        "settings": {},
    }
    with pytest.raises(ApiError) as excinfo:
        FrontendApi(t).run_workflow("wf", full_workflow=full)
    msg = str(excinfo.value.message)
    assert "2 active triggers" in msg
    assert "Webhook A" in msg and "Webhook B" in msg


def test_run_workflow_skips_disabled_triggers_automatically() -> None:
    import httpx

    from n8n_cli.api.frontend import FrontendApi
    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    node_types._TRIGGERS_PROCESS_CACHE.clear()
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json as _j

        captured["body"] = _j.loads(req.content.decode())
        return httpx.Response(200, json={"data": {"executionId": "1"}})

    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(
        base_url="https://n8n.example.com", transport=httpx.MockTransport(handler)
    )
    full = {
        "id": "wf",
        "name": "X",
        "nodes": [
            {"name": "Disabled Webhook", "type": "n8n-nodes-base.webhook", "disabled": True},
            {"name": "Active Webhook", "type": "n8n-nodes-base.webhook"},
        ],
        "connections": {},
        "settings": {},
    }
    FrontendApi(t).run_workflow("wf", full_workflow=full)
    assert captured["body"]["triggerToStartFrom"]["name"] == "Active Webhook"


def test_run_workflow_errors_when_all_triggers_disabled() -> None:
    import httpx

    from n8n_cli.api.errors import ApiError
    from n8n_cli.api.frontend import FrontendApi
    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    node_types._TRIGGERS_PROCESS_CACHE.clear()
    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(
        base_url="https://n8n.example.com",
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
    )
    full = {
        "id": "wf",
        "name": "X",
        "nodes": [
            {"name": "Webhook", "type": "n8n-nodes-base.webhook", "disabled": True},
        ],
        "connections": {},
        "settings": {},
    }
    with pytest.raises(ApiError) as excinfo:
        FrontendApi(t).run_workflow("wf", full_workflow=full)
    assert "disabled" in str(excinfo.value.message).lower()


def test_fetch_node_types_catalog_success() -> None:
    import httpx

    from n8n_cli.api.frontend import FrontendApi
    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"name": "n8n-nodes-base.httpRequest", "version": [3, 4, 4.2]},
                {"name": "n8n-nodes-base.webhook", "version": 2.1},
            ],
        )

    t._client = httpx.Client(
        base_url="https://n8n.example.com", transport=httpx.MockTransport(handler)
    )
    out = FrontendApi(t).fetch_node_types_catalog()
    assert len(out) == 2
    mapping = latest_node_versions(out)
    assert mapping["n8n-nodes-base.httpRequest"] == 4.2
    assert mapping["n8n-nodes-base.webhook"] == 2.1
