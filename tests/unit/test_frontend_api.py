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


# --- MFA login --------------------------------------------------------


def test_login_raises_mfa_required_on_code_998() -> None:
    """n8n returns 401 + {'code': 998, 'message': 'MFA Error'} when the
    account has 2FA enabled and the request omits mfaCode/mfaRecoveryCode.
    The CLI must surface this as MfaRequiredError, not generic AuthError,
    so the command layer can prompt for a code.
    """
    from n8n_cli.api.errors import MfaRequiredError

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 998, "message": "MFA Error"})

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(MfaRequiredError):
        FrontendApi(t).login("x@y", "ok")


def test_login_with_mfa_code_sends_field_and_succeeds() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/rest/login"):
            import json

            captured["body"] = json.loads(req.content.decode())
            return httpx.Response(
                200,
                headers={"set-cookie": "n8n-auth=JWT; Path=/; HttpOnly"},
                json={"data": {"id": "u1", "email": "x@y", "role": "global:owner"}},
            )
        return httpx.Response(200, json={"data": {"id": "proj-1"}})

    t = _make_transport(httpx.MockTransport(handler))
    FrontendApi(t).login("x@y", "ok", mfa_code="123456")
    assert captured["body"]["mfaCode"] == "123456"
    assert "mfaRecoveryCode" not in captured["body"]


def test_login_with_recovery_code_sends_field() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/rest/login"):
            import json

            captured["body"] = json.loads(req.content.decode())
            return httpx.Response(
                200,
                headers={"set-cookie": "n8n-auth=JWT; Path=/"},
                json={"data": {"id": "u1"}},
            )
        return httpx.Response(200, json={"data": {"id": "p"}})

    t = _make_transport(httpx.MockTransport(handler))
    FrontendApi(t).login("x@y", "ok", mfa_recovery_code="recovery-abc")
    assert captured["body"]["mfaRecoveryCode"] == "recovery-abc"
    assert "mfaCode" not in captured["body"]


def test_login_with_bad_mfa_code_raises_authn_not_mfa_required() -> None:
    """When a code WAS sent and n8n returns 401, the message should reflect
    invalid-code, not MFA-required, so we don't loop the prompt."""
    from n8n_cli.api.errors import AuthError, MfaRequiredError

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"status": "error", "message": "Invalid mfa token or recovery code"}
        )

    t = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(AuthError) as exc_info:
        FrontendApi(t).login("x@y", "ok", mfa_code="000000")
    # Bad-code error must NOT be classified as MFA-required (no re-prompt loop)
    assert not isinstance(exc_info.value, MfaRequiredError)


# --- archive / unarchive (dedicated frontend endpoints) --------------


def test_archive_workflow_posts_to_archive_endpoint() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        return httpx.Response(200, json={"data": {"id": "w1", "isArchived": True}})

    t = _make_transport(httpx.MockTransport(handler))
    result = FrontendApi(t).archive_workflow("w1")
    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/workflows/w1/archive"
    assert result["isArchived"] is True


def test_unarchive_workflow_posts_to_unarchive_endpoint() -> None:
    """Critical: the PUT-based flow returns 400 on archived workflows.
    Only the dedicated POST endpoint can flip isArchived back to false."""
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        return httpx.Response(200, json={"data": {"id": "w1", "isArchived": False}})

    t = _make_transport(httpx.MockTransport(handler))
    result = FrontendApi(t).unarchive_workflow("w1")
    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/workflows/w1/unarchive"
    assert result["isArchived"] is False
