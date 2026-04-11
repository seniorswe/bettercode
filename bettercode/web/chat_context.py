import re
from pathlib import Path

from bettercode.context import Message, Workspace, WorkspaceTab
from bettercode.router.selector import analyze_routing_task


TARGET_FILE_LIMIT = 6
RECENT_HISTORY_LIMIT = 4
RECENT_HISTORY_CHARS = 220
PROMPT_KEYWORD_RE = re.compile(r"[a-z0-9_.-]{2,}", re.IGNORECASE)


def _prompt_keywords(text: str) -> set[str]:
    return {match.group(0).lower() for match in PROMPT_KEYWORD_RE.finditer(text or "")}


def _relevance_score(text: str, keywords: set[str]) -> int:
    if not text:
        return 0
    lowered = text.lower()
    score = 0
    for keyword in keywords:
        if keyword in lowered:
            score += 3 if "." in keyword else 1
    return score


def _rank_recent_messages(messages: list[Message], request_text: str, limit: int, char_limit: int) -> list[str]:
    keywords = _prompt_keywords(request_text)
    ranked = sorted(
        messages,
        key=lambda message: (
            _relevance_score(message.content or "", keywords),
            message.id,
        ),
        reverse=True,
    )
    selected = sorted(ranked[:limit], key=lambda message: message.id)
    return [f"{message.role}: {(message.content or '')[:char_limit]}" for message in selected]


def _git_candidate_paths(git_state: dict) -> list[str]:
    seen = set()
    ordered = []
    for bucket in ("changed", "staged", "untracked"):
        for entry in git_state.get(bucket, []) or []:
            path = str((entry or {}).get("path") or "").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            ordered.append(path)
    return ordered


def _rank_target_files(request_text: str, git_state: dict, limit: int = TARGET_FILE_LIMIT) -> list[str]:
    keywords = _prompt_keywords(request_text)
    request_lower = (request_text or "").lower()

    def mention_index(path: str) -> int:
        basename = Path(path).name.lower()
        direct = request_lower.find(path.lower())
        if direct >= 0:
            return direct
        base = request_lower.find(basename)
        return base if base >= 0 else 10**9

    ranked = sorted(
        _git_candidate_paths(git_state),
        key=lambda path: (
            mention_index(path) == 10**9,
            mention_index(path),
            -_relevance_score(path, keywords),
            len(Path(path).parts),
            path,
        ),
    )
    return ranked[:limit]


def _request_goal(request_text: str) -> str:
    text = " ".join((request_text or "").split()).strip()
    if not text:
        return "Handle the user's request."
    return text[:180] + ("..." if len(text) > 180 else "")


def _execution_mode(task_analysis: dict) -> str:
    task_type = task_analysis.get("task_type") or "general"
    if task_type in {"review", "architecture"}:
        return "Analysis-first response"
    if task_type in {"debugging", "implementation", "small_edit"}:
        return "Targeted repo changes"
    return "Direct answer unless code changes are clearly needed"


def _success_criteria(task_analysis: dict, target_files: list[str], attachments: list[dict]) -> str:
    task_type = task_analysis.get("task_type") or "general"
    if task_type == "review":
        return "Call out concrete risks, regressions, and missing coverage."
    if task_type == "architecture":
        return "Return a clear design with practical tradeoffs and next steps."
    if task_type == "debugging":
        return "Identify the root cause and fix the actual failure path."
    if task_type in {"implementation", "small_edit"} and target_files:
        return f"Make the needed changes with minimal scope, starting from {', '.join(target_files[:3])}."
    if attachments:
        return "Use the attachment content directly and keep the answer grounded in it."
    return "Answer directly and stay focused on the requested outcome."


def _ambiguity_note(request_text: str, task_analysis: dict, target_files: list[str]) -> str:
    text = (request_text or "").lower()
    if task_analysis.get("task_type") == "general" and len(text.split()) <= 6:
        return "The request is terse; inspect only the most relevant context before expanding scope."
    if any(token in text for token in ("this", "that", "it")) and not target_files:
        return "The request may be underspecified; rely on the nearest relevant context, then proceed conservatively."
    return ""


def _tab_message_query(db, workspace: Workspace, tab: WorkspaceTab | None):
    query = db.query(Message).filter(Message.workspace_id == workspace.id)
    if tab is not None:
        query = query.filter(Message.tab_id == tab.id)
    return query


def _build_preprocessed_turn_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    parse_git_status,
    tab: WorkspaceTab | None = None,
) -> dict:
    git_state = parse_git_status(workspace.path)
    recent_messages = (
        _tab_message_query(db, workspace, tab)
        .order_by(Message.created_at.desc())
        .limit(8)
        .all()
    )
    context_summary = (tab.context_summary if tab is not None else workspace.context_summary) or "None"
    task_context = "\n".join(
        part for part in (
            f"Workspace: {workspace.name}",
            f"Context summary: {context_summary}",
            f"Attachments: {', '.join(attachment['name'] for attachment in attachments) if attachments else 'None'}",
            f"Changed files: {', '.join(_git_candidate_paths(git_state)[:12]) or 'None'}",
        ) if part
    )
    task_analysis = analyze_routing_task(request_text, task_context)
    target_files = _rank_target_files(request_text, git_state)
    recent_history = _rank_recent_messages(recent_messages, request_text, RECENT_HISTORY_LIMIT, RECENT_HISTORY_CHARS)
    return {
        "git_state": git_state,
        "task_analysis": task_analysis,
        "goal": _request_goal(request_text),
        "execution_mode": _execution_mode(task_analysis),
        "target_files": target_files,
        "recent_history": recent_history,
        "attachment_names": [attachment["name"] for attachment in attachments],
        "success_criteria": _success_criteria(task_analysis, target_files, attachments),
        "ambiguity_note": _ambiguity_note(request_text, task_analysis, target_files),
    }


def _selector_context_limits(git_state: dict, attachments: list[dict]) -> dict:
    changed_total = (
        len(git_state.get("changed", []))
        + len(git_state.get("staged", []))
        + len(git_state.get("untracked", []))
    )
    large_repo = changed_total >= 24
    return {
        "history_limit": 3 if large_repo else 6,
        "history_chars": 220 if large_repo else 500,
        "changed_limit": 6 if large_repo else 12,
        "attachment_limit": 4 if large_repo else 8,
        "summary_chars": 320 if large_repo else 900,
    }


def _build_selector_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    parse_git_status,
    tab: WorkspaceTab | None = None,
) -> str:
    preprocessed = _build_preprocessed_turn_context(db, workspace, request_text, attachments, parse_git_status, tab=tab)
    git_state = preprocessed["git_state"]
    limits = _selector_context_limits(git_state, attachments)
    history_lines = preprocessed["recent_history"][:limits["history_limit"]]
    changed_paths = preprocessed["target_files"][:limits["changed_limit"]]
    attachment_names = [attachment["name"] for attachment in attachments[:limits["attachment_limit"]]]
    summary_source = tab.context_summary if tab is not None else workspace.context_summary
    summary = (summary_source or "")[:limits["summary_chars"]] or "None"

    parts = [
        f"Workspace: {workspace.name}",
        f"Goal: {preprocessed['goal'] or 'None'}",
        f"Execution mode: {preprocessed['execution_mode']}",
        f"Success criteria: {preprocessed['success_criteria']}",
        f"Context summary: {summary}",
        f"Recent relevant history: {' | '.join(history_lines) if history_lines else 'None'}",
        f"Focus files: {', '.join(changed_paths) if changed_paths else 'None'}",
        f"Attachments: {', '.join(attachment_names) if attachment_names else 'None'}",
    ]
    if preprocessed["ambiguity_note"]:
        parts.append(f"Ambiguity note: {preprocessed['ambiguity_note']}")
    return "\n".join(parts)


def _build_manual_task_context(db, workspace: Workspace, attachments: list[dict], tab: WorkspaceTab | None = None) -> str:
    recent_messages = (
        _tab_message_query(db, workspace, tab)
        .order_by(Message.created_at.desc())
        .limit(4)
        .all()
    )
    recent_messages = list(reversed(recent_messages))
    history_lines = [f"{message.role}: {message.content[:240]}" for message in recent_messages]
    attachment_names = [attachment["name"] for attachment in attachments]
    context_summary = tab.context_summary if tab is not None else workspace.context_summary

    parts = [
        f"Workspace: {workspace.name}",
        f"Context summary: {context_summary or 'None'}",
        f"Recent history: {' | '.join(history_lines) if history_lines else 'None'}",
        f"Attachments: {', '.join(attachment_names) if attachment_names else 'None'}",
    ]
    return "\n".join(parts)


def _manual_task_analysis(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    tab: WorkspaceTab | None = None,
) -> dict:
    selector_context = _build_manual_task_context(db, workspace, attachments, tab=tab)
    return analyze_routing_task(request_text, selector_context)
