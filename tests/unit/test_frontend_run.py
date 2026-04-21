"""FrontendApi.run_workflow — body shape against n8n quirks."""

from __future__ import annotations

import json

import httpx

from n8n_cli.api.frontend import FrontendApi
from n8n_cli.api.transport import Transport
from n8n_cli.config.instance import Instance


def _make_transport(handler: httpx.MockTransport) -> Transport:
    inst = Instance(url="https://n8n.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst)
    t._client = httpx.Client(base_url="https://n8n.example.com", transport=handler)
    return t


def test_run_workflow_uses_trigger_to_start_from() -> None:
    """Regression: startNodes returns 500; triggerToStartFrom works."""
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"data": {"executionId": "42"}})

    t = _make_transport(httpx.MockTransport(handler))
    full = {
        "id": "wf1",
        "name": "X",
        "nodes": [
            {"name": "Start", "type": "n8n-nodes-base.manualTrigger"},
            {"name": "Set", "type": "n8n-nodes-base.set"},
        ],
        "connections": {},
        "settings": {},
    }
    result = FrontendApi(t).run_workflow("wf1", full_workflow=full)
    assert result["executionId"] == "42"
    assert captured["path"] == "/rest/workflows/wf1/run"
    body = captured["body"]
    assert body["triggerToStartFrom"]["name"] == "Start"
    assert "startNodes" not in body  # must not be set — breaks n8n
    # Workflow payload is stripped to the writable slice.
    assert set(body["workflowData"].keys()) >= {
        "id",
        "name",
        "nodes",
        "connections",
        "settings",
        "pinData",
        "active",
    }


def test_run_workflow_explicit_trigger_override() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"data": {"executionId": "99"}})

    t = _make_transport(httpx.MockTransport(handler))
    full = {
        "id": "wf",
        "name": "X",
        "nodes": [
            {"name": "WebhookOne", "type": "n8n-nodes-base.webhook"},
            {"name": "WebhookTwo", "type": "n8n-nodes-base.webhook"},
        ],
        "connections": {},
        "settings": {},
    }
    FrontendApi(t).run_workflow("wf", full_workflow=full, trigger_name="WebhookTwo")
    assert captured["body"]["triggerToStartFrom"]["name"] == "WebhookTwo"
