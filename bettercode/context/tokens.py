from typing import Any

try:
    import tiktoken
except ImportError:  # pragma: no cover - exercised via environments without tiktoken
    tiktoken = None
from sqlalchemy.orm import Session

from bettercode.context.state import Message, Workspace, WorkspaceTab
from bettercode.router.selector import squash_workspace_context

_ENCODING_CACHE: dict[str, Any] = {}


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    encoding = _ENCODING_CACHE.get(model)
    if encoding is None:
        try:
            if tiktoken is None:
                raise RuntimeError("tiktoken is unavailable")
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            try:
                encoding = _ENCODING_CACHE.get("cl100k_base") or tiktoken.get_encoding("cl100k_base")
                _ENCODING_CACHE["cl100k_base"] = encoding
            except Exception:
                encoding = None
        except Exception:
            encoding = None
        _ENCODING_CACHE[model] = encoding
    if encoding is None:
        word_count = len(text.split())
        return max(1, max(word_count, (len(text) + 5) // 6))
    return len(encoding.encode(text))


def token_count_for_content(content: str) -> int:
    return count_tokens(content)


def _resolve_workspace_tab(db: Session, workspace: Workspace, tab: WorkspaceTab | None = None) -> WorkspaceTab | None:
    if tab is not None:
        return tab
    return (
        db.query(WorkspaceTab)
        .filter(WorkspaceTab.workspace_id == workspace.id, WorkspaceTab.archived_at.is_(None))
        .order_by(WorkspaceTab.sort_order.asc(), WorkspaceTab.id.asc())
        .first()
    )


def _tab_message_query(db: Session, workspace: Workspace, tab: WorkspaceTab | None):
    query = db.query(Message).filter(Message.workspace_id == workspace.id)
    if tab is not None:
        query = query.filter(Message.tab_id == tab.id)
    return query


def refresh_workspace_token_totals(db: Session, workspace: Workspace, tab: WorkspaceTab | None = None) -> int:
    resolved_tab = _resolve_workspace_tab(db, workspace, tab)
    target = resolved_tab or workspace

    messages = (
        _tab_message_query(db, workspace, resolved_tab)
        .order_by(Message.id.asc())
        .all()
    )
    total_tokens = 0
    changed = False
    for message in messages:
        token_count = int(message.token_count or 0)
        if token_count <= 0 and message.content:
            token_count = token_count_for_content(message.content)
            message.token_count = token_count
            changed = True
        total_tokens += max(0, token_count)

    if int(target.active_message_tokens or 0) != total_tokens:
        target.active_message_tokens = total_tokens
        changed = True

    if changed:
        db.commit()
        db.refresh(target)

    return total_tokens


def append_workspace_message_tokens(workspace: Workspace, content: str, tab: WorkspaceTab | None = None) -> int:
    token_count = token_count_for_content(content)
    target = tab or workspace
    target.active_message_tokens = max(0, int(target.active_message_tokens or 0)) + token_count
    return token_count


MAX_CONTEXT_SUMMARY_CHARS = 6_000  # ≈ 1 500 tokens — keeps paid-model prompts lean


def build_workspace_context_block(workspace: Workspace, tab: WorkspaceTab | None = None) -> str:
    summary = (tab.context_summary or "").strip() if tab is not None else ""
    if not summary:
        summary = (workspace.context_summary or "").strip()
    if not summary:
        return ""

    if len(summary) > MAX_CONTEXT_SUMMARY_CHARS:
        # Keep the tail — most recent context is most relevant.
        summary = "… [earlier context trimmed]\n" + summary[-MAX_CONTEXT_SUMMARY_CHARS:]

    return (
        "Workspace context summary:\n"
        f"{summary}\n\n"
        "Use this summary as durable project context. Prefer it over stale older chat details when they conflict."
    )


def manage_workspace_context(
    db: Session,
    workspace: Workspace,
    tab: WorkspaceTab | None = None,
    max_tokens: int = 6000,
    keep_recent_messages: int = 8,
) -> bool:
    resolved_tab = _resolve_workspace_tab(db, workspace, tab)
    target = resolved_tab or workspace

    total_tokens = int(target.active_message_tokens or 0)
    if total_tokens <= 0:
        total_tokens = refresh_workspace_token_totals(db, workspace, resolved_tab)

    if total_tokens <= max_tokens:
        return False

    messages = (
        _tab_message_query(db, workspace, resolved_tab)
        .order_by(Message.id.asc())
        .all()
    )

    to_keep = messages[-keep_recent_messages:]
    to_squash = messages[:-keep_recent_messages]
    if not to_squash:
        return False

    transcript = "\n".join(f"{message.role}: {message.content}" for message in to_squash).strip()
    if not transcript:
        return False

    merged_summary = squash_workspace_context(target.context_summary or "", transcript).strip()
    if not merged_summary:
        return False

    for message in to_squash:
        db.delete(message)

    target.context_summary = merged_summary
    # Include the summary's own token cost so the next budget check is accurate.
    kept_tokens = sum(max(0, int(message.token_count or 0)) for message in to_keep)
    summary_tokens = token_count_for_content(merged_summary)
    target.active_message_tokens = kept_tokens + summary_tokens
    db.commit()
    return True
