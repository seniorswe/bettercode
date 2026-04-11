from datetime import UTC, datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from bettercode.app_meta import bettercode_home_dir

Base = declarative_base()


def utc_now():
    return datetime.now(UTC)

class Workspace(Base):
    __tablename__ = 'workspaces'
    __table_args__ = (
        Index("ix_workspaces_last_used_at_id", "last_used_at", "id"),
    )
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    path = Column(String, unique=True, nullable=False)
    context_summary = Column(Text, default="")
    active_message_tokens = Column(Integer, default=0)
    codex_session_id = Column(String, default="")
    claude_session_id = Column(String, default="")
    cursor_session_id = Column(String, default="")
    last_model = Column(String, default="")
    last_runtime = Column(String, default="")
    last_request_text = Column(Text, default="")
    last_request_model = Column(String, default="")
    last_request_agent_mode = Column(String, default="")
    last_request_attachments = Column(Text, default="[]")
    session_state = Column(String, default="cold")
    generated_files_seen_count = Column(Integer, nullable=True)
    run_settings = Column(Text, default='{}')
    last_used_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    messages = relationship("Message", back_populates="workspace", cascade="all, delete-orphan")
    tabs = relationship("WorkspaceTab", back_populates="workspace", cascade="all, delete-orphan")
    memories = relationship("MemoryEntry", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceTab(Base):
    __tablename__ = 'workspace_tabs'
    __table_args__ = (
        Index("ix_workspace_tabs_workspace_id_sort_order_id", "workspace_id", "sort_order", "id"),
        Index("ix_workspace_tabs_workspace_id_archived_at_id", "workspace_id", "archived_at", "id"),
        Index("ix_workspace_tabs_last_used_at_id", "last_used_at", "id"),
    )
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'), nullable=False)
    title = Column(String, nullable=False, default="New Tab")
    sort_order = Column(Integer, default=0)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    context_summary = Column(Text, default="")
    active_message_tokens = Column(Integer, default=0)
    codex_session_id = Column(String, default="")
    claude_session_id = Column(String, default="")
    cursor_session_id = Column(String, default="")
    last_model = Column(String, default="")
    last_runtime = Column(String, default="")
    last_request_text = Column(Text, default="")
    last_request_model = Column(String, default="")
    last_request_agent_mode = Column(String, default="")
    last_request_attachments = Column(Text, default="[]")
    session_state = Column(String, default="cold")
    last_used_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now)
    workspace = relationship("Workspace", back_populates="tabs")
    messages = relationship("Message", back_populates="tab")
    memories = relationship("MemoryEntry", back_populates="tab", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        Index("ix_messages_workspace_id_id", "workspace_id", "id"),
        Index("ix_messages_workspace_id_created_at", "workspace_id", "created_at"),
        Index("ix_messages_tab_id_id", "tab_id", "id"),
        Index("ix_messages_tab_id_created_at", "tab_id", "created_at"),
    )
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'), nullable=False)
    tab_id = Column(Integer, ForeignKey('workspace_tabs.id'), nullable=True)
    role = Column(String, nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    activity_log = Column(Text, default="")
    history_log = Column(Text, default="")
    terminal_log = Column(Text, default="")
    change_log = Column(Text, default="")
    recommendations = Column(Text, default="")
    routing_meta = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    workspace = relationship("Workspace", back_populates="messages")
    tab = relationship("WorkspaceTab", back_populates="messages")


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (
        Index("ix_memory_entries_workspace_id_tab_id_created_at", "workspace_id", "tab_id", "created_at"),
        Index("ix_memory_entries_workspace_id_tab_id_bucket", "workspace_id", "tab_id", "bucket"),
        Index("ix_memory_entries_expires_at", "expires_at"),
    )
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    tab_id = Column(Integer, ForeignKey("workspace_tabs.id"), nullable=False)
    bucket = Column(String, nullable=False, default="short")
    kind = Column(String, nullable=False, default="fact")
    content = Column(Text, nullable=False)
    normalized_content = Column(String, nullable=False, default="")
    source = Column(String, default="auto")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    workspace = relationship("Workspace", back_populates="memories")
    tab = relationship("WorkspaceTab", back_populates="memories")


class RouterTelemetry(Base):
    __tablename__ = 'router_telemetry'
    __table_args__ = (
        Index("ix_router_telemetry_workspace_id_created_at", "workspace_id", "created_at"),
        Index("ix_router_telemetry_created_at", "created_at"),
    )
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'), nullable=True)
    model_id = Column(String, nullable=False, default="")
    runtime = Column(String, default="")
    source = Column(String, default="")
    task_type = Column(String, default="")
    complexity = Column(Integer, default=0)
    estimated_tokens = Column(Integer, default=0)
    success = Column(Integer, default=0)
    changed_files = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    workspace = relationship("Workspace")


class CodeReview(Base):
    __tablename__ = 'code_reviews'
    __table_args__ = (
        Index("ix_code_reviews_workspace_id_created_at", "workspace_id", "created_at"),
    )
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey('workspaces.id'), nullable=False)
    depth = Column(String, default="standard")
    files = Column(Text, default="[]")
    primary_model = Column(String, default="")
    secondary_model = Column(String, default="")
    primary_model_label = Column(String, default="")
    secondary_model_label = Column(String, default="")
    summary_primary = Column(Text, default="")
    summary_secondary = Column(Text, default="")
    findings = Column(Text, default="[]")
    activity_log = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    workspace = relationship("Workspace")

def get_db_path():
    return bettercode_home_dir(create=True) / "state.db"

engine = None
SessionLocal = sessionmaker()


def _ensure_workspace_columns():
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(workspaces)").fetchall()
        }
        if "active_message_tokens" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN active_message_tokens INTEGER DEFAULT 0")
        if "codex_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN codex_session_id TEXT DEFAULT ''")
        if "claude_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN claude_session_id TEXT DEFAULT ''")
        if "cursor_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN cursor_session_id TEXT DEFAULT ''")
        if "last_model" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_model TEXT DEFAULT ''")
        if "last_runtime" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_runtime TEXT DEFAULT ''")
        if "last_request_text" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_request_text TEXT DEFAULT ''")
        if "last_request_model" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_request_model TEXT DEFAULT ''")
        if "last_request_agent_mode" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_request_agent_mode TEXT DEFAULT ''")
        if "last_request_attachments" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_request_attachments TEXT DEFAULT '[]'")
        if "session_state" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN session_state TEXT DEFAULT 'cold'")
        if "last_used_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN last_used_at DATETIME")
        if "generated_files_seen_count" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN generated_files_seen_count INTEGER")
        if "run_settings" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspaces ADD COLUMN run_settings TEXT DEFAULT '{}'")


def _ensure_message_columns():
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(messages)").fetchall()
        }
        if "tab_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN tab_id INTEGER")
        if "token_count" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN token_count INTEGER DEFAULT 0")
        if "activity_log" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN activity_log TEXT DEFAULT ''")
        if "history_log" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN history_log TEXT DEFAULT ''")
        if "terminal_log" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN terminal_log TEXT DEFAULT ''")
        if "change_log" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN change_log TEXT DEFAULT ''")
        if "recommendations" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN recommendations TEXT DEFAULT ''")
        if "routing_meta" not in columns:
            connection.exec_driver_sql("ALTER TABLE messages ADD COLUMN routing_meta TEXT DEFAULT ''")


def _ensure_workspace_tab_columns():
    with engine.begin() as connection:
        table_exists = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_tabs'"
        ).fetchone()
        if not table_exists:
            return

        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(workspace_tabs)").fetchall()
        }
        if "title" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN title TEXT DEFAULT 'New Tab'")
        if "sort_order" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN sort_order INTEGER DEFAULT 0")
        if "archived_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN archived_at DATETIME")
        if "context_summary" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN context_summary TEXT DEFAULT ''")
        if "active_message_tokens" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN active_message_tokens INTEGER DEFAULT 0")
        if "codex_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN codex_session_id TEXT DEFAULT ''")
        if "claude_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN claude_session_id TEXT DEFAULT ''")
        if "cursor_session_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN cursor_session_id TEXT DEFAULT ''")
        if "last_model" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_model TEXT DEFAULT ''")
        if "last_runtime" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_runtime TEXT DEFAULT ''")
        if "last_request_text" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_request_text TEXT DEFAULT ''")
        if "last_request_model" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_request_model TEXT DEFAULT ''")
        if "last_request_agent_mode" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_request_agent_mode TEXT DEFAULT ''")
        if "last_request_attachments" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_request_attachments TEXT DEFAULT '[]'")
        if "session_state" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN session_state TEXT DEFAULT 'cold'")
        if "last_used_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN last_used_at DATETIME")
        if "created_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN created_at DATETIME")
        if "updated_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE workspace_tabs ADD COLUMN updated_at DATETIME")


def _ensure_workspace_tab_backfill():
    with engine.begin() as connection:
        table_exists = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_tabs'"
        ).fetchone()
        if not table_exists:
            return

        workspaces = connection.exec_driver_sql(
            """
            SELECT
                id,
                context_summary,
                active_message_tokens,
                codex_session_id,
                claude_session_id,
                cursor_session_id,
                last_model,
                last_runtime,
                last_request_text,
                last_request_model,
                last_request_agent_mode,
                last_request_attachments,
                session_state,
                last_used_at,
                created_at
            FROM workspaces
            ORDER BY id ASC
            """
        ).fetchall()

        for row in workspaces:
            workspace_id = int(row[0])
            existing_tab_id = connection.exec_driver_sql(
                "SELECT id FROM workspace_tabs WHERE workspace_id = ? ORDER BY archived_at IS NOT NULL ASC, sort_order ASC, id ASC LIMIT 1",
                (workspace_id,),
            ).scalar()
            if existing_tab_id is None:
                connection.exec_driver_sql(
                    """
                    INSERT INTO workspace_tabs (
                        workspace_id,
                        title,
                        sort_order,
                        archived_at,
                        context_summary,
                        active_message_tokens,
                        codex_session_id,
                        claude_session_id,
                        cursor_session_id,
                        last_model,
                        last_runtime,
                        last_request_text,
                        last_request_model,
                        last_request_agent_mode,
                        last_request_attachments,
                        session_state,
                        last_used_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_id,
                        "New Tab",
                        0,
                        None,
                        row[1] or "",
                        int(row[2] or 0),
                        row[3] or "",
                        row[4] or "",
                        row[5] or "",
                        row[6] or "",
                        row[7] or "",
                        row[8] or "",
                        row[9] or "",
                        row[10] or "",
                        row[11] or "[]",
                        row[12] or "cold",
                        row[13],
                        row[14],
                        row[13] or row[14],
                    ),
                )
                existing_tab_id = connection.exec_driver_sql("SELECT last_insert_rowid()").scalar()

            if existing_tab_id is not None:
                connection.exec_driver_sql(
                    "UPDATE messages SET tab_id = ? WHERE workspace_id = ? AND tab_id IS NULL",
                    (int(existing_tab_id), workspace_id),
                )


def _ensure_memory_entry_columns():
    with engine.begin() as connection:
        table_exists = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_entries'"
        ).fetchone()
        if not table_exists:
            return

        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(memory_entries)").fetchall()
        }
        if "kind" not in columns:
            connection.exec_driver_sql("ALTER TABLE memory_entries ADD COLUMN kind TEXT DEFAULT 'fact'")
        if "last_accessed_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE memory_entries ADD COLUMN last_accessed_at DATETIME")


def _ensure_indexes():
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_workspaces_last_used_at_id ON workspaces (last_used_at, id)",
        "CREATE INDEX IF NOT EXISTS ix_workspace_tabs_workspace_id_sort_order_id ON workspace_tabs (workspace_id, sort_order, id)",
        "CREATE INDEX IF NOT EXISTS ix_workspace_tabs_workspace_id_archived_at_id ON workspace_tabs (workspace_id, archived_at, id)",
        "CREATE INDEX IF NOT EXISTS ix_workspace_tabs_last_used_at_id ON workspace_tabs (last_used_at, id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_workspace_id_id ON messages (workspace_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_workspace_id_created_at ON messages (workspace_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_messages_tab_id_id ON messages (tab_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_tab_id_created_at ON messages (tab_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_memory_entries_workspace_id_tab_id_created_at ON memory_entries (workspace_id, tab_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_memory_entries_workspace_id_tab_id_bucket ON memory_entries (workspace_id, tab_id, bucket)",
        "CREATE INDEX IF NOT EXISTS ix_memory_entries_expires_at ON memory_entries (expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_router_telemetry_workspace_id_created_at ON router_telemetry (workspace_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_router_telemetry_created_at ON router_telemetry (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_code_reviews_workspace_id_created_at ON code_reviews (workspace_id, created_at)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)

def init_db():
    global engine
    db_url = f"sqlite:///{get_db_path()}"

    if engine is None or str(engine.url) != db_url:
        engine = create_engine(db_url)
        SessionLocal.configure(bind=engine)

    Base.metadata.create_all(engine)
    _ensure_workspace_columns()
    _ensure_message_columns()
    _ensure_workspace_tab_columns()
    _ensure_workspace_tab_backfill()
    _ensure_memory_entry_columns()
    _ensure_indexes()
