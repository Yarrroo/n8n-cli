"""Instance model — a named n8n deployment."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr


class Instance(BaseModel):
    """One named n8n deployment (prod, staging, local, ...).

    `api_key` is the JWT for the public REST API (/api/v1).
    `email` is used for frontend session login (/rest/login); the password is
    never stored here — it's prompted or read from env at login time.
    """

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    api_key: SecretStr | None = None
    email: str | None = None
    api_key_expires: str | None = Field(
        default=None,
        description="Optional ISO date string, informational only.",
    )

    def dump_public(self) -> dict[str, object]:
        """Serialize without secret values (for `instance list/get` output)."""
        return {
            "url": str(self.url),
            "has_api_key": self.api_key is not None,
            "email": self.email,
            "api_key_expires": self.api_key_expires,
        }
