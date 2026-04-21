"""Redactor contract: secrets out, legit fields in."""

from __future__ import annotations

from n8n_cli.output.jsonout import redact


def test_redacts_credential_data_by_scope() -> None:
    # Shaped like a credential — `data` is redacted.
    cred = {"id": "c1", "name": "GH", "type": "githubApi", "data": {"token": "SECRET"}}
    out = redact(cred)
    assert out["data"] == "<redacted>"


def test_leaves_unrelated_data_field_alone() -> None:
    # Shaped like a list response — `data` is legitimate payload.
    resp = {"data": [{"id": "wf1"}], "nextCursor": None}
    out = redact(resp)
    assert out["data"] == [{"id": "wf1"}]


def test_redacts_common_secret_keys() -> None:
    obj = {
        "apiKey": "s1",
        "API_KEY": "s2",
        "accessToken": "s3",
        "clientSecret": "s4",
        "Authorization": "Bearer xyz",
        "password": "p",
        "name": "keep me",
    }
    out = redact(obj)
    for k in ("apiKey", "API_KEY", "accessToken", "clientSecret", "Authorization", "password"):
        assert out[k] == "<redacted>", f"{k} should be redacted"
    assert out["name"] == "keep me"


def test_redacts_deeply_nested() -> None:
    obj = {"level1": {"level2": [{"token": "x"}, {"safe": 1}]}}
    out = redact(obj)
    assert out["level1"]["level2"][0]["token"] == "<redacted>"
    assert out["level1"]["level2"][1]["safe"] == 1


def test_preserves_non_dict_values() -> None:
    assert redact([1, 2, 3]) == [1, 2, 3]
    assert redact("plain") == "plain"
    assert redact(None) is None


def test_does_not_redact_metadata_booleans() -> None:
    # `has_api_key: true` is metadata, not a secret — must stay.
    obj = {"has_api_key": True, "hasToken": False, "api_key_expires": "2026-05-20"}
    out = redact(obj)
    assert out == {"has_api_key": True, "hasToken": False, "api_key_expires": "2026-05-20"}
