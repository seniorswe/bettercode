from __future__ import annotations

from typing import Callable


def _git_has_head(workspace_path: str, run_git: Callable) -> bool:
    result = run_git(workspace_path, ["rev-parse", "--verify", "HEAD"], check=False)
    return int(getattr(result, "returncode", 1) or 0) == 0


def git_status_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        return {"git": parse_git_status(workspace.path)}


def review_files_payload(
    workspace_id: int,
    *,
    limit: int,
    session_factory,
    get_workspace_or_404: Callable,
    parse_git_status: Callable[[str], dict],
    review_changed_files: Callable[..., list[dict]],
    workspace_recent_file_entries: Callable[..., list[dict]],
    serialize_workspace: Callable,
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        git_state = parse_git_status(workspace.path)
        changed_files = review_changed_files(git_state, limit=limit)
        recent_files = workspace_recent_file_entries(
            workspace.path,
            limit=limit,
            exclude_paths={item["path"] for item in changed_files},
        )
        return {
            "workspace": serialize_workspace(workspace),
            "git": {
                "is_repo": bool(git_state.get("is_repo")),
                "branch": git_state.get("branch") or "",
            },
            "changed_files": changed_files,
            "recent_files": recent_files,
        }


def git_stage_all_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        run_git(workspace.path, ["add", "-A"])
        invalidate_workspace_caches(workspace.path)
        return {"git": parse_git_status(workspace.path)}


def git_init_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        run_git(workspace.path, ["init"])
        invalidate_workspace_caches(workspace.path)
        return {"git": parse_git_status(workspace.path)}


def git_unstage_all_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        if _git_has_head(workspace.path, run_git):
            run_git(workspace.path, ["reset", "HEAD", "--", "."])
        else:
            run_git(workspace.path, ["rm", "--cached", "-r", "--", "."])
        invalidate_workspace_caches(workspace.path)
        return {"git": parse_git_status(workspace.path)}


def git_stage_files_payload(
    workspace_id: int,
    paths: list[str],
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
    normalize_git_paths: Callable[[list[str]], list[str]],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        normalized_paths = normalize_git_paths(paths)
        run_git(workspace.path, ["add", "--", *normalized_paths])
        invalidate_workspace_caches(workspace.path)
        return {"git": parse_git_status(workspace.path)}


def git_unstage_files_payload(
    workspace_id: int,
    paths: list[str],
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
    normalize_git_paths: Callable[[list[str]], list[str]],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        normalized_paths = normalize_git_paths(paths)
        if _git_has_head(workspace.path, run_git):
            run_git(workspace.path, ["reset", "HEAD", "--", *normalized_paths])
        else:
            run_git(workspace.path, ["rm", "--cached", "-r", "--", *normalized_paths])
        invalidate_workspace_caches(workspace.path)
        return {"git": parse_git_status(workspace.path)}


def git_fetch_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        result = run_git(workspace.path, ["fetch", "--all", "--prune"])
        invalidate_workspace_caches(workspace.path)
        return {"output": (result.stdout or result.stderr).strip(), "git": parse_git_status(workspace.path)}


def git_pull_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        result = run_git(workspace.path, ["pull", "--ff-only"])
        invalidate_workspace_caches(workspace.path)
        return {"output": (result.stdout or result.stderr).strip(), "git": parse_git_status(workspace.path)}


def git_update_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        fetch_result = run_git(workspace.path, ["fetch", "--all", "--prune"])
        pull_result = run_git(workspace.path, ["pull", "--ff-only"])
        invalidate_workspace_caches(workspace.path)
        output = "\n".join(
            filter(
                None,
                [
                    (fetch_result.stdout or fetch_result.stderr).strip(),
                    (pull_result.stdout or pull_result.stderr).strip(),
                ],
            )
        ).strip()
        return {"output": output, "git": parse_git_status(workspace.path)}


def git_commit_payload(
    workspace_id: int,
    message: str,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
    normalize_commit_message: Callable[[str], str],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        normalized_message = normalize_commit_message(message)
        result = run_git(workspace.path, ["commit", "-m", normalized_message])
        invalidate_workspace_caches(workspace.path)
        return {"output": (result.stdout or result.stderr).strip(), "git": parse_git_status(workspace.path)}


def git_push_payload(
    workspace_id: int,
    *,
    session_factory,
    get_workspace_or_404: Callable,
    run_git: Callable,
    invalidate_workspace_caches: Callable[[str], None],
    parse_git_status: Callable[[str], dict],
) -> dict:
    with session_factory() as db:
        workspace = get_workspace_or_404(db, workspace_id)
        result = run_git(workspace.path, ["push"])
        invalidate_workspace_caches(workspace.path)
        return {"output": (result.stdout or result.stderr).strip(), "git": parse_git_status(workspace.path)}
