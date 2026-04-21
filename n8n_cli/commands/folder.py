"""`n8n-cli folder *` — tree operations via frontend API."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from n8n_cli.api.errors import UserError
from n8n_cli.api.frontend import FrontendApi
from n8n_cli.api.transport import Transport
from n8n_cli.config import store
from n8n_cli.core.paths import FolderPathResolver
from n8n_cli.output.jsonout import emit

app = typer.Typer(help="Manage workflow folders (frontend API).", no_args_is_help=True)

InstanceOpt = Annotated[
    str | None, typer.Option("--instance", help="Instance name (defaults to current).")
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Log HTTP calls to stderr.")]
ProjectOpt = Annotated[
    str | None,
    typer.Option("--project", help="Project id (defaults to personal project)."),
]
IdOpt = Annotated[str | None, typer.Option("--id", help="Folder id (direct addressing).")]
PathOpt = Annotated[
    str | None, typer.Option("--path", help="Human-readable folder path, e.g. 'A/B/C'.")
]


def _context(
    instance_name: str | None, project: str | None, verbose: bool
) -> tuple[Transport, FrontendApi, str]:
    name, inst = store.resolve_active(instance_name)
    t = Transport(inst, instance_name=name, verbose=verbose)
    api = FrontendApi(t)
    pid = project or api.personal_project_id()
    return t, api, pid


def _resolve_folder_id(
    api: FrontendApi, project_id: str, *, id_: str | None, path: str | None
) -> str:
    if id_ is not None and path is not None:
        raise UserError("pass either --id or --path, not both")
    if id_ is not None:
        return id_
    if path is not None:
        return FolderPathResolver(api, project_id).resolve_path(path)
    raise UserError("folder identification required: use --id or --path")


@app.command("list")
def list_(
    project: ProjectOpt = None,
    parent_path: Annotated[
        str | None,
        typer.Option("--parent-path", help="Only show folders whose parent is this path."),
    ] = None,
    parent_id: Annotated[
        str | None, typer.Option("--parent-id", help="Only show folders under this parent id.")
    ] = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """List folders in a project (with path, id, parentFolderId, counts)."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        resolver = FolderPathResolver(api, pid)
        target_parent: str | None = None
        if parent_id is not None:
            target_parent = parent_id
        elif parent_path is not None:
            target_parent = resolver.resolve_path(parent_path)
        rows = resolver.as_dicts()
        if target_parent is not None or parent_id == "" or parent_path == "":
            rows = [r for r in rows if r["parentFolderId"] == target_parent]
        rows.sort(key=lambda r: r["path"])
        emit(rows)
    finally:
        t.__exit__(None, None, None)


@app.command("get")
def get(
    id_: IdOpt = None,
    path: PathOpt = None,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Show one folder by id or path."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        fid = _resolve_folder_id(api, pid, id_=id_, path=path)
        resolver = FolderPathResolver(api, pid)
        # Find the matching entry so callers get counts/tags.
        match: dict[str, Any] | None = None
        for f in resolver.as_dicts():
            if f["id"] == fid:
                match = f
                break
        if match is None:
            raise UserError(f"folder id {fid!r} not found in project")
        emit(match)
    finally:
        t.__exit__(None, None, None)


@app.command("tree")
def tree(
    id_: IdOpt = None,
    path: PathOpt = None,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Return the subtree rooted at this folder's top ancestor (n8n's /tree shape)."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        fid = _resolve_folder_id(api, pid, id_=id_, path=path)
        emit(api.get_folder_tree(pid, fid))
    finally:
        t.__exit__(None, None, None)


@app.command("content")
def content(
    id_: IdOpt = None,
    path: PathOpt = None,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Summary of folder content: counts of sub-folders and workflows."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        fid = _resolve_folder_id(api, pid, id_=id_, path=path)
        emit(api.get_folder_content(pid, fid))
    finally:
        t.__exit__(None, None, None)


@app.command("path")
def path_cmd(
    id_: Annotated[str, typer.Option("--id", help="Folder id.")],
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Resolve a folder id to its human-readable path."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        resolver = FolderPathResolver(api, pid)
        emit({"id": id_, "path": resolver.resolve_id(id_)})
    finally:
        t.__exit__(None, None, None)


@app.command("add")
def add(
    name: Annotated[str, typer.Option("--name", help="Folder name.")],
    parent_id: Annotated[str | None, typer.Option("--parent-id")] = None,
    parent_path: Annotated[
        str | None, typer.Option("--parent-path", help="Human-readable parent path.")
    ] = None,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Create a folder, optionally nested under --parent-path or --parent-id."""
    if parent_id is not None and parent_path is not None:
        raise UserError("pass either --parent-id or --parent-path, not both")
    t, api, pid = _context(instance_name, project, verbose)
    try:
        resolved_parent: str | None = parent_id
        if parent_path is not None:
            resolved_parent = FolderPathResolver(api, pid).resolve_path(parent_path)
        created = api.create_folder(pid, name=name, parent_folder_id=resolved_parent)
        emit(created)
    finally:
        t.__exit__(None, None, None)


@app.command("patch")
def patch(
    id_: IdOpt = None,
    path: PathOpt = None,
    name: Annotated[
        str | None, typer.Option("--set", help="New name (--set name=... style).")
    ] = None,
    tag_ids: Annotated[
        list[str] | None, typer.Option("--tag-id", help="Replace tag list with these ids.")
    ] = None,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Rename a folder and/or replace its tags."""
    parsed_name: str | None = None
    if name is not None:
        parsed_name = name[len("name=") :] if name.startswith("name=") else name
    if parsed_name is None and tag_ids is None:
        raise UserError("nothing to update — pass --set name=... or --tag-id ...")

    t, api, pid = _context(instance_name, project, verbose)
    try:
        fid = _resolve_folder_id(api, pid, id_=id_, path=path)
        api.patch_folder(pid, fid, name=parsed_name, tag_ids=tag_ids)
        emit({"id": fid, "updated": True})
    finally:
        t.__exit__(None, None, None)


@app.command("delete")
def delete(
    id_: IdOpt = None,
    path: PathOpt = None,
    transfer_to: Annotated[
        str | None,
        typer.Option("--transfer-to", help="Move contents to this folder id before delete."),
    ] = None,
    transfer_to_path: Annotated[
        str | None, typer.Option("--transfer-to-path", help="Move contents to this path.")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Delete a folder. Optionally transfer its children to another folder first."""
    if transfer_to is not None and transfer_to_path is not None:
        raise UserError("pass either --transfer-to or --transfer-to-path, not both")
    t, api, pid = _context(instance_name, project, verbose)
    try:
        fid = _resolve_folder_id(api, pid, id_=id_, path=path)
        dst: str | None = transfer_to
        if transfer_to_path is not None:
            dst = FolderPathResolver(api, pid).resolve_path(transfer_to_path)
        if not force:
            typer.confirm(f"Delete folder {fid}?", abort=True)
        api.delete_folder(pid, fid, transfer_to=dst)
        emit({"deleted": fid})
    finally:
        t.__exit__(None, None, None)


@app.command("move")
def move(
    id_: Annotated[str, typer.Option("--id", help="Folder id.")],
    to_project: Annotated[str, typer.Option("--to-project", help="Destination project id.")],
    project: ProjectOpt = None,
    instance_name: InstanceOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Transfer a folder to another project (enterprise-only on some instances)."""
    t, api, pid = _context(instance_name, project, verbose)
    try:
        # No dedicated wrapper — send the PUT directly.
        api.t.put(
            f"/rest/projects/{pid}/folders/{id_}/transfer",
            json={"destinationProjectId": to_project},
        )
        emit({"moved": id_, "to_project": to_project})
    finally:
        t.__exit__(None, None, None)
