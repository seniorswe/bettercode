from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable


def generated_files_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    serialize_workspace: Callable,
    workspace_generated_dir: Callable,
    workspace_generated_file_entries: Callable,
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        return {
            "workspace": serialize_workspace(workspace),
            "generated_root": str(workspace_generated_dir(workspace, create=False)),
            "generated_files": workspace_generated_file_entries(workspace),
        }


def mark_generated_files_seen_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    workspace_generated_file_count: Callable,
    serialize_workspace: Callable,
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        workspace.generated_files_seen_count = workspace_generated_file_count(workspace)
        db.commit()
        db.refresh(workspace)
        return {"workspace": serialize_workspace(workspace)}


def open_generated_file_payload(
    workspace_id: int,
    relative_path: str,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    resolve_generated_file_path: Callable,
    workspace_generated_dir: Callable,
    open_with_system_default: Callable,
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        file_path = resolve_generated_file_path(workspace, relative_path)
        open_with_system_default(file_path)
        return {
            "opened": True,
            "path": str(file_path.relative_to(workspace_generated_dir(workspace, create=False))),
            "absolute_path": str(file_path),
        }


def open_telemetry_log_payload(*, telemetry_log_path: Callable[[], Path], open_with_system_default: Callable[[Path], None]) -> dict:
    log_path = telemetry_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    open_with_system_default(log_path)
    return {
        "opened": True,
        "path": str(log_path),
    }


def delete_workspace_generated_files(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
