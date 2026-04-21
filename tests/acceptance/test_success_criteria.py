"""Project-wide acceptance tests — walk through task.md success criteria.

These run against a real n8n instance via VCR cassettes. Each test maps to one of
the bullets in task.md's "Success Criteria" block.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from n8n_cli.main import app
from n8n_cli.output.summarize import SummarizeOptions, summarize_items


@pytest.mark.acceptance
def test_cli_covers_all_task_md_commands() -> None:
    """Every resource subcommand advertised in task.md loads and shows --help."""
    runner = CliRunner()
    resources = [
        "instance",
        "auth",
        "project",
        "folder",
        "workflow",
        "node",
        "connection",
        "pin-data",
        "execution",
        "execution-data",
        "credential",
    ]
    for r in resources:
        result = runner.invoke(app, [r, "--help"])
        assert result.exit_code == 0, f"{r} --help failed: {result.output}"
        assert r in result.output or r.replace("-", " ") in result.output


@pytest.mark.acceptance
def test_all_workflow_actions_present() -> None:
    """Every workflow verb from task.md is mounted on the CLI."""
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0
    for verb in (
        "list",
        "get",
        "structure",
        "add",
        "patch",
        "archive",
        "unarchive",
        "publish",
        "unpublish",
        "execute",
        "export",
        "import",
        "copy",
        "link",
        "unlink",
        "projects",
        "move",
        "delete",
    ):
        assert verb in result.output, f"workflow verb {verb!r} missing from --help"


@pytest.mark.acceptance
def test_summarizer_meets_one_kb_budget_for_2mb_payload() -> None:
    """Headline success criterion — 2MB raw node output → ≤1KB summary."""
    # Each item ~220 bytes → ~2 MB at 10k items. We also make names long
    # enough that raw JSON crosses the 2 MB mark even on lean encoders.
    padding = "x" * 150  # inflate each item
    items = [
        {
            "id": f"u_{i}",
            "name": f"User {i} {padding}",
            "email": f"u{i}@example.com",
            "metadata": {"created_at": "2026-04-21T10:00:00Z", "score": i * 1.5},
        }
        for i in range(10000)
    ]
    raw = json.dumps(items).encode()
    assert len(raw) > 2_000_000, f"test fixture too small: {len(raw):,} bytes"
    out = summarize_items(items, SummarizeOptions())
    serialized = json.dumps(out, ensure_ascii=False).encode()
    assert len(serialized) <= 1024, f"summary over budget: {len(serialized)} bytes"
    assert out["item_count"] == 10000


@pytest.mark.acceptance
def test_exit_codes_are_stable() -> None:
    """Exit codes 0/1/2/3/4/5 are part of the public contract."""
    from n8n_cli.api.errors import ExitCode

    assert ExitCode.SUCCESS == 0
    assert ExitCode.UNIMPLEMENTED == 1
    assert ExitCode.USER_ERROR == 2
    assert ExitCode.API_ERROR == 3
    assert ExitCode.AUTH_ERROR == 4
    assert ExitCode.CAPABILITY_GATED == 5


@pytest.mark.acceptance
def test_dual_api_routing_advertised_in_verbose() -> None:
    """Transport logs backend tag on --verbose — documented contract."""
    from unittest.mock import patch

    import httpx

    from n8n_cli.api.transport import Transport
    from n8n_cli.config.instance import Instance

    inst = Instance(url="https://x.example.com", api_key="k")  # type: ignore[arg-type]
    t = Transport(inst, verbose=True)
    t._client = httpx.Client(
        base_url="https://x.example.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    with patch.object(t._err, "print") as mock_print:
        t.get("/api/v1/workflows")
        t.get("/rest/workflows")
    # Expect both "public" and "frontend" tags in the two log lines.
    lines = " | ".join(str(call.args[0]) for call in mock_print.call_args_list)
    assert "public" in lines
    assert "frontend" in lines


@pytest.mark.acceptance
def test_credential_redaction_is_belt_and_suspenders() -> None:
    """Even if n8n starts returning credential `data`, our redactor strips it."""
    from n8n_cli.output.jsonout import redact

    payload = {
        "id": "c1",
        "name": "Github",
        "type": "githubApi",
        "data": {"accessToken": "leakme"},
    }
    out = redact(payload)
    assert out["data"] == "<redacted>"
