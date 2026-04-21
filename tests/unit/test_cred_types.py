"""Node-type to credential-type mapping."""

from __future__ import annotations

from n8n_cli.core.cred_types import (
    credential_types_for_node_name,
    credential_types_for_node_type,
)


def test_exact_type_mapping() -> None:
    creds = credential_types_for_node_type("n8n-nodes-base.httpRequest")
    assert "httpHeaderAuth" in creds
    assert "oAuth2Api" in creds


def test_display_name_to_type() -> None:
    assert credential_types_for_node_name("HTTP Request")
    assert "googleApi" in credential_types_for_node_name("GoogleSheets")


def test_unknown_returns_empty() -> None:
    assert credential_types_for_node_type("n8n-nodes-base.totallyMadeUp") == ()
    assert credential_types_for_node_name("NotARealNode") == ()


def test_trigger_only_nodes_have_no_creds() -> None:
    assert credential_types_for_node_type("n8n-nodes-base.manualTrigger") == ()
    assert credential_types_for_node_type("n8n-nodes-base.set") == ()
