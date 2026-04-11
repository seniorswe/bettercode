from bettercode.context import Message, SessionLocal, Workspace, init_db, manage_workspace_context


def test_manage_workspace_context_squashes_older_messages(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.context.tokens.squash_workspace_context", lambda previous, transcript: "Compressed context")
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        for index in range(12):
            db.add(Message(workspace_id=workspace.id, role="user", content=f"message {index} " * 80))
        db.commit()

        changed = manage_workspace_context(db, workspace, max_tokens=40, keep_recent_messages=4)

        remaining = db.query(Message).filter_by(workspace_id=workspace.id).order_by(Message.created_at.asc()).all()
        db.refresh(workspace)

    assert changed is True
    assert workspace.context_summary == "Compressed context"
    assert len(remaining) == 4


def test_manage_workspace_context_skips_when_under_limit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with SessionLocal() as db:
        workspace = Workspace(name="demo", path=str(tmp_path))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        db.add(Message(workspace_id=workspace.id, role="user", content="small message"))
        db.commit()

        changed = manage_workspace_context(db, workspace, max_tokens=1000)

    assert changed is False
