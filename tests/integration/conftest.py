"""Integration test fixtures: VCR recorder scrubbed of API keys.

Cassettes live under `tests/integration/cassettes/`. Recording mode is
controlled via `VCR_RECORD` env var:
    VCR_RECORD=new_episodes  → record any new interactions (default)
    VCR_RECORD=none          → replay only (fail if cassette missing) — CI
    VCR_RECORD=all           → re-record everything (live)

The cassettes committed to the repo are already scrubbed — the API key never
touches disk in a readable form.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import vcr  # type: ignore[import-untyped]

from n8n_cli.api.transport import Transport
from n8n_cli.config.instance import Instance

_TEST_URL = os.environ.get("N8N_URL", "https://n8n.example.com")
_API_KEY = os.environ.get("N8N_API_KEY", "PLACEHOLDER_KEY")
_CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _scrub_request(request: vcr.request.Request) -> vcr.request.Request:
    if "X-N8N-API-KEY" in request.headers:
        request.headers["X-N8N-API-KEY"] = "SCRUBBED"
    if "x-n8n-api-key" in request.headers:
        request.headers["x-n8n-api-key"] = "SCRUBBED"
    return request


vcr_instance = vcr.VCR(
    cassette_library_dir=str(_CASSETTE_DIR),
    record_mode=os.environ.get("VCR_RECORD", "new_episodes"),
    match_on=("method", "scheme", "host", "port", "path", "query"),
    filter_headers=[("X-N8N-API-KEY", "SCRUBBED"), ("authorization", "SCRUBBED")],
    before_record_request=_scrub_request,
)


@pytest.fixture
def live_instance() -> Instance:
    """Instance pointing at the configured test URL with whatever API key is in $N8N_API_KEY.

    When replaying cassettes, the key just needs to be present (contents
    irrelevant since scrubbed). When recording, it needs to be real.
    """
    return Instance(url=_TEST_URL, api_key=_API_KEY)  # type: ignore[arg-type]


@pytest.fixture
def live_transport(live_instance: Instance) -> Iterator[Transport]:
    with Transport(live_instance) as t:
        yield t
