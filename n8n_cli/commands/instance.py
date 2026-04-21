"""`n8n-cli instance *` — manage named n8n deployments.

An instance is a named pair (url, auth). Every command that talks to n8n
resolves its target via `--instance <name>`, falling back to
`current_instance` from config.
"""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from n8n_cli.api.errors import UserError
from n8n_cli.config import store
from n8n_cli.config.instance import Instance
from n8n_cli.output.jsonout import emit

app = typer.Typer(
    help="Manage named n8n instances (prod, staging, local, ...).",
    no_args_is_help=True,
)


NameArg = Annotated[str, typer.Argument(help="Instance name (local identifier).")]


def _read_api_key(flag_value: str | None) -> str | None:
    """Resolve API key from flag → stdin → N8N_API_KEY env → None."""
    if flag_value is not None:
        return flag_value
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            return piped
    return os.environ.get("N8N_API_KEY")


@app.command("add")
def add(
    name: NameArg,
    url: Annotated[str, typer.Option("--url", help="Base URL of the n8n instance.")],
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="Public-API JWT. If omitted, read from stdin or $N8N_API_KEY.",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option("--email", help="Login email (for frontend session auth, Phase 4)."),
    ] = None,
    use: Annotated[
        bool,
        typer.Option("--use/--no-use", help="Also set this as the current instance."),
    ] = False,
) -> None:
    """Register a new instance. Fails if one by that name already exists — use `patch`."""
    cfg = store.load()
    if name in cfg.instances:
        raise UserError(
            f"instance '{name}' already exists",
            hint="update it with `n8n-cli instance patch` or pick another name.",
        )
    key = _read_api_key(api_key)
    inst = Instance(url=url, api_key=key, email=email)  # type: ignore[arg-type]
    cfg.instances[name] = inst
    if use or cfg.current_instance is None:
        cfg.current_instance = name
    store.save(cfg)
    emit({"added": name, "is_active": cfg.current_instance == name, **inst.dump_public()})


@app.command("list")
def list_() -> None:
    """List all configured instances (secrets redacted)."""
    cfg = store.load()
    rows = []
    for nm, inst in sorted(cfg.instances.items()):
        rows.append({"name": nm, "is_active": cfg.current_instance == nm, **inst.dump_public()})
    emit(rows)


@app.command("get")
def get(name: NameArg) -> None:
    """Show one instance's public metadata."""
    cfg = store.load()
    inst = store.get_instance(name, cfg)
    emit({"name": name, "is_active": cfg.current_instance == name, **inst.dump_public()})


@app.command("patch")
def patch(
    name: NameArg,
    url: Annotated[str | None, typer.Option("--url")] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="New API key; pass `-` to read from stdin.",
        ),
    ] = None,
    email: Annotated[str | None, typer.Option("--email")] = None,
) -> None:
    """Update one or more fields on an existing instance."""
    cfg = store.load()
    inst = store.get_instance(name, cfg)
    if url is not None:
        inst = inst.model_copy(update={"url": url})
    if email is not None:
        inst = inst.model_copy(update={"email": email})
    if api_key is not None:
        resolved = _read_api_key(None) if api_key == "-" else api_key
        inst = inst.model_copy(update={"api_key": resolved})
    cfg.instances[name] = inst
    store.save(cfg)
    emit({"updated": name, **inst.dump_public()})


@app.command("delete")
def delete(
    name: NameArg,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
) -> None:
    """Remove an instance from config."""
    cfg = store.load()
    store.get_instance(name, cfg)  # existence check
    if not force:
        typer.confirm(f"Delete instance '{name}'?", abort=True)
    del cfg.instances[name]
    if cfg.current_instance == name:
        cfg.current_instance = None
    # Remove any cached session file for this instance, best-effort.
    session_file = store.sessions_dir() / f"{name}.session"
    if session_file.exists():
        session_file.unlink()
    store.save(cfg)
    emit({"deleted": name})


@app.command("use")
def use(name: NameArg) -> None:
    """Set the active instance used when --instance is omitted."""
    cfg = store.load()
    store.get_instance(name, cfg)  # existence check
    cfg.current_instance = name
    store.save(cfg)
    emit({"current_instance": name})


@app.command("current")
def current() -> None:
    """Print the active instance."""
    cfg = store.load()
    if cfg.current_instance is None:
        raise UserError(
            "no active instance set",
            hint="run `n8n-cli instance use <name>` to pick one.",
        )
    inst = store.get_instance(cfg.current_instance, cfg)
    emit({"name": cfg.current_instance, **inst.dump_public()})
