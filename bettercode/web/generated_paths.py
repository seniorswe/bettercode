from pathlib import Path

from fastapi import HTTPException

from bettercode.app_meta import bettercode_home_dir
from bettercode.context import Workspace


GENERATED_FILES_DIRNAME = "generated-files"


def _bettercode_home_dir() -> Path:
    return bettercode_home_dir(create=True)


def _workspace_generated_dir(workspace: Workspace | int, create: bool = False) -> Path:
    workspace_id = workspace.id if isinstance(workspace, Workspace) else int(workspace)
    path = _bettercode_home_dir() / GENERATED_FILES_DIRNAME / f"workspace-{workspace_id}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _workspace_generated_staging_dir(workspace: Workspace | int | str, create: bool = False) -> Path:
    if isinstance(workspace, Workspace):
        workspace_path = Path(workspace.path)
    elif isinstance(workspace, int):
        raise ValueError("Workspace path is required to resolve the staging directory.")
    else:
        workspace_path = Path(str(workspace))
    path = workspace_path / ".bettercode-generated"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_generated_file_path(workspace: Workspace | int, relative_path: str) -> Path:
    normalized = str(relative_path or "").strip().replace("\\", "/")
    if not normalized:
        raise HTTPException(status_code=400, detail="Generated file path is required.")

    relative = Path(normalized)
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="Generated file path must be relative.")

    generated_root = _workspace_generated_dir(workspace, create=False).resolve()
    candidate = (generated_root / relative).resolve()
    try:
        candidate.relative_to(generated_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Generated file path is invalid.") from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    return candidate
