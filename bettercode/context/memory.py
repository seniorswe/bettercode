import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from bettercode.context.state import MemoryEntry, Workspace, WorkspaceTab

MEMORY_BUCKETS = ("short", "medium", "long")
MEMORY_BUCKET_PRIORITY = {bucket: index for index, bucket in enumerate(MEMORY_BUCKETS)}
MEMORY_KINDS = ("preference", "constraint", "task", "project", "fact")
MEDIUM_TERM_TTL = timedelta(hours=48)
MAX_MEMORY_CONTEXT_ITEMS = {"short": 4, "medium": 6, "long": 8}
MAX_MEMORY_CONTEXT_CHARS = 280
_WHITESPACE_RE = re.compile(r"\s+")
_NORMALIZED_RE = re.compile(r"[^a-z0-9]+")
_KEYWORD_RE = re.compile(r"[a-z0-9_./:-]{2,}", re.IGNORECASE)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_memory_bucket(bucket: str | None) -> str | None:
    value = (bucket or "").strip().lower()
    return value if value in MEMORY_BUCKETS else None


def normalize_memory_kind(kind: str | None) -> str:
    value = (kind or "").strip().lower()
    return value if value in MEMORY_KINDS else "fact"


def normalize_memory_content(content: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", str(content or "").strip())


def normalize_memory_key(content: str | None) -> str:
    normalized = normalize_memory_content(content).lower()
    normalized = _NORMALIZED_RE.sub(" ", normalized)
    return _WHITESPACE_RE.sub(" ", normalized).strip()[:240]


def memory_expires_at(bucket: str, now: datetime | None = None) -> datetime | None:
    resolved_bucket = normalize_memory_bucket(bucket)
    if resolved_bucket != "medium":
        return None
    current_time = now or _utcnow()
    return current_time + MEDIUM_TERM_TTL


def serialize_memory_entry(entry: MemoryEntry) -> dict:
    return {
        "id": entry.id,
        "workspace_id": entry.workspace_id,
        "tab_id": entry.tab_id,
        "bucket": entry.bucket,
        "kind": entry.kind or "fact",
        "content": entry.content,
        "source": entry.source or "",
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
        "last_accessed_at": entry.last_accessed_at.isoformat() if entry.last_accessed_at else None,
        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
    }


def prune_expired_memory_entries(
    db: Session,
    workspace: Workspace | int | None = None,
    tab: WorkspaceTab | int | None = None,
    now: datetime | None = None,
) -> int:
    current_time = now or _utcnow()
    query = db.query(MemoryEntry).filter(
        MemoryEntry.expires_at.isnot(None),
        MemoryEntry.expires_at <= current_time,
    )
    if workspace is not None:
        workspace_id = workspace if isinstance(workspace, int) else workspace.id
        query = query.filter(MemoryEntry.workspace_id == workspace_id)
    if tab is not None:
        tab_id = tab if isinstance(tab, int) else tab.id
        query = query.filter(MemoryEntry.tab_id == tab_id)
    try:
        deleted = query.delete(synchronize_session=False)
    except OperationalError:
        db.rollback()
        return 0
    if deleted:
        db.flush()
    return int(deleted or 0)


def list_memory_entries(
    db: Session,
    workspace: Workspace | int,
    tab: WorkspaceTab | int,
    include_expired: bool = False,
    now: datetime | None = None,
) -> list[MemoryEntry]:
    if not include_expired:
        prune_expired_memory_entries(db, workspace=workspace, tab=tab, now=now)

    workspace_id = workspace if isinstance(workspace, int) else workspace.id
    tab_id = tab if isinstance(tab, int) else tab.id
    query = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.workspace_id == workspace_id, MemoryEntry.tab_id == tab_id)
        .order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id.desc())
    )
    if not include_expired:
        current_time = now or _utcnow()
        query = query.filter(
            (MemoryEntry.expires_at.is_(None)) | (MemoryEntry.expires_at > current_time)
        )
    return query.all()


def clear_memory_entries(
    db: Session,
    workspace: Workspace | int,
    tab: WorkspaceTab | int,
    bucket: str | None = None,
    now: datetime | None = None,
) -> int:
    prune_expired_memory_entries(db, workspace=workspace, tab=tab, now=now)
    workspace_id = workspace if isinstance(workspace, int) else workspace.id
    tab_id = tab if isinstance(tab, int) else tab.id
    query = db.query(MemoryEntry).filter(
        MemoryEntry.workspace_id == workspace_id,
        MemoryEntry.tab_id == tab_id,
    )
    resolved_bucket = normalize_memory_bucket(bucket)
    if resolved_bucket:
        query = query.filter(MemoryEntry.bucket == resolved_bucket)
    deleted = query.delete(synchronize_session=False)
    if deleted:
        db.flush()
    return int(deleted or 0)


def _resolved_bucket(existing_bucket: str, incoming_bucket: str) -> str:
    current = normalize_memory_bucket(existing_bucket) or "short"
    incoming = normalize_memory_bucket(incoming_bucket) or "short"
    if MEMORY_BUCKET_PRIORITY[incoming] >= MEMORY_BUCKET_PRIORITY[current]:
        return incoming
    return current


def _infer_memory_kind(content: str) -> str:
    lowered = content.lower()
    if any(token in lowered for token in ("prefers", "preference", "always", "never", "keep replies", "answer style")):
        return "preference"
    if any(token in lowered for token in ("must", "cannot", "can't", "should not", "constraint", "requirement")):
        return "constraint"
    if any(token in lowered for token in ("working on", "current task", "next step", "todo", "follow up")):
        return "task"
    if any(token in lowered for token in ("workspace", "repo", "project", "file", "branch", "module", ".py", ".js", ".ts")):
        return "project"
    return "fact"


def _prompt_keywords(text: str) -> set[str]:
    return {match.group(0).lower() for match in _KEYWORD_RE.finditer(text or "")}


def upsert_memory_entries(
    db: Session,
    workspace: Workspace,
    tab: WorkspaceTab,
    entries: list[dict],
    source: str = "auto",
    now: datetime | None = None,
) -> list[MemoryEntry]:
    current_time = now or _utcnow()
    prune_expired_memory_entries(db, workspace=workspace, tab=tab, now=current_time)

    normalized_entries: list[tuple[str, str, str, str]] = []
    seen_keys: set[str] = set()
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        bucket = normalize_memory_bucket(item.get("bucket"))
        content = normalize_memory_content(item.get("content"))
        kind = normalize_memory_kind(item.get("kind")) if item.get("kind") is not None else _infer_memory_kind(content)
        key = normalize_memory_key(content)
        if not bucket or len(content) < 8 or not key or key in seen_keys:
            continue
        seen_keys.add(key)
        normalized_entries.append((bucket, kind, content[:400], key))

    if not normalized_entries:
        return []

    existing_entries = {
        entry.normalized_content: entry
        for entry in list_memory_entries(db, workspace, tab, include_expired=True, now=current_time)
        if (entry.normalized_content or "").strip()
    }

    touched: list[MemoryEntry] = []
    for bucket, kind, content, key in normalized_entries:
        existing = existing_entries.get(key)
        if existing is None:
            existing = MemoryEntry(
                workspace_id=workspace.id,
                tab_id=tab.id,
                bucket=bucket,
                kind=kind,
                content=content,
                normalized_content=key,
                source=source,
                created_at=current_time,
                updated_at=current_time,
                expires_at=memory_expires_at(bucket, current_time),
            )
            db.add(existing)
            existing_entries[key] = existing
        else:
            resolved_bucket = _resolved_bucket(existing.bucket, bucket)
            if MEMORY_BUCKET_PRIORITY[bucket] >= MEMORY_BUCKET_PRIORITY.get(existing.bucket, 0):
                existing.content = content
            existing.bucket = resolved_bucket
            existing.kind = kind
            existing.source = source
            existing.updated_at = current_time
            existing.expires_at = memory_expires_at(resolved_bucket, current_time)
        touched.append(existing)

    db.flush()
    return touched


def retrieve_memory_entries(
    db: Session,
    workspace: Workspace,
    tab: WorkspaceTab,
    request_text: str,
    limit: int = 8,
    now: datetime | None = None,
) -> list[MemoryEntry]:
    current_time = now or _utcnow()
    entries = list_memory_entries(db, workspace, tab, include_expired=False, now=current_time)
    if not entries:
        return []

    request_keywords = _prompt_keywords(request_text)
    request_lower = (request_text or "").lower()
    bucket_weight = {"short": 42, "medium": 26, "long": 16}
    kind_weight = {"preference": 18, "constraint": 16, "task": 12, "project": 10, "fact": 6}

    scored: list[tuple[tuple[int, float, int], MemoryEntry]] = []
    for entry in entries:
        content = (entry.content or "").strip()
        if not content:
            continue
        entry_keywords = _prompt_keywords(content)
        overlap = len(request_keywords & entry_keywords)
        direct_match = 1 if request_lower and content.lower() in request_lower else 0
        mention_match = 0
        if request_lower:
            for keyword in entry_keywords:
                if len(keyword) >= 3 and keyword in request_lower:
                    mention_match += 1
        recency_anchor = entry.updated_at or entry.created_at or current_time
        if recency_anchor is not None and recency_anchor.tzinfo is None:
            recency_anchor = recency_anchor.replace(tzinfo=UTC)
        age_seconds = max(0.0, (current_time - recency_anchor).total_seconds()) if recency_anchor else 0.0
        recency_bonus = max(0.0, 7.0 - min(7.0, age_seconds / 43200.0))
        score = (
            bucket_weight.get(normalize_memory_bucket(entry.bucket) or "short", 0)
            + kind_weight.get(normalize_memory_kind(entry.kind), 0)
            + overlap * 14
            + min(mention_match, 4) * 5
            + direct_match * 12
        )
        if not request_keywords and normalize_memory_kind(entry.kind) == "preference":
            score += 8
        if request_keywords and overlap == 0 and normalize_memory_kind(entry.kind) not in {"preference", "constraint"}:
            score -= 8
        scored.append(((score, recency_bonus, entry.id), entry))

    scored.sort(key=lambda item: item[0], reverse=True)

    selected: list[MemoryEntry] = []
    seen_ids: set[int] = set()
    selected_kinds: set[str] = set()

    for _, entry in scored:
        kind = normalize_memory_kind(entry.kind)
        if kind == "preference" and entry.id not in seen_ids:
            selected.append(entry)
            seen_ids.add(entry.id)
            selected_kinds.add(kind)
        if len(selected) >= min(limit, 2):
            break

    for _, entry in scored:
        if entry.id in seen_ids:
            continue
        selected.append(entry)
        seen_ids.add(entry.id)
        selected_kinds.add(normalize_memory_kind(entry.kind))
        if len(selected) >= limit:
            break

    for entry in selected:
        entry.last_accessed_at = current_time
    if selected:
        db.flush()
    return selected


def build_memory_context_block(
    db: Session,
    workspace: Workspace,
    tab: WorkspaceTab,
    request_text: str = "",
    limit: int = 8,
    now: datetime | None = None,
) -> str:
    entries = retrieve_memory_entries(db, workspace, tab, request_text=request_text, limit=limit, now=now)
    if not entries:
        return ""

    lines = []
    for entry in entries:
        bucket = normalize_memory_bucket(entry.bucket) or "short"
        kind = normalize_memory_kind(entry.kind)
        lines.append(f"- [{bucket}/{kind}] {entry.content[:MAX_MEMORY_CONTEXT_CHARS]}")
    return "Relevant memory for this turn:\n" + "\n".join(lines)
