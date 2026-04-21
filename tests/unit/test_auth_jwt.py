"""JWT `exp` decoding for `auth status`."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

from n8n_cli.commands.auth import _decode_jwt_exp


def _make_jwt(claims: dict) -> str:
    def _b64(data: dict | str) -> str:
        raw = json.dumps(data).encode() if isinstance(data, dict) else data.encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_b64({'alg': 'HS256'})}.{_b64(claims)}.{_b64('sig')}"


def test_decodes_future_exp() -> None:
    future = datetime.now(tz=UTC) + timedelta(days=30)
    token = _make_jwt({"exp": int(future.timestamp())})
    out = _decode_jwt_exp(token)
    assert out is not None
    # Drop sub-second precision (fromtimestamp truncates to int seconds).
    assert abs((out - future).total_seconds()) < 1.5


def test_missing_exp_returns_none() -> None:
    token = _make_jwt({"sub": "abc"})
    assert _decode_jwt_exp(token) is None


def test_malformed_token_returns_none() -> None:
    assert _decode_jwt_exp("not.a.valid") is None
    assert _decode_jwt_exp("one-part-only") is None
    assert _decode_jwt_exp("") is None
