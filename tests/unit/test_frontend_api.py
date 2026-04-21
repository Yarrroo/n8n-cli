"""Frontend API wrappers — cookie extraction + move-to-root quirk."""

from __future__ import annotations

import httpx
import pytest

from n8n_cli.api.frontend import FrontendApi, iter_folder_tree
from n8n_cli.api.transport import Transport, _extract_cookie
from n8n_cli.config.instance import Instance


def _make_transport(handler: httpx.MockTransport) -> Transport:
    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(
        base_url="https://n8n.example.com",
        transport=handler,
        headers={"accept": "application/json"},
    )
    return t


def test_extract_cookie_single_header() -> None:
    h = "n8n-auth=abc123; Max-Age=604800; Path=/; HttpOnly"
    assert _extract_cookie(h, "n8n-auth") == "abc123"


def test_extract_cookie_missing_returns_none() -> None:
    assert _extract_cookie("other=x; Path=/", "n8n-auth") is None


def test_move_to_root_translates_none_to_empty_string() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"data": {"id": "w1", "parentFolder": None}})

    t = _make_transport(httpx.MockTransport(handler))
    FrontendApi(t).move_workflow("w1", parent_folder_id=None)
    import json

    assert json.loads(captured["body"])["parentFolderId"] == ""


def test_move_to_folder_uses_real_id() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"data": {"id": "w1"}})

    t = _make_transport(httpx.MockTransport(handler))
    FrontendApi(t).move_workflow("w1", parent_folder_id="f42")
    import json

    assert json.loads(captured["body"])["parentFolderId"] == "f42"


def test_iter_folder_tree_yields_paths() -> None:
    trees = [
        {
            "id": "a",
            "name": "Ops",
            "children": [
                {
                    "id": "b",
                    "name": "Billing",
                    "children": [{"id": "c", "name": "Invoices", "children": []}],
                }
            ],
        }
    ]
    paths = {path: node["id"] for path, node in iter_folder_tree(trees)}
    assert paths == {"Ops": "a", "Ops/Billing": "b", "Ops/Billing/Invoices": "c"}


def test_login_fails_on_401() -> None:
    from n8n_cli.api.errors import AuthError

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "error", "message": "Unauthorized"})

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(AuthError):
        FrontendApi(t).login("x@y", "bad")


def test_login_stores_cookie_from_set_cookie_header() -> None:
    """Login path-sensitive handler: only the login endpoint returns a Set-Cookie."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/rest/login"):
            return httpx.Response(
                200,
                headers={"set-cookie": "n8n-auth=JWT123; Path=/; HttpOnly; Secure"},
                json={"data": {"id": "u1", "email": "x@y", "role": "global:owner"}},
            )
        # The follow-up personal-project lookup: no cookie, just data.
        return httpx.Response(200, json={"data": {"id": "proj-1"}})

    t = _make_transport(httpx.MockTransport(handler))
    user = FrontendApi(t).login("x@y", "ok")
    assert user["id"] == "u1"
    # Cookie is now on the transport client — exactly one, no conflicts.
    cookies = [c for c in t._client.cookies.jar if c.name == "n8n-auth"]
    assert len(cookies) == 1
    assert cookies[0].value == "JWT123"
