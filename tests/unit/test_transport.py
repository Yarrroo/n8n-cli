"""Transport: param cleaning, auth headers, error mapping.

Uses httpx's MockTransport to avoid network calls entirely.
"""

from __future__ import annotations

import httpx
import pytest

from n8n_cli.api.errors import ApiError, AuthError, CapabilityError
from n8n_cli.api.transport import Transport, _backend_for, _normalize
from n8n_cli.config.instance import Instance


def _make_transport(handler: httpx.MockTransport) -> Transport:
    inst = Instance(url="https://n8n.example.com", api_key="testkey")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(
        base_url="https://n8n.example.com",
        transport=handler,
        headers={"accept": "application/json"},
    )
    return t


def test_backend_detection() -> None:
    assert _backend_for("/api/v1/workflows") == "public"
    assert _backend_for("/rest/workflows") == "frontend"
    assert _backend_for("/workflows") == "public"  # fallback


def test_path_normalization() -> None:
    assert _normalize("/workflows") == "/api/v1/workflows"
    assert _normalize("/api/v1/workflows") == "/api/v1/workflows"
    assert _normalize("/rest/login") == "/rest/login"


def test_get_passes_api_key_header() -> None:
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["key"] = req.headers.get("X-N8N-API-KEY", "")
        return httpx.Response(200, json={"data": []})

    t = _make_transport(httpx.MockTransport(handler))
    t.get("/api/v1/workflows")
    assert captured["key"] == "testkey"


def test_401_raises_auth_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(AuthError):
        t.get("/api/v1/workflows")


def test_403_license_gates_raise_capability_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "message": (
                    "Your license does not allow for feat:projectRole:admin. Upgrade to enable."
                )
            },
        )

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(CapabilityError):
        t.get("/api/v1/projects")


def test_500_raises_api_error_with_status() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "oops"})

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(ApiError) as excinfo:
        t.get("/api/v1/workflows")
    assert excinfo.value.status_code == 500
    assert excinfo.value.backend == "public"


def test_paginate_follows_cursor() -> None:
    pages = iter(
        [
            {"data": [{"id": "a"}, {"id": "b"}], "nextCursor": "p2"},
            {"data": [{"id": "c"}], "nextCursor": None},
        ]
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(pages))

    t = _make_transport(httpx.MockTransport(handler))
    items = list(t.paginate("/api/v1/workflows"))
    assert [i["id"] for i in items] == ["a", "b", "c"]


def test_clean_params_drops_none_and_coerces_bool() -> None:
    inst = Instance(url="https://x.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    out = t._clean_params({"active": True, "archived": False, "limit": 5, "tag": None})
    assert out == {"active": "true", "archived": "false", "limit": 5}


def test_missing_api_key_raises_auth_error() -> None:
    inst = Instance(url="https://x.example.com", api_key=None)
    t = Transport(inst)
    # No handler installed — call should short-circuit in _auth_headers.
    with pytest.raises(AuthError):
        t.get("/api/v1/workflows")
