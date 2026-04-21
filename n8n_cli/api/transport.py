"""HTTP transport layer.

One `Transport` per CLI invocation. Owns:
  - httpx.Client lifecycle (context manager)
  - automatic backend selection: `/api/v1/*` (public, API-key) vs `/rest/*`
    (frontend, session cookie) based on the path prefix
  - cursor pagination
  - error mapping to our exit-code hierarchy
  - `--verbose` request logging to stderr

Commands never import `httpx` directly — they go through `PublicApi` /
`FrontendApi`, which in turn go through `Transport`.
"""

from __future__ import annotations

import json as _json
import time
from collections.abc import Iterator
from typing import Any

import httpx
from rich.console import Console

from n8n_cli.api.errors import ApiError, AuthError, CapabilityError
from n8n_cli.config.instance import Instance

_PUBLIC_PREFIX = "/api/v1"
_FRONTEND_PREFIX = "/rest"


def _backend_for(path: str) -> str:
    if path.startswith(_PUBLIC_PREFIX):
        return "public"
    if path.startswith(_FRONTEND_PREFIX):
        return "frontend"
    # Allow bare paths like "/workflows" — default to public, the most common case.
    return "public"


def _normalize(path: str) -> str:
    if path.startswith(_PUBLIC_PREFIX) or path.startswith(_FRONTEND_PREFIX):
        return path
    # Bare `/workflows` → `/api/v1/workflows`.
    return _PUBLIC_PREFIX + path if path.startswith("/") else f"{_PUBLIC_PREFIX}/{path}"


class Transport:
    def __init__(
        self,
        instance: Instance,
        *,
        instance_name: str | None = None,
        verbose: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.instance = instance
        self.instance_name = instance_name
        self.verbose = verbose
        self._err = Console(stderr=True)
        self._client = httpx.Client(
            base_url=str(instance.url).rstrip("/"),
            timeout=timeout,
            headers={"accept": "application/json"},
            follow_redirects=True,
        )
        # Load a cached session cookie up front so frontend requests don't
        # need an extra round-trip. If missing, _auth_cookies falls through.
        self._session_loaded = False
        self._load_session_into_client()

    # --- context manager so callers can `with Transport(...) as t:` ---

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    # --- public HTTP methods ---

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=self._clean_params(params))

    def post(self, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json, params=self._clean_params(params or {}))

    def put(self, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json=json, params=self._clean_params(params or {}))

    def patch(self, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, json=json, params=self._clean_params(params or {}))

    def delete(self, path: str, **params: Any) -> Any:
        return self._request("DELETE", path, params=self._clean_params(params))

    def paginate(self, path: str, **params: Any) -> Iterator[dict[str, Any]]:
        """Yield items across cursor pages until `nextCursor` is null/absent."""
        cursor: str | None = None
        while True:
            call_params = dict(self._clean_params(params))
            if cursor is not None:
                call_params["cursor"] = cursor
            body = self._request("GET", path, params=call_params)
            yield from body.get("data", []) or []
            cursor = body.get("nextCursor")
            if not cursor:
                return

    # --- internals ---

    def _clean_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Drop keys with None values; coerce bools to lowercase strings."""
        clean: dict[str, Any] = {}
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, bool):
                clean[k] = "true" if v else "false"
            else:
                clean[k] = v
        return clean

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        _retry: bool = True,
    ) -> Any:
        backend = _backend_for(path)
        url = _normalize(path)
        headers = self._auth_headers(backend)

        started = time.monotonic()
        try:
            resp = self._client.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            self._log(method, url, backend, None, time.monotonic() - started)
            raise ApiError(
                f"network error contacting n8n: {exc!s}",
                backend=backend,
                hint="check N8N_URL and connectivity.",
            ) from exc

        duration = time.monotonic() - started
        self._log(method, url, backend, resp.status_code, duration)

        # Auto-relogin path for frontend 401 when credentials are available.
        if (
            resp.status_code == 401
            and backend == "frontend"
            and _retry
            and self._try_frontend_relogin()
        ):
            return self._request(method, path, params=params, json=json, _retry=False)

        return self._unwrap(resp, backend=backend)

    def _try_frontend_relogin(self) -> bool:
        """Attempt POST /rest/login with $N8N_EMAIL/$N8N_PASSWORD. Returns success."""
        import os

        from n8n_cli.config import sessions

        email = os.environ.get("N8N_EMAIL") or self.instance.email
        password = os.environ.get("N8N_PASSWORD")
        if not (email and password):
            return False
        try:
            resp = self._client.post(
                "/rest/login",
                json={"emailOrLdapLoginId": email, "password": password},
                headers={"content-type": "application/json", "accept": "application/json"},
            )
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        # Install new cookie + persist session.
        cookie_header = resp.headers.get("set-cookie") or ""
        raw = _extract_cookie(cookie_header, "n8n-auth")
        if not raw:
            return False
        self.refresh_session_cookie(f"n8n-auth={raw}")
        if self.instance_name:
            try:
                body = resp.json()
            except _json.JSONDecodeError:
                body = {}
            user = body.get("data", {}) if isinstance(body, dict) else {}
            sessions.save(
                self.instance_name,
                sessions.Session(
                    cookie=f"n8n-auth={raw}",
                    user_id=user.get("id"),
                ),
            )
        if self.verbose:
            self._err.print("[dim]→ POST /rest/login (frontend, 200) [re-auth][/dim]")
        return True

    def _auth_headers(self, backend: str) -> dict[str, str]:
        if backend == "public":
            key = self.instance.api_key
            if key is None:
                raise AuthError(
                    f"instance '{self.instance.url}' has no API key configured",
                    hint="add one with `n8n-cli instance patch <name> --api-key ...`.",
                )
            return {"X-N8N-API-KEY": key.get_secret_value()}
        return {}

    def _auth_cookies(self, backend: str) -> dict[str, str]:
        # Actual cookie is already on `self._client.cookies` (loaded in __init__
        # via `_load_session_into_client`). We return an empty dict here so the
        # caller's per-request override path is a no-op.
        return {}

    def _load_session_into_client(self) -> None:
        """Install cached n8n-auth cookie from sessions/<instance>.session."""
        from n8n_cli.config import sessions

        if self.instance_name is None:
            return
        sess = sessions.load(self.instance_name)
        if sess is None:
            return
        # session.cookie is stored as "n8n-auth=<jwt>" — parse into name/value.
        if "=" in sess.cookie:
            name, value = sess.cookie.split("=", 1)
            self._client.cookies.set(name.strip(), value.strip())
            self._session_loaded = True

    def refresh_session_cookie(self, raw_cookie: str) -> None:
        """Install a freshly-acquired cookie (after login/relogin).

        Clears every existing cookie with the same name first — httpx keeps
        cookies indexed by (name, domain, path) and raises CookieConflict
        when more than one matches a plain `.get(name)`. The server's
        Set-Cookie from the login POST may already have populated one.
        """
        if "=" not in raw_cookie:
            return
        name, value = raw_cookie.split("=", 1)
        name = name.strip()
        value = value.strip()
        jar = self._client.cookies.jar
        # The underlying cookielib jar supports in-place removal while we
        # re-iterate via a snapshot list.
        for cookie in [c for c in jar if c.name == name]:
            jar.clear(cookie.domain, cookie.path, cookie.name)
        self._client.cookies.set(name, value)
        self._session_loaded = True

    def _unwrap(self, resp: httpx.Response, *, backend: str) -> Any:
        if resp.is_success:
            if not resp.content:
                return {}
            try:
                return resp.json()
            except _json.JSONDecodeError as exc:
                raise ApiError(
                    "n8n returned non-JSON response",
                    status_code=resp.status_code,
                    backend=backend,
                ) from exc

        body_msg = _extract_error_message(resp)
        if resp.status_code == 401:
            hint = (
                "public API: check instance API key (may be expired)."
                if backend == "public"
                else "frontend API: session missing or expired — run `n8n-cli auth login` (Phase 4)."
            )
            raise AuthError(f"unauthorized ({resp.status_code}): {body_msg}", hint=hint)
        if resp.status_code == 403 and "license" in body_msg.lower():
            raise CapabilityError(
                f"feature not licensed on this instance: {body_msg}",
                hint="this operation requires an n8n license tier not active here.",
            )
        raise ApiError(
            f"{backend} API {resp.status_code}: {body_msg}",
            status_code=resp.status_code,
            backend=backend,
        )

    def _log(self, method: str, url: str, backend: str, status: int | None, seconds: float) -> None:
        if not self.verbose:
            return
        code = status if status is not None else "ERR"
        self._err.print(
            f"[dim]→[/dim] {method} {url} [cyan]({backend}, {code}, {seconds * 1000:.0f}ms)[/cyan]"
        )


def _extract_cookie(set_cookie_header: str, name: str) -> str | None:
    """Pull the value of `name` from a potentially multi-cookie Set-Cookie string."""
    for chunk in set_cookie_header.split(","):
        for part in chunk.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part.split("=", 1)[1]
    return None


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except _json.JSONDecodeError:
        text = resp.text.strip()
        return text[:200] if text else f"HTTP {resp.status_code}"
    if isinstance(data, dict):
        for key in ("message", "hint", "error"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return resp.text[:200] or f"HTTP {resp.status_code}"
