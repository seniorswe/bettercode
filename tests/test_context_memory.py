from datetime import UTC, datetime, timedelta

from bettercode.context import (
    SessionLocal,
    Workspace,
    WorkspaceTab,
    build_memory_context_block,
    clear_memory_entries,
    init_db,
    list_memory_entries,
    retrieve_memory_entries,
    upsert_memory_entries,
)
from bettercode.context.state import MemoryEntry


def test_list_memory_entries_prunes_expired_medium_memory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        tab = WorkspaceTab(workspace_id=workspace.id, title="Chat")
        db.add(tab)
        db.commit()
        db.refresh(tab)

        db.add(
            MemoryEntry(
                workspace_id=workspace.id,
                tab_id=tab.id,
                bucket="medium",
                content="Temporary task detail",
                normalized_content="temporary task detail",
                created_at=datetime.now(UTC) - timedelta(hours=49),
                updated_at=datetime.now(UTC) - timedelta(hours=49),
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.add(
            MemoryEntry(
                workspace_id=workspace.id,
                tab_id=tab.id,
                bucket="long",
                content="User prefers concise answers.",
                normalized_content="user prefers concise answers",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                expires_at=None,
            )
        )
        db.commit()

        entries = list_memory_entries(db, workspace, tab)
        remaining = db.query(MemoryEntry).filter_by(workspace_id=workspace.id, tab_id=tab.id).all()

    assert len(entries) == 1
    assert entries[0].bucket == "long"
    assert len(remaining) == 1


def test_upsert_memory_entries_upgrades_bucket_and_builds_context(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        tab = WorkspaceTab(workspace_id=workspace.id, title="Chat")
        db.add(tab)
        db.commit()
        db.refresh(tab)

        upsert_memory_entries(
            db,
            workspace,
            tab,
            [{"bucket": "short", "content": "Working in bettercode/web/api.py."}],
            source="test",
        )
        upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "long", "content": "Working in bettercode/web/api.py."},
                {"bucket": "medium", "content": "Current task is adding chat memory."},
            ],
            source="test",
        )
        db.commit()

        entries = list_memory_entries(db, workspace, tab)
        context_block = build_memory_context_block(db, workspace, tab, request_text="Continue memory work in bettercode/web/api.py.")

    assert len(entries) == 2
    assert any(entry.bucket == "long" and "bettercode/web/api.py" in entry.content for entry in entries)
    assert any(entry.kind == "project" for entry in entries)
    assert "Relevant memory for this turn:" in context_block
    assert "[long/project]" in context_block
    assert "Current task is adding chat memory." in context_block


def test_clear_memory_entries_can_target_short_bucket(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        tab = WorkspaceTab(workspace_id=workspace.id, title="Chat")
        db.add(tab)
        db.commit()
        db.refresh(tab)

        upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "short", "content": "Temporary debugging target is selector.py."},
                {"bucket": "long", "content": "User prefers direct, simple answers."},
            ],
            source="test",
        )
        db.commit()

        deleted = clear_memory_entries(db, workspace, tab, "short")
        db.commit()
        entries = list_memory_entries(db, workspace, tab)

    assert deleted == 1
    assert len(entries) == 1
    assert entries[0].bucket == "long"


def test_retrieve_memory_entries_prefers_relevant_project_and_preference_memory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        tab = WorkspaceTab(workspace_id=workspace.id, title="Chat")
        db.add(tab)
        db.commit()
        db.refresh(tab)

        upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "long", "kind": "preference", "content": "User prefers direct, simple answers."},
                {"bucket": "medium", "kind": "project", "content": "Current focus is bettercode/web/api.py memory retrieval."},
                {"bucket": "medium", "kind": "fact", "content": "The weather was discussed once."},
            ],
            source="test",
        )
        db.commit()

        retrieved = retrieve_memory_entries(
            db,
            workspace,
            tab,
            request_text="Update memory retrieval in bettercode/web/api.py.",
            limit=2,
        )

    assert len(retrieved) == 2
    assert any(entry.kind == "preference" for entry in retrieved)
    assert any("bettercode/web/api.py" in entry.content for entry in retrieved)
