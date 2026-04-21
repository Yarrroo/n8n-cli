"""JSON stdout emitter with secret redaction.

The CLI is AI-first: the default output is JSON on stdout, with a stable
schema per command. `--human` delegates to a caller-supplied formatter
(typically a Rich table) for interactive use.

Secret redaction is applied defensively to every response coming back from
n8n — even if a newer API version starts returning credential `data` we
won't accidentally leak it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, Final

from pydantic import BaseModel
from rich.console import Console

# Keys whose values are always redacted before printing. Case-insensitive.
# Matches either an exact key name OR a key where the lowercase form contains
# one of these tokens (so `apiKey`, `api_key`, `API-Key` all hit).
_REDACT_EXACT: Final[frozenset[str]] = frozenset(
    {
        "data",  # credential payload
        "password",
        "authorization",
    }
)
_REDACT_CONTAINS: Final[tuple[str, ...]] = (
    "apikey",
    "api_key",
    "secret",
    "token",
)
_REDACTED: Final[str] = "<redacted>"


def _should_redact(key: str, value: Any, *, parent_type: str | None) -> bool:
    low = key.lower().replace("-", "").replace("_", "")
    # Metadata/booleans naming a secret are not secrets themselves.
    # `has_api_key`, `hasToken`, `tokenExpiresAt`, `apiKeyExpires`.
    if low.startswith("has") or low.endswith("expires") or low.endswith("expiresat"):
        return False
    if isinstance(value, bool):
        return False
    if low in _REDACT_EXACT:
        # `data` is only a secret inside a credential; elsewhere it's legitimate
        # (e.g. `{"data": [...]}` wrappers from list endpoints).
        return not (key.lower() == "data" and parent_type != "credential")
    return any(token in low for token in _REDACT_CONTAINS)


def redact(obj: Any, *, parent_type: str | None = None) -> Any:
    """Return a deep copy with secret-looking fields replaced by `<redacted>`.

    `parent_type` is an optional hint (e.g. `"credential"`) that scopes the
    otherwise ambiguous `data` key.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        # Detect credential-shaped objects so we scope `data` redaction.
        this_type = parent_type
        if "type" in obj and "name" in obj and ("data" in obj or "isResolvable" in obj):
            this_type = "credential"
        for k, v in obj.items():
            if isinstance(k, str) and _should_redact(k, v, parent_type=this_type):
                out[k] = _REDACTED
            else:
                out[k] = redact(v, parent_type=this_type)
        return out
    if isinstance(obj, list):
        return [redact(x, parent_type=parent_type) for x in obj]
    return obj


def _to_jsonable(obj: Any) -> Any:
    """Normalize pydantic models / datetimes / URLs into JSON-safe values."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True, exclude_none=False)
    return obj


def emit(
    data: Any,
    *,
    human: bool = False,
    human_formatter: Callable[[Any], None] | None = None,
) -> None:
    """Print `data` to stdout — JSON by default, human-rendered when asked.

    `human_formatter` receives the redacted, already-jsonable data and is
    responsible for writing to stdout itself (typically via `rich.print` or a
    Table render).
    """
    payload = _to_jsonable(data)
    payload = redact(payload)

    if human and human_formatter is not None:
        human_formatter(payload)
        return

    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write(text + "\n")


def emit_error(message: str, *, hint: str | None = None) -> None:
    """Pretty error line on stderr. `CliError` handling in main.run() uses this."""
    err = Console(stderr=True)
    err.print(f"[red]error:[/red] {message}")
    if hint:
        err.print(f"[dim]hint:[/dim] {hint}")
