import asyncio
import hashlib
import subprocess
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bettercode.web.api as web_api
import bettercode.web.telemetry as web_telemetry
from bettercode.router import selector as selector_module
from bettercode.context.state import Message, SessionLocal, init_db
from bettercode.web.api import (
    ChatAttachment,
    _model_options,
    _require_selector_for_app_startup,
    _ensure_default_workspace,
    archive_workspace_tab_payload,
    chat_payload,
    clear_memory_payload,
    choose_workspace_payload,
    create_workspace_tab_payload,
    create_current_workspace_payload,
    create_workspace_folder_payload,
    create_workspace_payload,
    create_app,
    delete_workspace_payload,
    git_commit_payload,
    git_stage_files_payload,
    git_status_payload,
    git_unstage_files_payload,
    git_update_payload,
    get_messages_payload,
    list_workspaces_payload,
    memory_payload,
    pick_workspace_path_payload,
    refresh_model_options_payload,
    rename_workspace_payload,
    reset_workspace_session_payload,
    restore_workspace_tab_payload,
    review_files_payload,
)


def _completed(args, stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


async def _read_streaming_response(response):
    chunks = []
    underlying_iterator = (
        getattr(getattr(response, "body_iterator", None), "ag_frame", None)
        and response.body_iterator.ag_frame.f_locals.get("iterator")
    )
    if underlying_iterator is not None:
        for chunk in underlying_iterator:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.fixture(autouse=True)
def _selector_runtime_ready(monkeypatch):
    with web_api.GIT_STATUS_CACHE_LOCK:
        web_api.GIT_STATUS_CACHE.clear()
    with web_api.RECENT_FILE_ENTRIES_CACHE_LOCK:
        web_api.RECENT_FILE_ENTRIES_CACHE.clear()
    monkeypatch.setattr(
        web_api,
        "require_selector_runtime",
        lambda **kwargs: {
            "installed": True,
            "running": True,
            "model": "qwen2.5-coder:1.5b",
            "model_ready": True,
        },
    )
    yield
    with web_api.ACTIVE_RUN_PROCESSES_LOCK:
        web_api.ACTIVE_RUN_PROCESSES.clear()
    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES.clear()
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META.clear()
    with web_api.PENDING_CHAT_INPUT_LOCK:
        web_api.PENDING_CHAT_INPUT.clear()
    with web_api.ORCHESTRATED_CHAT_LOCK:
        web_api.ORCHESTRATED_CHAT_PROCESSES.clear()
        web_api.ORCHESTRATED_CHAT_META.clear()
    with web_api.RUNTIME_JOBS_LOCK:
        web_api.RUNTIME_JOBS.clear()
    selector_module._MANAGED_OLLAMA_PROCESS = None


def test_workspaces_include_current_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    payload = list_workspaces_payload()

    assert payload["workspaces"]
    assert payload["workspaces"][0]["path"] == str(tmp_path)


def test_emit_status_event_separates_status_and_transcript():
    activity_log = []
    history_log = []

    payload = json.loads(
        web_api._emit_status_event(
            activity_log,
            history_log,
            message="Running shell command: rg",
            transcript='{"type":"item.started","item":{"type":"command","command":["rg"]}}',
            terminal="[start] $ rg",
        ).decode("utf-8")
    )

    assert activity_log == ["Running shell command: rg"]
    assert history_log == ['{"type":"item.started","item":{"type":"command","command":["rg"]}}']
    assert payload["message"] == "Running shell command: rg"
    assert payload["transcript"] == '{"type":"item.started","item":{"type":"command","command":["rg"]}}'
    assert payload["terminal"] == "[start] $ rg"


def test_emit_status_event_does_not_copy_status_into_history_without_transcript():
    activity_log = []
    history_log = []

    payload = json.loads(
        web_api._emit_status_event(activity_log, history_log, message="The local router is pre-processing the request.").decode("utf-8")
    )

    assert activity_log == ["The local router is pre-processing the request."]
    assert history_log == []
    assert payload["message"] == "The local router is pre-processing the request."
    assert payload["transcript"] == ""
    assert payload["terminal"] == ""


def test_create_current_workspace_payload_uses_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    payload = create_current_workspace_payload()

    assert payload["workspace"]["path"] == str(tmp_path)


def test_choose_workspace_payload_uses_native_picker(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    chosen = tmp_path / "project"
    chosen.mkdir()

    payload = choose_workspace_payload(lambda: str(chosen))

    assert payload["cancelled"] is False
    assert payload["workspace"]["path"] == str(chosen)


def test_pick_workspace_path_payload_returns_path_without_creating_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    chosen = tmp_path / "project"
    chosen.mkdir()

    payload = pick_workspace_path_payload(lambda: str(chosen))

    assert payload["cancelled"] is False
    assert payload["path"] == str(chosen)
    assert list_workspaces_payload()["workspaces"] == []


def test_create_workspace_folder_payload_creates_directory_and_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    parent = tmp_path / "projects"
    parent.mkdir()

    payload = create_workspace_folder_payload(str(parent), "platform")

    assert (parent / "platform").is_dir()
    assert payload["workspace"]["path"] == str(parent / "platform")


def test_create_workspace_folder_payload_rejects_traversal_name(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    parent = tmp_path / "projects"
    parent.mkdir()

    with pytest.raises(web_api.HTTPException) as exc_info:
        create_workspace_folder_payload(str(parent), "../escape")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Project name must be a single directory name."
    assert not (tmp_path / "escape").exists()


def test_create_workspace_payload_includes_default_tab(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    project = tmp_path / "project"
    project.mkdir()

    payload = create_workspace_payload(str(project))

    assert payload["workspace"]["tabs"]
    assert payload["workspace"]["tabs"][0]["title"] == "New Tab"
    assert payload["workspace"]["tab_history"] == []


def test_get_messages_payload_isolated_by_tab(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    project = tmp_path / "project"
    project.mkdir()

    workspace_payload = create_workspace_payload(str(project))
    workspace_id = workspace_payload["workspace"]["id"]
    first_tab_id = workspace_payload["workspace"]["tabs"][0]["id"]
    second_tab_id = create_workspace_tab_payload(workspace_id)["tab"]["id"]

    with SessionLocal() as db:
        db.add(Message(workspace_id=workspace_id, tab_id=first_tab_id, role="user", content="tab one"))
        db.add(Message(workspace_id=workspace_id, tab_id=second_tab_id, role="assistant", content="tab two"))
        db.commit()

    payload = get_messages_payload(workspace_id, tab_id=first_tab_id)

    assert payload["tab"]["id"] == first_tab_id
    assert [message["content"] for message in payload["messages"]] == ["tab one"]


def test_archive_and_restore_workspace_tab_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    project = tmp_path / "project"
    project.mkdir()

    workspace_payload = create_workspace_payload(str(project))
    workspace_id = workspace_payload["workspace"]["id"]
    first_tab_id = workspace_payload["workspace"]["tabs"][0]["id"]
    archived_tab_id = create_workspace_tab_payload(workspace_id)["tab"]["id"]

    archived = archive_workspace_tab_payload(workspace_id, archived_tab_id)

    assert archived["next_tab_id"] == first_tab_id
    assert any(tab["id"] == archived_tab_id for tab in archived["workspace"]["tab_history"])

    restored = restore_workspace_tab_payload(workspace_id, archived_tab_id)

    assert any(tab["id"] == archived_tab_id for tab in restored["workspace"]["tabs"])
    assert all(tab["id"] != archived_tab_id for tab in restored["workspace"]["tab_history"])


def test_rename_workspace_payload_updates_name(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = rename_workspace_payload(workspace_id, "Platform")

    assert payload["workspace"]["name"] == "Platform"


def test_app_settings_payload_includes_auto_model_select_preferences(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(
        max_cost_tier="medium",
        auto_model_preference="faster",
        enable_task_breakdown=False,
        enable_follow_up_suggestions=False,
        performance_profile="balanced",
    )
    payload = web_api.app_settings_payload()

    assert payload["settings"] == {
        "performance_profile": "balanced",
        "max_cost_tier": "medium",
        "auto_model_preference": "faster",
        "enable_task_breakdown": False,
        "enable_follow_up_suggestions": False,
        "local_preprocess_mode": "off",
        "local_preprocess_model": None,
        "font_size": "medium",
        "human_language": "en",
    }


def test_app_settings_performance_profile_fast_applies_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(performance_profile="fast")
    payload = web_api.app_settings_payload()

    assert payload["settings"] == {
        "performance_profile": "fast",
        "max_cost_tier": None,
        "auto_model_preference": "faster",
        "enable_task_breakdown": False,
        "enable_follow_up_suggestions": False,
        "local_preprocess_mode": "off",
        "local_preprocess_model": None,
        "font_size": "medium",
        "human_language": "en",
    }


def test_app_settings_explicit_overrides_win_over_performance_profile(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(
        performance_profile="fast",
        auto_model_preference="smarter",
        enable_task_breakdown=True,
        enable_follow_up_suggestions=True,
    )
    payload = web_api.app_settings_payload()

    assert payload["settings"] == {
        "performance_profile": "fast",
        "max_cost_tier": None,
        "auto_model_preference": "smarter",
        "enable_task_breakdown": True,
        "enable_follow_up_suggestions": True,
        "local_preprocess_mode": "off",
        "local_preprocess_model": None,
        "font_size": "medium",
        "human_language": "en",
    }


def test_changing_performance_profile_resets_derived_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(
        performance_profile="fast",
        auto_model_preference="smarter",
        enable_task_breakdown=True,
        enable_follow_up_suggestions=True,
    )
    web_api.set_app_settings(performance_profile="balanced")
    payload = web_api.app_settings_payload()

    assert payload["settings"] == {
        "performance_profile": "balanced",
        "max_cost_tier": None,
        "auto_model_preference": "balanced",
        "enable_task_breakdown": True,
        "enable_follow_up_suggestions": True,
        "local_preprocess_mode": "off",
        "local_preprocess_model": None,
        "font_size": "medium",
        "human_language": "en",
    }


def test_app_settings_support_local_preprocess_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(local_preprocess_mode="small", local_preprocess_model="qwen2.5-coder:3b")
    payload = web_api.app_settings_payload()

    assert payload["settings"]["local_preprocess_mode"] == "small"
    assert payload["settings"]["local_preprocess_model"] == "qwen2.5-coder:3b"


def test_app_settings_local_model_alone_enables_local_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(local_preprocess_model="qwen2.5-coder:3b")
    payload = web_api.app_settings_payload()

    assert payload["settings"]["local_preprocess_mode"] == "small"
    assert payload["settings"]["local_preprocess_model"] == "qwen2.5-coder:3b"


def test_app_settings_support_font_size_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(font_size="large")
    payload = web_api.app_settings_payload()

    assert payload["settings"]["font_size"] == "large"


def test_app_settings_support_human_language_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()

    web_api.set_app_settings(human_language="ko")
    payload = web_api.app_settings_payload()

    assert payload["settings"]["human_language"] == "ko"


def test_build_prompt_text_includes_human_language_instruction():
    prompt = web_api._build_prompt_text("Fix the bug.", [], human_language="ja")

    assert "Japanese" in prompt


def test_install_selector_model_payload_installs_curated_local_model(monkeypatch):
    installed = []
    monkeypatch.setattr(
        web_api,
        "installable_local_preprocess_model",
        lambda model_id, mode="small": {"id": model_id, "installed": False, "source": "catalog"},
    )
    monkeypatch.setattr(web_api, "pull_local_preprocess_model", lambda model_id: installed.append(model_id))
    monkeypatch.setattr(web_api, "selector_status", lambda: {"available_local_models": [{"id": "qwen2.5-coder:1.5b", "installed": True}]})

    payload = web_api.install_selector_model_payload("qwen2.5-coder:1.5b")

    assert installed == ["qwen2.5-coder:1.5b"]
    assert payload["ok"] is True
    assert payload["selector"]["available_local_models"][0]["installed"] is True


def test_install_selector_model_route_rejects_unknown_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    monkeypatch.setattr(web_api, "installable_local_preprocess_model", lambda model_id, mode="small": None)
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/selector/models/install", json={"model_id": "unknown:model"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported local preprocess model."


def test_app_settings_route_partial_update_only_changes_requested_fields(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()
    web_api.set_app_settings(
        performance_profile="full",
        max_cost_tier="medium",
        auto_model_preference="smarter",
        enable_task_breakdown=True,
        enable_follow_up_suggestions=True,
        local_preprocess_mode="small",
        local_preprocess_model="qwen2.5-coder:3b",
    )
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/app/settings", json={"performance_profile": "fast"})

    assert response.status_code == 200
    assert response.json()["settings"] == {
        "performance_profile": "fast",
        "max_cost_tier": "medium",
        "auto_model_preference": "faster",
        "enable_task_breakdown": False,
        "enable_follow_up_suggestions": False,
        "local_preprocess_mode": "small",
        "local_preprocess_model": "qwen2.5-coder:3b",
        "font_size": "medium",
        "human_language": "en",
    }


def test_app_settings_route_updates_font_size(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/app/settings", json={"font_size": "large"})

    assert response.status_code == 200
    assert response.json()["settings"]["font_size"] == "large"


def test_serialize_workspace_marks_saved_context_without_native_session(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        workspace.context_summary = "Keep using the existing API shape."
        workspace.last_runtime = "gemini"
        db.commit()
        payload = web_api._serialize_workspace(workspace)

    assert payload["has_session"] is False
    assert payload["has_context"] is True
    assert payload["last_runtime"] == "gemini"


def test_delete_workspace_payload_removes_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = delete_workspace_payload(workspace_id)

    assert payload["deleted"] is True
    assert list_workspaces_payload()["workspaces"] == []


def test_create_workspace_payload_makes_duplicate_names_unique(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    first = tmp_path / "api"
    second = tmp_path / "nested" / "api"
    first.mkdir()
    second.mkdir(parents=True)

    create_workspace_payload(str(first))
    create_workspace_payload(str(second))
    names = [workspace["name"] for workspace in list_workspaces_payload()["workspaces"]]

    assert "api" in names
    assert "api 2" in names


def test_git_status_payload_parses_repo_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]

    def fake_run_git(workspace_path, args, check=True):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(
                args,
                stdout=(
                    "# branch.head main\n"
                    "# branch.ab +2 -1\n"
                    "1 M. N... 100644 100644 100644 abc abc file1.py\n"
                    "1 .M N... 100644 100644 100644 abc abc file2.py\n"
                    "? file3.py\n"
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    payload = git_status_payload(workspace_id)

    assert payload["git"]["is_repo"] is True
    assert payload["git"]["branch"] == "main"
    assert payload["git"]["ahead"] == 2
    assert payload["git"]["behind"] == 1
    assert len(payload["git"]["staged"]) == 1
    assert len(payload["git"]["changed"]) == 2
    assert len(payload["git"]["untracked"]) == 1


def test_review_files_payload_returns_changed_and_recent_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]

    changed_file = tmp_path / "app.py"
    changed_file.write_text("print('changed')\n", encoding="utf-8")
    recent_file = tmp_path / "README.md"
    recent_file.write_text("# hello\n", encoding="utf-8")

    def fake_run_git(workspace_path, args, check=True):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(
                args,
                stdout=(
                    "# branch.head main\n"
                    "# branch.ab +0 -0\n"
                    "1 .M N... 100644 100644 100644 abc abc app.py\n"
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    payload = review_files_payload(workspace_id)

    assert payload["git"]["is_repo"] is True
    assert payload["git"]["branch"] == "main"
    assert payload["changed_files"] == [{
        "path": "app.py",
        "status": "modified",
        "git_status": ".M",
        "source_label": "modified",
    }]
    assert payload["recent_files"][0]["path"] == "README.md"
    assert payload["recent_files"][0]["modified_at"]


def test_parse_git_status_uses_short_lived_cache(monkeypatch, tmp_path):
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(tuple(args))
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(
                args,
                stdout=(
                    "# branch.head main\n"
                    "# branch.ab +0 -0\n"
                    "1 .M N... 100644 100644 100644 abc abc app.py\n"
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    first = web_api._parse_git_status(str(tmp_path))
    second = web_api._parse_git_status(str(tmp_path))

    assert first["branch"] == "main"
    assert second["branch"] == "main"
    assert calls == [
        ("rev-parse", "--show-toplevel"),
        ("status", "--porcelain=2", "--branch"),
    ]

    web_api._invalidate_workspace_caches(str(tmp_path))
    web_api._parse_git_status(str(tmp_path))
    assert calls == [
        ("rev-parse", "--show-toplevel"),
        ("status", "--porcelain=2", "--branch"),
        ("rev-parse", "--show-toplevel"),
        ("status", "--porcelain=2", "--branch"),
    ]


def test_parse_git_status_preserves_paths_with_spaces_and_renames(monkeypatch, tmp_path):
    def fake_run_git(workspace_path, args, check=True):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(
                args,
                stdout=(
                    "# branch.head main\n"
                    "# branch.ab +0 -0\n"
                    "1 .M N... 100644 100644 100644 abc abc dir/file with spaces.py\n"
                    "2 R. N... 100644 100644 100644 abc abc R100 new name.py\told name.py\n"
                    "? \"docs/user guide.md\"\n"
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    payload = web_api._parse_git_status(str(tmp_path))

    assert payload["changed"][0]["path"] == "dir/file with spaces.py"
    assert payload["staged"][0]["path"] == "new name.py"
    assert payload["changed"][1]["path"] == "docs/user guide.md"
    assert payload["untracked"][0]["path"] == "docs/user guide.md"


def test_review_files_payload_reuses_recent_file_scan_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]

    (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
    walk_calls = {"count": 0}
    original_walk = web_api.os.walk

    def counting_walk(*args, **kwargs):
        walk_calls["count"] += 1
        yield from original_walk(*args, **kwargs)

    def fake_run_git(workspace_path, args, check=True):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api.os.walk", counting_walk)
    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    first = review_files_payload(workspace_id)
    second = review_files_payload(workspace_id)

    assert first["recent_files"][0]["path"] == "README.md"
    assert second["recent_files"][0]["path"] == "README.md"
    assert walk_calls["count"] == 1


def test_git_commit_payload_runs_commit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["commit", "-m", "Ship it"]:
            return _completed(args, stdout="[main abc123] Ship it\n")
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    payload = git_commit_payload(workspace_id, "Ship it")

    assert payload["output"] == "[main abc123] Ship it"
    assert ["commit", "-m", "Ship it"] in calls


def test_git_stage_files_payload_runs_add_for_selected_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["add", "--", "file1.py", "dir/file2.py"]:
            return _completed(args)
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    git_stage_files_payload(workspace_id, ["file1.py", "dir/file2.py"])

    assert ["add", "--", "file1.py", "dir/file2.py"] in calls


def test_git_unstage_files_payload_runs_reset_for_selected_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["rev-parse", "--verify", "HEAD"]:
            return _completed(args, stdout="abc123\n")
        if args == ["reset", "HEAD", "--", "file1.py"]:
            return _completed(args)
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    git_unstage_files_payload(workspace_id, ["file1.py"])

    assert ["reset", "HEAD", "--", "file1.py"] in calls


def test_git_unstage_files_payload_uses_rm_without_head(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["rev-parse", "--verify", "HEAD"]:
            return _completed(args, returncode=128, stderr="fatal: ambiguous argument 'HEAD'\n")
        if args == ["rm", "--cached", "-r", "--", "file1.py"]:
            return _completed(args)
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    git_unstage_files_payload(workspace_id, ["file1.py"])

    assert ["rm", "--cached", "-r", "--", "file1.py"] in calls


def test_git_unstage_all_payload_uses_rm_without_head(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["rev-parse", "--verify", "HEAD"]:
            return _completed(args, returncode=128, stderr="fatal: ambiguous argument 'HEAD'\n")
        if args == ["rm", "--cached", "-r", "--", "."]:
            return _completed(args)
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    web_api.git_unstage_all_payload(workspace_id)

    assert ["rm", "--cached", "-r", "--", "."] in calls


def test_git_update_payload_runs_fetch_then_pull(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    calls = []

    def fake_run_git(workspace_path, args, check=True):
        calls.append(args)
        if args == ["fetch", "--all", "--prune"]:
            return _completed(args, stdout="fetch ok\n")
        if args == ["pull", "--ff-only"]:
            return _completed(args, stdout="pull ok\n")
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(args, stdout="# branch.head main\n# branch.ab +0 -0\n")
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)

    payload = git_update_payload(workspace_id)

    assert payload["output"] == "fetch ok\npull ok"
    assert calls[:2] == [["fetch", "--all", "--prune"], ["pull", "--ff-only"]]


def test_chat_endpoint_persists_messages(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", None)
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", None)
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr(
        "bettercode.web.api._run_workspace_chat_cli",
        lambda workspace, tab, prompt_text, selected_model, agent_mode=None: {
            "reply": "stubbed answer",
            "model": "codex/default",
            "runtime": "codex",
        },
    )
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(workspace_id, "Build a parser")

    assert payload["model"] == "codex/default"
    assert payload["runtime"] == "codex"
    assert payload["message"]["content"] == "stubbed answer"
    assert payload["message"]["routing_meta"]["selector"] == "heuristic"

    messages = get_messages_payload(workspace_id)["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]

    with web_api.SessionLocal() as db:
        telemetry = db.query(web_api.RouterTelemetry).all()
        assert len(telemetry) == 1
        assert telemetry[0].model_id == "codex/default"
        assert telemetry[0].success == 1


def test_chat_payload_supports_direct_model_selection_and_attachments(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    captured = {}
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        captured["workspace_path"] = workspace.path
        captured["prompt_text"] = prompt_text
        captured["selected_model"] = selected_model
        return {"reply": "attached answer", "model": "codex/gpt-5", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(
        workspace_id,
        "Review this file",
        "codex/gpt-5",
        [ChatAttachment(name="app.py", content="print('hi')")],
    )

    assert payload["model"] == "codex/gpt-5"
    assert captured["selected_model"] == "codex/gpt-5"
    assert "Attached file context:" in captured["prompt_text"]
    assert "File: app.py" in captured["prompt_text"]

    messages = get_messages_payload(workspace_id)["messages"]
    assert messages[0]["content"] == "Review this file\n\nAttached files: app.py"


def test_chat_payload_skips_local_preprocessing_for_manual_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._selector_preprocess_turn", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selector should not run")))
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        captured["selected_model"] = selected_model
        return {"reply": "manual answer", "model": "codex/gpt-5", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(workspace_id, "Use the selected model", "codex/gpt-5")

    assert payload["model"] == "codex/gpt-5"
    assert captured["selected_model"] == "codex/gpt-5"
    assert payload["message"]["routing_meta"]["selector"] == "manual"
    assert payload["message"]["routing_meta"]["reason"] == "Model selected directly."


def test_chat_payload_skips_follow_up_suggestions_when_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {
            "id": "codex/gpt-5",
            "label": "GPT-5",
            "agent_modes": ["plan", "auto_edit", "full_agentic"],
            "default_agent_mode": "full_agentic",
        },
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api.suggest_follow_up_recommendations", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recommendations should not run")))
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr(
        "bettercode.web.api._run_workspace_chat_cli",
        lambda workspace, tab, prompt_text, selected_model, agent_mode=None: {
            "reply": "manual answer",
            "model": "codex/gpt-5",
            "runtime": "codex",
        },
    )
    init_db()
    web_api.set_app_settings(None, "balanced", enable_follow_up_suggestions=False)
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(workspace_id, "Use the selected model", "codex/gpt-5")

    assert payload["message"]["recommendations"] == []


def test_chat_payload_defers_postprocess_work(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {
            "id": "codex/gpt-5",
            "label": "GPT-5",
            "agent_modes": ["plan", "auto_edit", "full_agentic"],
            "default_agent_mode": "full_agentic",
        },
    ])
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr(
        "bettercode.web.api._run_workspace_chat_cli",
        lambda workspace, tab, prompt_text, selected_model, agent_mode=None: {
            "reply": "manual answer",
            "model": "codex/gpt-5",
            "runtime": "codex",
        },
    )
    monkeypatch.setattr(
        "bettercode.web.api.suggest_follow_up_recommendations",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("postprocess should be async")),
    )
    started = {}
    monkeypatch.setattr(
        "bettercode.web.api._start_turn_postprocess",
        lambda message_id, workspace_id, tab_id, request_text, reply_text, change_log: started.update({
            "message_id": message_id,
            "workspace_id": workspace_id,
            "tab_id": tab_id,
            "request_text": request_text,
            "reply_text": reply_text,
            "change_log": change_log,
        }),
    )
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(workspace_id, "Use the selected model", "codex/gpt-5")

    assert payload["message"]["recommendations"] == []
    assert started["workspace_id"] == workspace_id
    assert started["request_text"] == "Use the selected model"
    assert started["reply_text"] == "manual answer"


def test_chat_payload_emits_telemetry_events(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr(
        "bettercode.web.api._run_workspace_chat_cli",
        lambda workspace, tab, prompt_text, selected_model, agent_mode=None: {
            "reply": "manual answer",
            "model": "codex/gpt-5",
            "runtime": "codex",
        },
    )
    events = []
    monkeypatch.setattr("bettercode.web.api.log_event", lambda event, **fields: events.append((event, fields)))
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    chat_payload(workspace_id, "Use the selected model", "codex/gpt-5")

    turn_events = [event for event in events if event[0].startswith("chat_turn_")]
    assert [event[0] for event in turn_events] == ["chat_turn_started", "chat_turn_completed"]
    assert turn_events[0][1]["stream"] is False
    assert turn_events[1][1]["runtime"] == "codex"


def test_parse_git_status_emits_observability_event(monkeypatch, tmp_path):
    events = []

    def fake_run_git(workspace_path, args, check=True):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, stdout=f"{workspace_path}\n")
        if args == ["status", "--porcelain=2", "--branch"]:
            return _completed(
                args,
                stdout=(
                    "# branch.head main\n"
                    "# branch.ab +0 -0\n"
                    "1 .M N... 100644 100644 100644 abc abc app.py\n"
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("bettercode.web.api._run_git", fake_run_git)
    monkeypatch.setattr("bettercode.web.api.log_event", lambda event, **fields: events.append((event, fields)))

    payload = web_api._parse_git_status(str(tmp_path))

    assert payload["branch"] == "main"
    assert events[-1][0] == "git_status_scanned"
    assert events[-1][1]["cache_hit"] is False
    assert events[-1][1]["changed_count"] == 1


def test_chat_status_payload_reports_stalled_process(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    workspace = list_workspaces_payload()["workspaces"][0]
    tab_id = workspace["tabs"][0]["id"]

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES[tab_id] = FakeProcess()
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META[tab_id] = {
            "started_at": 10.0,
            "last_output_at": 10.0,
            "input_waiting": False,
            "stop_requested": False,
            "runtime": "codex",
            "pid": 1234,
        }
    monkeypatch.setattr("bettercode.web.api.time.monotonic", lambda: 10.0 + web_api.CHAT_STALL_WARNING_SECONDS + 2.0)

    payload = web_api.chat_status_payload(workspace["id"])

    assert payload["chat"]["active"] is True
    assert payload["chat"]["stalled"] is True
    assert payload["chat"]["idle_seconds"] >= web_api.CHAT_STALL_WARNING_SECONDS

    web_api._clear_active_chat_process(tab_id)


def test_stop_chat_payload_kills_process_and_unblocks_pending_input(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    workspace = list_workspaces_payload()["workspaces"][0]
    tab_id = workspace["tabs"][0]["id"]

    class FakeProcess:
        pid = 321

        def poll(self):
            return None

    stopped = {}
    web_api._clear_active_chat_process(tab_id)
    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES[tab_id] = FakeProcess()
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META[tab_id] = {
            "started_at": 1.0,
            "last_output_at": 1.0,
            "input_waiting": True,
            "stop_requested": False,
            "runtime": "claude",
            "pid": 321,
        }
    with web_api.PENDING_CHAT_INPUT_LOCK:
        pending = web_api.queue.Queue()
        web_api.PENDING_CHAT_INPUT[tab_id] = pending

    original_kill = web_api._kill_process_tree
    try:
        web_api._kill_process_tree = lambda process: stopped.setdefault("pid", process.pid)
        payload = web_api.stop_chat_payload(workspace["id"])
    finally:
        web_api._kill_process_tree = original_kill

    assert payload == {"stopped": True, "already_finished": False}
    assert stopped["pid"] == 321


def test_stop_chat_payload_is_idempotent_when_process_already_finished(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    workspace = list_workspaces_payload()["workspaces"][0]
    tab_id = workspace["tabs"][0]["id"]

    class FakeProcess:
        pid = 654

        def poll(self):
            return 0

    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES[tab_id] = FakeProcess()
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META[tab_id] = {"pid": 654}

    payload = web_api.stop_chat_payload(workspace["id"])

    assert payload == {"stopped": False, "already_finished": True}
    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        assert 11 not in web_api.ACTIVE_CHAT_PROCESSES


def test_sweep_active_run_processes_clears_finished_entries():
    class FakeProcess:
        def __init__(self, pid, returncode):
            self.pid = pid
            self._returncode = returncode

        def poll(self):
            return self._returncode

    with web_api.ACTIVE_RUN_PROCESSES_LOCK:
        web_api.ACTIVE_RUN_PROCESSES[3] = FakeProcess(9001, 0)
        web_api.ACTIVE_RUN_PROCESSES[4] = FakeProcess(9002, None)

    cleared = web_api._sweep_active_run_processes()

    assert cleared == [3]
    with web_api.ACTIVE_RUN_PROCESSES_LOCK:
        assert 3 not in web_api.ACTIVE_RUN_PROCESSES
        assert 4 in web_api.ACTIVE_RUN_PROCESSES


def test_run_status_payload_reports_active_process():
    class FakeProcess:
        def __init__(self, pid, returncode):
            self.pid = pid
            self._returncode = returncode

        def poll(self):
            return self._returncode

    with web_api.ACTIVE_RUN_PROCESSES_LOCK:
        web_api.ACTIVE_RUN_PROCESSES[21] = FakeProcess(9201, None)

    payload = web_api.run_status_payload(21)

    assert payload == {"active": True, "pid": 9201}


def test_run_status_payload_reports_inactive_when_missing():
    payload = web_api.run_status_payload(22)

    assert payload == {"active": False, "pid": None}


def test_sweep_inactive_chat_processes_clears_finished_entries():
    class FakeProcess:
        def __init__(self, pid, returncode):
            self.pid = pid
            self._returncode = returncode

        def poll(self):
            return self._returncode

    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES[5] = FakeProcess(9101, 0)
        web_api.ACTIVE_CHAT_PROCESSES[6] = FakeProcess(9102, None)
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META[5] = {"pid": 9101}
        web_api.ACTIVE_CHAT_PROCESS_META[6] = {"pid": 9102}

    cleared = web_api._sweep_inactive_chat_processes()

    assert cleared == [5]
    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        assert 5 not in web_api.ACTIVE_CHAT_PROCESSES
        assert 6 in web_api.ACTIVE_CHAT_PROCESSES


def test_sweep_runtime_jobs_reaps_old_finished_jobs():
    with web_api.RUNTIME_JOBS_LOCK:
        web_api.RUNTIME_JOBS["done"] = {
            "id": "done",
            "runtime": "codex",
            "action": "install",
            "status": "completed",
            "finished_at": (datetime.now(UTC) - timedelta(seconds=web_api.RUNTIME_JOB_RETENTION_SECONDS + 5)).isoformat(),
        }
        web_api.RUNTIME_JOBS["active"] = {
            "id": "active",
            "runtime": "claude",
            "action": "login",
            "status": "running",
            "finished_at": "",
        }

    cleared = web_api._sweep_runtime_jobs()

    assert cleared == ["done"]
    with web_api.RUNTIME_JOBS_LOCK:
        assert "done" not in web_api.RUNTIME_JOBS
        assert "active" in web_api.RUNTIME_JOBS


def test_clear_active_chat_process_clears_pending_input_queue():
    with web_api.PENDING_CHAT_INPUT_LOCK:
        web_api.PENDING_CHAT_INPUT[33] = web_api.queue.Queue()

    web_api._clear_active_chat_process(33)

    with web_api.PENDING_CHAT_INPUT_LOCK:
        assert 33 not in web_api.PENDING_CHAT_INPUT


def test_retry_chat_payload_reuses_last_request(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {
            "id": "codex/gpt-5",
            "label": "GPT-5",
            "agent_modes": ["plan", "auto_edit", "full_agentic"],
            "default_agent_mode": "full_agentic",
        },
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    calls = []

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        calls.append({"model": selected_model, "prompt": prompt_text, "agent_mode": agent_mode})
        return {
            "reply": "ok",
            "model": selected_model,
            "runtime": "codex",
        }

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    attachments = [web_api.ChatAttachment(name="notes.txt", content="hello")]

    web_api.chat_payload(workspace_id, "Retry me", "codex/gpt-5", attachments, agent_mode="plan")
    payload = web_api.retry_chat_payload(workspace_id)

    assert payload["model"] == "codex/gpt-5"
    assert len(calls) == 2
    assert calls[1]["model"] == "codex/gpt-5"
    assert calls[1]["agent_mode"] == "plan"
    assert "Retry me" in calls[1]["prompt"]
    assert "notes.txt" in calls[1]["prompt"]


def test_retry_chat_payload_requires_saved_request(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]

    with pytest.raises(web_api.HTTPException) as exc:
        web_api.retry_chat_payload(workspace_id)

    assert exc.value.status_code == 404


def test_restart_selector_runtime_payload_restarts_runtime(monkeypatch):
    calls = {"stopped": 0, "required": 0}

    monkeypatch.setattr("bettercode.web.api.stop_managed_ollama", lambda: calls.__setitem__("stopped", calls["stopped"] + 1))
    monkeypatch.setattr(
        "bettercode.web.api.require_selector_runtime",
        lambda **kwargs: calls.__setitem__("required", calls["required"] + 1) or {
            "installed": True,
            "running": True,
            "model": "qwen2.5-coder:1.5b",
            "model_ready": True,
        },
    )

    payload = web_api.restart_selector_runtime_payload()

    assert calls == {"stopped": 1, "required": 1}
    assert payload["selector"]["running"] is True
    assert payload["message"] == "Auto Model Select runtime restarted."


def test_app_settings_route_switches_local_preprocess_runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    web_api.set_app_settings(local_preprocess_mode="small", local_preprocess_model="qwen2.5-coder:1.5b")
    app = create_app()
    calls = []

    monkeypatch.setattr(
        web_api,
        "selector_status",
        lambda: {
            "installed": True,
            "running": True,
            "mode": "small",
            "model": selector_module.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:1.5b",
            "model_ready": True,
        },
    )
    monkeypatch.setattr(
        web_api,
        "apply_local_preprocess_runtime_change",
        lambda previous_model_id, next_mode, next_model_id, startup_timeout=10.0: calls.append(
            (previous_model_id, next_mode, next_model_id, startup_timeout)
        ) or {
            "installed": True,
            "running": True,
            "mode": next_mode,
            "model": selector_module.SELECTOR_MODEL,
            "selected_model": next_model_id,
            "model_ready": True,
        },
    )

    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "") == "/api/app/settings" and "POST" in getattr(route, "methods", set())
    )
    payload = endpoint(web_api.AppSettingsRequest(local_preprocess_model="qwen2.5-coder:3b"))

    assert payload["settings"]["local_preprocess_model"] == "qwen2.5-coder:3b"
    assert calls == [("qwen2.5-coder:1.5b", "small", "qwen2.5-coder:3b", 10.0)]


def test_app_info_includes_telemetry_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/app/info")

    assert response.status_code == 200
    telemetry = response.json()["telemetry"]
    assert telemetry["path"].endswith("telemetry.jsonl")
    assert "exists" in telemetry
    assert response.json()["languages"]["needs_setup"] is True


def test_root_page_includes_onboarding_close_button(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="onboarding-close-button"' in response.text
    assert 'aria-label="Close window"' in response.text


def test_root_page_marks_multiple_window_drag_regions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('data-window-drag-region="true"') >= 4


def test_app_info_reports_language_setup_complete_when_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setattr("bettercode.settings.detect_system_human_language", lambda: "en")
    init_db()
    web_api.set_app_settings(human_language="ja")
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/app/info")

    assert response.status_code == 200
    assert response.json()["settings"]["human_language"] == "ja"
    assert response.json()["languages"]["current"] == "ja"
    assert response.json()["languages"]["needs_setup"] is False


def test_app_info_reports_updates_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/app/info")

    assert response.status_code == 200
    assert response.json()["update"] == {
        "enabled": False,
        "source": "disabled",
        "update_available": False,
        "latest_version": None,
        "release_name": "",
        "release_url": "",
        "download_url": "",
        "asset_name": "",
        "sha256": "",
        "error": web_api.APP_UPDATES_DISABLED_MESSAGE,
    }


def test_app_update_endpoint_reports_updates_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/app/update?force=true")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "source": "disabled",
        "update_available": False,
        "latest_version": None,
        "release_name": "",
        "release_url": "",
        "download_url": "",
        "asset_name": "",
        "sha256": "",
        "error": web_api.APP_UPDATES_DISABLED_MESSAGE,
    }


def test_app_update_payload_does_not_fetch_updates_when_disabled(monkeypatch):
    monkeypatch.setattr(web_api, "check_for_updates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fetch real updates")))

    payload = web_api.app_update_payload(force_refresh=True)

    assert payload == {
        "enabled": False,
        "source": "disabled",
        "update_available": False,
        "latest_version": None,
        "release_name": "",
        "release_url": "",
        "download_url": "",
        "asset_name": "",
        "sha256": "",
        "error": web_api.APP_UPDATES_DISABLED_MESSAGE,
    }


def test_app_update_install_endpoint_returns_conflict_when_updates_are_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/app/update/install")

    assert response.status_code == 409
    assert response.json()["detail"] == web_api.APP_UPDATES_DISABLED_MESSAGE


def test_review_run_payload_rejects_paths_outside_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    workspace = tmp_path / "project"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    workspace_payload = create_workspace_payload(str(workspace))
    workspace_id = workspace_payload["workspace"]["id"]

    response = web_api.review_run_payload(workspace_id, ["../secret.txt"], "deep", "codex/default", "off")
    payload = asyncio.run(_read_streaming_response(response))

    assert '"type": "error"' in payload
    assert '"message": "File path must stay inside the workspace."' in payload


def test_app_info_includes_configured_models_when_cache_is_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    web_api._clear_model_discovery_cache()
    monkeypatch.setattr(
        "bettercode.web.api._cli_runtimes",
        lambda quick=False, force_refresh=False: {
            "codex": {"available": True, "configured": True, "version": None, "path": "/usr/bin/codex"},
            "claude": {"available": False, "configured": False, "version": None, "path": None},
            "gemini": {"available": False, "configured": False, "version": None, "path": None},
            "npm": {"available": True, "configured": False, "version": None, "path": "/usr/bin/npm"},
        },
    )
    monkeypatch.setattr(
        "bettercode.web.api._codex_cached_model_registry",
        lambda: [
            {"id": "codex/default", "label": "Codex Default"},
            {"id": "codex/gpt-5.4@medium", "label": "gpt-5.4 / Medium"},
        ],
    )
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/app/info")

    assert response.status_code == 200
    models = response.json()["models"]
    assert [model["id"] for model in models] == [
        "smart",
        "codex/gpt-5.4@medium",
    ]


def test_model_options_for_app_info_hides_internal_codex_default_from_cache(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/default", "label": "Codex Default"},
        {"id": "codex/gpt-5.4@medium", "label": "gpt-5.4 / Medium"},
    ])

    assert web_api._model_options_for_app_info() == [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5.4@medium", "label": "gpt-5.4 / Medium"},
    ]


def test_app_telemetry_endpoint_returns_recent_events(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    web_telemetry.log_event("example_event", foo="bar")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/app/telemetry?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["telemetry"]["path"].endswith("telemetry.jsonl")
    assert any(event["event"] == "example_event" and event["foo"] == "bar" for event in payload["events"])


def test_open_telemetry_log_payload_creates_and_opens_log(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    opened = {}
    monkeypatch.setattr("bettercode.web.api._open_with_system_default", lambda path: opened.setdefault("path", str(path)))

    payload = web_api.open_telemetry_log_payload()

    assert payload["opened"] is True
    assert payload["path"].endswith("telemetry.jsonl")
    assert Path(payload["path"]).exists() is True
    assert opened["path"] == payload["path"]


def test_chat_payload_includes_workspace_context_summary_in_prompt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        captured["prompt_text"] = prompt_text
        return {"reply": "summary answer", "model": "codex/gpt-5", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        workspace.context_summary = "Keep using the monorepo build pipeline."
        db.commit()
        workspace_id = workspace.id

    payload = chat_payload(workspace_id, "Continue the refactor", "codex/gpt-5")

    assert payload["model"] == "codex/gpt-5"
    assert "Workspace context summary:" in captured["prompt_text"]
    assert "Keep using the monorepo build pipeline." in captured["prompt_text"]
    assert captured["prompt_text"].endswith("Continue the refactor")


def test_chat_payload_includes_chat_memory_in_prompt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        captured["prompt_text"] = prompt_text
        return {"reply": "memory answer", "model": "codex/gpt-5", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        web_api.upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "long", "content": "User prefers direct, simple answers."},
                {"bucket": "medium", "content": "Current task is adding chat memory buckets."},
            ],
            source="test",
        )
        db.commit()
        workspace_id = workspace.id

    payload = chat_payload(workspace_id, "Continue the refactor", "codex/gpt-5")

    assert payload["model"] == "codex/gpt-5"
    assert "Relevant memory for this turn:" in captured["prompt_text"]
    assert "User prefers direct, simple answers." in captured["prompt_text"]
    assert "Current task is adding chat memory buckets." in captured["prompt_text"]


def test_build_workspace_prompt_context_includes_execution_brief_and_focus_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    monkeypatch.setattr(
        web_api,
        "_parse_git_status",
        lambda _path: {
            "changed": [{"path": "bettercode/web/api.py"}, {"path": "bettercode/router/selector.py"}],
            "staged": [],
            "untracked": [],
        },
    )

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        workspace.context_summary = "Keep the router fast and safe."
        db.add(web_api.Message(workspace_id=workspace.id, role="assistant", content="Earlier we discussed selector routing."))
        db.add(web_api.Message(workspace_id=workspace.id, role="user", content="Please improve model selection for review tasks."))
        db.commit()
        context = web_api._build_workspace_prompt_context(
            db,
            workspace,
            "Improve review routing in selector.py and api.py.",
            [],
        )

    assert "Execution brief:" in context
    assert "Focus files: bettercode/router/selector.py, bettercode/web/api.py" in context
    assert "Relevant recent conversation:" in context
    assert "Keep the router fast and safe." in context


def test_memory_review_command_updates_chat_memory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
    ])
    captured = {}

    def fake_run_local_model_response(prompt_text, model_id=None, timeout=60.0, human_language=None):
        captured["prompt_text"] = prompt_text
        return {
            "reply": json.dumps(
                {
                    "memories": [
                        {"bucket": "long", "content": "User prefers direct, simple answers."},
                        {"bucket": "medium", "content": "Current task is building chat memory."},
                    ]
                }
            ),
            "model": "local/qwen2.5-coder:1.5b",
            "runtime": "local",
            "session_id": None,
        }

    monkeypatch.setattr("bettercode.web.api.run_local_model_response", fake_run_local_model_response)
    init_db()
    _ensure_default_workspace()
    workspace_payload = list_workspaces_payload()["workspaces"][0]
    workspace_id = workspace_payload["id"]
    tab_id = workspace_payload["tabs"][0]["id"]

    with web_api.SessionLocal() as db:
        db.add(web_api.Message(workspace_id=workspace_id, tab_id=tab_id, role="user", content="Please keep replies short."))
        db.add(web_api.Message(workspace_id=workspace_id, tab_id=tab_id, role="assistant", content="I will keep them concise."))
        db.commit()

    payload = chat_payload(workspace_id, "/memory", "smart", tab_id=tab_id)

    assert payload["runtime"] == "local"
    assert "Memory updated:" in payload["message"]["content"]
    assert "Please keep replies short." in captured["prompt_text"]

    memory_entries = memory_payload(workspace_id, tab_id=tab_id)["memory"]["entries"]
    assert len(memory_entries) == 2
    assert any(entry["bucket"] == "long" for entry in memory_entries)


def test_reset_workspace_session_clears_short_memory_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_payload = list_workspaces_payload()["workspaces"][0]
    workspace_id = workspace_payload["id"]
    tab_id = workspace_payload["tabs"][0]["id"]

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).filter_by(id=workspace_id).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(id=tab_id).first()
        web_api.upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "short", "content": "Current file target is selector.py."},
                {"bucket": "long", "content": "User prefers direct, simple answers."},
            ],
            source="test",
        )
        db.commit()

    reset_workspace_session_payload(workspace_id, tab_id=tab_id)
    memory_entries = memory_payload(workspace_id, tab_id=tab_id)["memory"]["entries"]

    assert len(memory_entries) == 1
    assert memory_entries[0]["bucket"] == "long"


def test_clear_memory_payload_removes_requested_bucket(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    workspace_payload = list_workspaces_payload()["workspaces"][0]
    workspace_id = workspace_payload["id"]
    tab_id = workspace_payload["tabs"][0]["id"]

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).filter_by(id=workspace_id).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(id=tab_id).first()
        web_api.upsert_memory_entries(
            db,
            workspace,
            tab,
            [
                {"bucket": "medium", "content": "Active task is building chat memory."},
                {"bucket": "long", "content": "User prefers direct, simple answers."},
            ],
            source="test",
        )
        db.commit()

    payload = clear_memory_payload(workspace_id, tab_id=tab_id, bucket="medium")

    assert payload["deleted"] == 1
    assert len(payload["memory"]["entries"]) == 1
    assert payload["memory"]["entries"][0]["bucket"] == "long"


def test_build_selector_context_includes_goal_success_and_focus_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()
    monkeypatch.setattr(
        web_api,
        "_parse_git_status",
        lambda _path: {
            "changed": [{"path": "bettercode/web/static/app.js"}, {"path": "bettercode/web/static/styles.css"}],
            "staged": [],
            "untracked": [],
        },
    )

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        selector_context = web_api._build_selector_context(
            db,
            workspace,
            "Tighten the processing panel layout in app.js.",
            [],
        )

    assert "Goal: Tighten the processing panel layout in app.js." in selector_context
    assert "Success criteria:" in selector_context
    assert "Focus files: bettercode/web/static/app.js" in selector_context


def test_chat_payload_uses_local_fast_path_for_safe_self_contained_requests(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}
    monkeypatch.setattr(
        "bettercode.web.api.maybe_select_local_execution",
        lambda request_text, workspace_context="", task_analysis=None, selector_runtime_status=None: {
            "selected_model": "local/qwen2.5-coder:1.5b",
            "selected_model_label": "Low Mem (1.0 GB) / Local",
            "reasoning": "The request is self-contained.",
            "source": "local_direct",
            "task_analysis": task_analysis or {"task_type": "general", "complexity": 0, "estimated_tokens": 120},
            "confidence": 10,
        },
    )

    def fake_run_local_model_response(prompt_text, model_id=None, timeout=60.0, human_language=None):
        captured["prompt_text"] = prompt_text
        return {
            "reply": "def slugify(value): return value.lower().replace(' ', '-')",
            "model": f"local/{model_id}",
            "runtime": "local",
            "session_id": None,
        }

    monkeypatch.setattr(
        "bettercode.web.api.run_local_model_response",
        fake_run_local_model_response,
    )
    monkeypatch.setattr(
        "bettercode.web.api._run_workspace_chat_cli",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("local fast path should not call external CLIs")),
    )
    init_db()
    _ensure_default_workspace()
    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).filter_by(id=workspace_id).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace_id).first()
        web_api.upsert_memory_entries(
            db,
            workspace,
            tab,
            [{"bucket": "long", "kind": "preference", "content": "User prefers direct, simple answers."}],
            source="test",
        )
        db.commit()

    payload = chat_payload(workspace_id, "Write a Python function that slugifies a string.", "smart")

    assert payload["runtime"] == "local"
    assert payload["model"] == "local/qwen2.5-coder:1.5b"
    assert "slugify" in payload["message"]["content"]
    assert payload["message"]["routing_meta"]["selector"] == "local_direct"
    assert "Relevant memory for this turn:" in captured["prompt_text"]
    assert "User prefers direct, simple answers." in captured["prompt_text"]


def test_chat_payload_includes_recent_conversation_context(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_codex_cli(workspace_path, prompt_text, model_name, reasoning_effort=None, agent_mode=None, session_id=None, ephemeral=False):
        captured["prompt_text"] = prompt_text
        return {"reply": "continued", "model": "codex/gpt-5", "runtime": "codex", "session_id": "abc"}

    monkeypatch.setattr("bettercode.web.api._run_codex_cli", fake_run_codex_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    chat_payload(workspace_id, "First message", "codex/gpt-5")
    chat_payload(workspace_id, "Second message", "codex/gpt-5")

    assert "Relevant recent conversation:" in captured["prompt_text"]
    assert "user: First message" in captured["prompt_text"]
    assert "assistant: continued" in captured["prompt_text"]
    assert captured["prompt_text"].endswith("Second message")


def test_get_messages_payload_includes_activity_and_change_logs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        db.add(
            web_api.Message(
                workspace_id=workspace.id,
                tab_id=tab.id,
                role="assistant",
                content="done",
                activity_log=json.dumps(["Starting Codex...", "Updating file: app.py"]),
                history_log=json.dumps(["Starting Codex...", "Session started.", "Updating file: app.py"]),
                terminal_log="$ pwd\n/tmp/project\n",
                change_log=json.dumps([
                    {"path": "app.py", "status": "modified", "diff": "--- a/app.py\n+++ b/app.py"},
                ]),
                recommendations=json.dumps(["Add tests covering the behavior changes."]),
            )
        )
        db.commit()
        workspace_id = workspace.id

    messages = get_messages_payload(workspace_id)["messages"]

    assert messages[0]["activity_log"] == ["Starting Codex...", "Updating file: app.py"]
    assert messages[0]["history_log"] == ["Starting Codex...", "Session started.", "Updating file: app.py"]
    assert messages[0]["terminal_log"] == "$ pwd\n/tmp/project\n"
    assert messages[0]["change_log"][0]["path"] == "app.py"
    assert messages[0]["recommendations"] == ["Add tests covering the behavior changes."]


def test_chat_payload_persists_per_turn_change_log(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })

    source_file = tmp_path / "app.py"
    source_file.write_text("print('before')\n", encoding="utf-8")

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        source_file.write_text("print('after')\n", encoding="utf-8")
        return {"reply": "changed file", "model": "codex/gpt-5", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    chat_payload(workspace_id, "Update app.py", "codex/gpt-5")

    messages = get_messages_payload(workspace_id)["messages"]
    assistant_message = messages[-1]

    assert assistant_message["change_log"][0]["path"] == "app.py"
    assert assistant_message["change_log"][0]["status"] == "modified"
    assert assistant_message["change_log"][0]["diff"].startswith("--- a/app.py\n+++ b/app.py")
    assert "-print('before')" in assistant_message["change_log"][0]["diff"]
    assert "+print('after')" in assistant_message["change_log"][0]["diff"]
    assert "note" not in assistant_message["change_log"][0]


def test_workspace_turn_changes_synthesizes_diff_for_new_file_without_git(monkeypatch, tmp_path):
    new_file = tmp_path / "new_file.py"
    new_file.write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setattr(web_api, "_capture_git_change_state", lambda workspace_path: None)
    monkeypatch.setattr(web_api, "_workspace_recent_files", lambda workspace_path, started_at_ns: ["new_file.py"])

    changes = web_api._workspace_turn_changes(
        str(tmp_path),
        {"started_at_ns": 1, "existing_paths": []},
    )

    assert changes[0]["path"] == "new_file.py"
    assert changes[0]["status"] == "added"
    assert changes[0]["diff"].startswith("--- /dev/null\n+++ b/new_file.py")
    assert "+print('hello')" in changes[0]["diff"]
    assert "note" not in changes[0]


def test_workspace_turn_changes_synthesizes_diff_for_untracked_git_file(monkeypatch, tmp_path):
    new_file = tmp_path / "new_file.py"
    new_file.write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setattr(
        web_api,
        "_capture_git_change_state",
        lambda workspace_path: {
            "paths": {
                "new_file.py": {"index_status": "?", "worktree_status": "?", "stat": {"size": 15, "mtime_ns": 2}},
            }
        },
    )
    monkeypatch.setattr(web_api, "_current_git_diff", lambda workspace_path, path, before_head=None: "")

    changes = web_api._workspace_turn_changes(
        str(tmp_path),
        {"git": {"paths": {}}, "existing_paths": []},
    )

    assert changes[0]["path"] == "new_file.py"
    assert changes[0]["status"] == "added"
    assert changes[0]["diff"].startswith("--- /dev/null\n+++ b/new_file.py")
    assert "+print('hello')" in changes[0]["diff"]
    assert "note" not in changes[0]


def test_workspace_turn_changes_synthesizes_binary_diff_for_new_file(monkeypatch, tmp_path):
    binary_file = tmp_path / "logo.png"
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02")

    monkeypatch.setattr(web_api, "_capture_git_change_state", lambda workspace_path: None)
    monkeypatch.setattr(web_api, "_workspace_recent_files", lambda workspace_path, started_at_ns: ["logo.png"])

    changes = web_api._workspace_turn_changes(
        str(tmp_path),
        {"started_at_ns": 1, "existing_paths": [], "file_metadata": {}},
    )

    assert changes[0]["path"] == "logo.png"
    assert changes[0]["status"] == "added"
    assert changes[0]["diff"].startswith("--- /dev/null\n+++ b/logo.png\n@@ binary @@")
    assert "+Binary file (" in changes[0]["diff"]
    assert "note" not in changes[0]


def test_workspace_turn_changes_synthesizes_summary_for_existing_text_file_without_snapshot(monkeypatch, tmp_path):
    source_file = tmp_path / "large.txt"
    source_file.write_text("after\n", encoding="utf-8")

    monkeypatch.setattr(web_api, "_capture_git_change_state", lambda workspace_path: None)
    monkeypatch.setattr(web_api, "_workspace_recent_files", lambda workspace_path, started_at_ns: ["large.txt"])

    changes = web_api._workspace_turn_changes(
        str(tmp_path),
        {
            "started_at_ns": 1,
            "existing_paths": ["large.txt"],
            "file_metadata": {"large.txt": {"size": 2048}},
            "text_snapshot": {},
        },
    )

    assert changes[0]["path"] == "large.txt"
    assert changes[0]["status"] == "modified"
    assert changes[0]["diff"].startswith("--- a/large.txt\n+++ b/large.txt\n@@ summary @@")
    assert "-Previous text file size: 2048 bytes" in changes[0]["diff"]
    assert "+Current text file size: 6 bytes" in changes[0]["diff"]
    assert "note" not in changes[0]


def test_workspace_turn_changes_synthesizes_diff_for_deleted_file_without_git(monkeypatch, tmp_path):
    old_file = tmp_path / "obsolete.py"
    old_file.write_text("print('gone')\n", encoding="utf-8")
    snapshot = web_api._capture_turn_text_snapshot(str(tmp_path), ["obsolete.py"])
    old_file.unlink()

    monkeypatch.setattr(web_api, "_capture_git_change_state", lambda workspace_path: None)
    monkeypatch.setattr(web_api, "_workspace_recent_files", lambda workspace_path, started_at_ns: [])

    changes = web_api._workspace_turn_changes(
        str(tmp_path),
        {"started_at_ns": 1, "existing_paths": ["obsolete.py"], "text_snapshot": snapshot},
    )

    assert changes[0]["path"] == "obsolete.py"
    assert changes[0]["status"] == "deleted"
    assert changes[0]["diff"].startswith("--- a/obsolete.py\n+++ /dev/null")
    assert "-print('gone')" in changes[0]["diff"]
    assert "note" not in changes[0]


def test_workspace_turn_changes_omits_generated_artifacts_when_source_files_exist(monkeypatch):
    monkeypatch.setattr(
        web_api,
        "_capture_git_change_state",
        lambda workspace_path: {
            "paths": {
                "app/page.jsx": {"index_status": ".", "worktree_status": "M", "stat": {"size": 1, "mtime_ns": 2}},
                ".next/trace": {"index_status": ".", "worktree_status": "M", "stat": {"size": 1, "mtime_ns": 2}},
                "out/index.html": {"index_status": ".", "worktree_status": "M", "stat": {"size": 1, "mtime_ns": 2}},
            }
        },
    )
    monkeypatch.setattr(web_api, "_current_git_diff", lambda workspace_path, path, before_head=None: f"diff for {path}")

    changes = web_api._workspace_turn_changes(
        "/tmp/project",
        {"git": {"paths": {}}},
    )

    assert changes[0]["path"] == "app/page.jsx"
    assert all(not change["path"].startswith(".next/") for change in changes if "/" in change["path"])
    assert all(not change["path"].startswith("out/") for change in changes if "/" in change["path"])
    assert changes[-1]["status"] == "generated"
    assert "Generated build output" in changes[-1]["note"]


def test_workspace_turn_changes_keeps_generated_artifacts_when_they_are_all_that_changed(monkeypatch):
    monkeypatch.setattr(
        web_api,
        "_capture_git_change_state",
        lambda workspace_path: {
            "paths": {
                ".next/trace": {"index_status": ".", "worktree_status": "M", "stat": {"size": 1, "mtime_ns": 2}},
                "out/index.html": {"index_status": ".", "worktree_status": "M", "stat": {"size": 1, "mtime_ns": 2}},
            }
        },
    )
    monkeypatch.setattr(web_api, "_current_git_diff", lambda workspace_path, path, before_head=None: f"diff for {path}")

    changes = web_api._workspace_turn_changes(
        "/tmp/project",
        {"git": {"paths": {}}},
    )

    assert [change["path"] for change in changes] == [".next/trace", "out/index.html"]


def test_workspace_turn_changes_include_generated_files(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    create_workspace_payload(str(tmp_path))

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        turn_context = web_api._capture_turn_context(workspace)

    generated_root = web_api._workspace_generated_dir(workspace.id, create=True)
    (generated_root / "notes").mkdir(parents=True, exist_ok=True)
    (generated_root / "notes" / "plan.md").write_text("# plan\n", encoding="utf-8")

    changes = web_api._workspace_turn_changes(str(tmp_path), turn_context)

    assert any(change["path"] == "generated/notes/plan.md" for change in changes)


def test_relocate_new_workspace_files_moves_staged_generated_files_to_generated_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    create_workspace_payload(str(tmp_path))

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        turn_context = web_api._capture_turn_context(workspace)
        staging_dir = web_api._workspace_generated_staging_dir(workspace, create=True)
        (staging_dir / "docs").mkdir(parents=True, exist_ok=True)
        (staging_dir / "docs" / "brief.md").write_text("hello\n", encoding="utf-8")
        web_api._relocate_new_workspace_files(workspace, turn_context)

    generated_file = web_api._workspace_generated_dir(workspace.id, create=False) / "docs" / "brief.md"
    assert not (staging_dir / "docs" / "brief.md").exists()
    assert generated_file.read_text(encoding="utf-8") == "hello\n"


def test_relocate_new_workspace_files_leaves_new_repo_files_in_place(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    create_workspace_payload(str(tmp_path))

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        turn_context = web_api._capture_turn_context(workspace)
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
        web_api._relocate_new_workspace_files(workspace, turn_context)

    assert (tmp_path / "src" / "app.py").read_text(encoding="utf-8") == "print('hello')\n"
    assert not (web_api._workspace_generated_dir(workspace.id, create=False) / "src" / "app.py").exists()


def test_get_messages_payload_paginates_results(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        for index in range(6):
            db.add(web_api.Message(workspace_id=workspace.id, tab_id=tab.id, role="user", content=f"message {index}"))
        db.commit()
        workspace_id = workspace.id

    first_page = get_messages_payload(workspace_id, limit=3)

    assert [message["content"] for message in first_page["messages"]] == ["message 3", "message 4", "message 5"]
    assert first_page["paging"]["has_more"] is True
    assert first_page["paging"]["next_before_id"] is not None

    second_page = get_messages_payload(workspace_id, limit=3, before_id=first_page["paging"]["next_before_id"])

    assert [message["content"] for message in second_page["messages"]] == ["message 0", "message 1", "message 2"]
    assert second_page["paging"]["has_more"] is False


def test_chat_payload_reuses_workspace_codex_session(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_codex_cli(workspace_path, prompt_text, model_name, reasoning_effort=None, agent_mode=None, session_id=None, ephemeral=False):
        captured["session_id"] = session_id
        return {"reply": "resumed", "model": "codex/gpt-5", "runtime": "codex", "session_id": session_id or "session-1"}

    monkeypatch.setattr("bettercode.web.api._run_codex_cli", fake_run_codex_cli)
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        tab.codex_session_id = "codex-session-123"
        db.commit()
        workspace_id = workspace.id

    payload = chat_payload(workspace_id, "Continue this project", "codex/gpt-5")

    assert payload["model"] == "codex/gpt-5"
    assert captured["session_id"] == "codex-session-123"

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).filter_by(id=workspace_id).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace_id).first()
        assert tab.session_state == "warm"
        assert tab.last_runtime == "codex"
        assert tab.last_model == "codex/gpt-5"


def test_chat_payload_routes_smart_selection_through_better_select(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/default", "label": "Codex Default"},
        {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr("bettercode.web.api.select_best_model", lambda prompt, models, context, routing_history=None, selector_runtime_status=None: {
        "selected_model": "codex/gpt-5.4@high",
        "reasoning": "Complex task.",
        "source": "local",
        "task_analysis": {"task_type": "architecture", "complexity": 4, "estimated_tokens": 200, "multi_file": False, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": True},
    })
    captured = {}

    def fake_run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=None):
        captured["selected_model"] = selected_model
        return {"reply": "smart answer", "model": selected_model, "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_workspace_chat_cli", fake_run_workspace_chat_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    payload = chat_payload(workspace_id, "Refactor the architecture", "smart")

    assert payload["model"] == "codex/gpt-5.4@high"
    assert captured["selected_model"] == "codex/gpt-5.4@high"
    assert payload["message"]["routing_meta"]["selector"] == "local"
    assert payload["message"]["routing_meta"]["task_type"] == "architecture"
    assert payload["message"]["routing_meta"]["reason"] == "Complex task."


def test_chat_stream_payload_skips_local_preprocessing_for_manual_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._selector_preprocess_turn", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selector should not run")))
    monkeypatch.setattr("bettercode.web.api.plan_subtasks", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr("bettercode.web.api._start_turn_postprocess", lambda *args, **kwargs: None)

    def fake_stream_codex_cli(workspace_path, prompt_text, model_name, reasoning_effort=None, agent_mode=None, session_id=None, activity_log=None, history_log=None, workspace_id=None, terminal_log=None):
        if activity_log is not None:
            activity_log.append("Starting Codex...")
        if history_log is not None:
            history_log.append("Starting Codex...")
        if terminal_log is not None:
            terminal_log.append("$ pwd\n/tmp/project\n")
        yield web_api._stream_event_bytes("terminal_chunk", text="$ pwd\n/tmp/project\n")
        yield web_api._stream_event_bytes("status", message="Starting Codex...")
        return {"reply": "streamed answer", "model": "codex/gpt-5", "runtime": "codex", "session_id": "session-1"}

    monkeypatch.setattr("bettercode.web.api._stream_codex_cli", fake_stream_codex_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    response = web_api.chat_stream_payload(workspace_id, "Use the selected model", "codex/gpt-5")
    payload = asyncio.run(_read_streaming_response(response))

    assert "The local router is pre-processing the request." not in payload
    assert "Using GPT-5." in payload
    assert '"terminal_log": "$ pwd\\n/tmp/project\\n"' in payload


def test_chat_stream_payload_skips_task_breakdown_when_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api.plan_subtasks", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))
    monkeypatch.setattr("bettercode.web.api._selector_preprocess_context", lambda *args, **kwargs: (
        "Workspace: test",
        {"task_type": "implementation", "complexity": 1, "estimated_tokens": 100, "multi_file": False, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": False},
        {"workspace": {}, "global": {}},
        [{"id": "codex/gpt-5", "label": "GPT-5"}],
        None,
    ))
    monkeypatch.setattr("bettercode.web.api.maybe_select_local_execution", lambda *args, **kwargs: None)
    monkeypatch.setattr("bettercode.web.api._resolve_better_select_model", lambda *args, **kwargs: {
        "selected_model": "codex/gpt-5",
        "selected_model_label": "GPT-5",
        "reasoning": "Balanced pick.",
        "source": "local",
        "task_analysis": {"task_type": "implementation", "complexity": 1, "estimated_tokens": 100, "multi_file": False, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": False},
    })
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr("bettercode.web.api._start_turn_postprocess", lambda *args, **kwargs: None)

    def fake_stream_codex_cli(*args, **kwargs):
        raise web_api.ChatStoppedError("Chat stopped.")
        yield  # pragma: no cover

    monkeypatch.setattr("bettercode.web.api._stream_codex_cli", fake_stream_codex_cli)
    init_db()
    web_api.set_app_settings(None, "balanced", enable_task_breakdown=False)
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    response = web_api.chat_stream_payload(workspace_id, "Route this automatically", "smart")
    payload = asyncio.run(_read_streaming_response(response))

    assert "Task breakdown" not in payload
    assert "Auto Model Select chose GPT-5. Balanced pick." in payload


def test_chat_stream_payload_prefers_local_fast_path_before_task_breakdown(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._selector_preprocess_context", lambda *args, **kwargs: (
        "Workspace: test",
        {"task_type": "general", "complexity": 0, "estimated_tokens": 12, "multi_file": False, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": False},
        {"workspace": {}, "global": {}},
        [{"id": "codex/gpt-5", "label": "GPT-5"}],
        {"running": True, "model_ready": True, "selected_model": "qwen2.5-coder:1.5b", "mode": "tiny"},
    ))
    monkeypatch.setattr(
        "bettercode.web.api.maybe_select_local_execution",
        lambda *args, **kwargs: {
            "selected_model": "local/qwen2.5-coder:1.5b",
            "selected_model_label": "Low Mem (1.0 GB) / Local",
            "reasoning": "This is a short self-contained request, so BetterCode can answer it locally.",
            "source": "local_direct",
            "task_analysis": {"task_type": "general", "complexity": 0, "estimated_tokens": 12, "multi_file": False, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": False},
            "confidence": 10,
        },
    )
    monkeypatch.setattr(
        "bettercode.web.api.plan_subtasks",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner should not run before a local fast-path selection")),
    )
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr("bettercode.web.api._start_turn_postprocess", lambda *args, **kwargs: None)

    def fake_run_local_model_response(prompt_text, model_id=None, timeout=60.0, human_language=None):
        return {
            "reply": "4",
            "model": f"local/{model_id}",
            "runtime": "local",
            "session_id": None,
        }

    monkeypatch.setattr("bettercode.web.api.run_local_model_response", fake_run_local_model_response)
    init_db()
    web_api.set_app_settings(None, "balanced", enable_task_breakdown=True)
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    response = web_api.chat_stream_payload(workspace_id, "What is 2 + 2?", "smart")
    payload = asyncio.run(_read_streaming_response(response))

    assert "Auto Model Select chose Low Mem (1.0 GB) / Local." in payload
    assert '"selector": "local_direct"' in payload
    assert '"runtime": "local"' in payload
    assert "Task breakdown" not in payload


def test_chat_stream_payload_emits_model_track_metadata_for_breakdown(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "codex/gpt-5.4@medium", "label": "GPT-5.4 / Medium"},
        {"id": "codex/gpt-5.4", "label": "GPT-5.4"},
        {"id": "claude/sonnet", "label": "Claude Sonnet"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._selector_preprocess_context", lambda *args, **kwargs: (
        "Workspace: test",
        {"task_type": "implementation", "complexity": 3, "estimated_tokens": 900, "multi_file": True, "has_recent_history": False, "has_attachments": False, "needs_deep_reasoning": False},
        {"workspace": {}, "global": {}},
        [
            {"id": "codex/gpt-5.4@medium", "label": "GPT-5.4 / Medium", "runtime": "codex"},
            {"id": "codex/gpt-5.4", "label": "GPT-5.4", "runtime": "codex"},
            {"id": "claude/sonnet", "label": "Claude Sonnet", "runtime": "claude"},
        ],
        None,
    ))
    monkeypatch.setattr("bettercode.web.api.plan_subtasks", lambda *args, **kwargs: {
        "source": "local",
        "tasks": [
            {
                "id": "inspect-code",
                "title": "Inspect code",
                "detail": "Read the current implementation.",
                "depends_on": [],
                "execution": "async",
                "stage": "inspect",
                "model_id": "claude/sonnet",
                "model_label": "Claude Sonnet",
                "selection_reason": "This is a read-heavy inspection step, so a faster scan model fit best.",
                "track_key": "model:claude/sonnet",
                "track_label": "Claude Sonnet",
                "track_kind": "model",
                "parallel_group": "inspect:root",
            },
            {
                "id": "wire-ui",
                "title": "Wire the UI",
                "detail": "Implement the task tracker.",
                "depends_on": ["inspect-code"],
                "execution": "sync",
                "stage": "edit",
                "model_id": "codex/gpt-5.4",
                "model_label": "GPT-5.4",
                "selection_reason": "This is the main code-writing step, so BetterCode kept a stronger implementation model on it.",
                "track_key": "model:codex/gpt-5.4",
                "track_label": "GPT-5.4",
                "track_kind": "model",
                "parallel_group": "",
            },
        ],
    })
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    monkeypatch.setattr("bettercode.web.api._start_turn_postprocess", lambda *args, **kwargs: None)
    monkeypatch.setattr("bettercode.web.api._workspace_turn_changes", lambda *args, **kwargs: [
        {"path": "bettercode/web/api.py", "status": "modified", "diff": ""},
        {"path": "bettercode/web/static/app.js", "status": "modified", "diff": ""},
    ])

    def fake_run_orchestrated_task_cli(workspace_path, prompt_text, selected_model, agent_mode=None, workspace_id=None, stream_handler=None):
        if "Inspect code" in prompt_text:
            if stream_handler:
                stream_handler({"type": "terminal_chunk", "text": "$ rg task graph\nInspecting planner output...\n"})
                stream_handler({"type": "history_line", "text": "$ rg task graph"})
            return {"reply": "Inspected the existing implementation and mapped the task graph.", "model": "claude/sonnet", "runtime": "claude"}
        if stream_handler:
            stream_handler({"type": "terminal_chunk", "text": "$ apply_patch\nUpdated app.js\n"})
            stream_handler({"type": "history_line", "text": "$ apply_patch"})
        return {"reply": "Implemented the task tracker UI and backend orchestration.", "model": "codex/gpt-5.4", "runtime": "codex"}

    monkeypatch.setattr("bettercode.web.api._run_orchestrated_task_cli", fake_run_orchestrated_task_cli)
    init_db()
    web_api.set_app_settings(None, "balanced", enable_task_breakdown=True)
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    response = web_api.chat_stream_payload(workspace_id, "Handle several related tasks", "smart")
    payload = asyncio.run(_read_streaming_response(response))

    assert '"track_key": "model:claude/sonnet"' in payload
    assert '"track_key": "model:codex/gpt-5.4"' in payload
    assert '"kind": "planned"' in payload
    assert '"kind": "system"' in payload
    assert '"title": "Planning"' in payload
    assert '"title": "Task breakdown"' in payload
    assert '"title": "Execute tasks"' in payload
    assert '"title": "Validate completion"' in payload
    assert '"selection_reason": "This is a read-heavy inspection step, so a faster scan model fit best."' in payload
    assert '"selection_reason": "This is the main code-writing step, so BetterCode kept a stronger implementation model on it."' in payload
    assert 'Auto Model Select planned 2 tasks, 2 models, 1 parallel.' in payload
    assert '"model_label": "Multi-model plan"' in payload
    assert '"task_count": 2' in payload
    assert '"depends_on": ["subtask:inspect-code"]' in payload
    assert '"type": "terminal_chunk"' in payload
    assert "$ rg task graph" in payload


def test_chat_stream_payload_emits_cancelled_event(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "codex/gpt-5", "label": "GPT-5"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })

    def fake_stream_codex_cli(*args, **kwargs):
        raise web_api.ChatStoppedError("Chat stopped.")
        yield  # pragma: no cover

    monkeypatch.setattr("bettercode.web.api._stream_codex_cli", fake_stream_codex_cli)
    init_db()
    _ensure_default_workspace()

    workspace_id = list_workspaces_payload()["workspaces"][0]["id"]
    response = web_api.chat_stream_payload(workspace_id, "Stop this", "codex/gpt-5")
    payload = asyncio.run(_read_streaming_response(response))

    assert '"type": "cancelled"' in payload


def test_workspace_session_pool_caps_warm_projects(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with web_api.SessionLocal() as db:
        for index in range(6):
            workspace = web_api.Workspace(
                name=f"project-{index}",
                path=str(tmp_path / f"project-{index}"),
                last_used_at=datetime.now(UTC) - timedelta(minutes=index),
            )
            db.add(workspace)
            db.flush()
            tab = web_api.WorkspaceTab(
                workspace_id=workspace.id,
                title="New Tab",
                codex_session_id=f"session-{index}",
                last_used_at=workspace.last_used_at,
            )
            db.add(tab)

        db.commit()
        web_api._rebalance_workspace_session_pool(db)
        db.commit()

        refreshed = db.query(web_api.WorkspaceTab).order_by(web_api.WorkspaceTab.workspace_id.asc()).all()

    warm_ids = {tab.workspace_id for tab in refreshed if tab.session_state == "warm"}
    cold_ids = {tab.workspace_id for tab in refreshed if tab.session_state == "cold"}

    assert len(warm_ids) == web_api.MAX_WARM_WORKSPACES
    assert len(cold_ids) == 2
    assert refreshed[0].id in warm_ids
    assert refreshed[1].id in warm_ids
    assert refreshed[4].id in cold_ids
    assert refreshed[5].id in cold_ids


def test_activate_workspace_session_promotes_recent_saved_session(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        tab.codex_session_id = "session-1"
        tab.session_state = "cold"
        db.commit()
        workspace_id = workspace.id

    payload = web_api.activate_workspace_session_payload(workspace_id)

    assert payload["workspace"]["session_state"] == "warm"
    assert payload["workspace"]["has_session"] is True
    assert payload["workspace"]["session_runtime"] == "codex"


def test_reset_workspace_session_clears_saved_runtime_sessions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        tab.codex_session_id = "session-1"
        tab.claude_session_id = "session-2"
        tab.last_runtime = "codex"
        tab.last_model = "codex/gpt-5.4"
        tab.session_state = "warm"
        db.commit()
        workspace_id = workspace.id

    payload = web_api.reset_workspace_session_payload(workspace_id)

    assert payload["workspace"]["session_state"] == "cold"
    assert payload["workspace"]["has_session"] is False
    assert payload["workspace"]["last_runtime"] == ""
    assert payload["workspace"]["last_model"] == ""


def test_workspace_session_pool_ages_out_stale_sessions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    with web_api.SessionLocal() as db:
        fresh = web_api.Workspace(
            name="fresh",
            path=str(tmp_path / "fresh"),
            last_used_at=datetime.now(UTC),
        )
        stale = web_api.Workspace(
            name="stale",
            path=str(tmp_path / "stale"),
            last_used_at=datetime.now(UTC) - timedelta(minutes=web_api.WARM_SESSION_IDLE_MINUTES + 5),
        )
        db.add(fresh)
        db.add(stale)
        db.flush()
        db.add(web_api.WorkspaceTab(
            workspace_id=fresh.id,
            title="New Tab",
            codex_session_id="fresh-session",
            last_used_at=fresh.last_used_at,
        ))
        db.add(web_api.WorkspaceTab(
            workspace_id=stale.id,
            title="New Tab",
            codex_session_id="stale-session",
            last_used_at=stale.last_used_at,
        ))
        db.commit()

        web_api._rebalance_workspace_session_pool(db)
        db.commit()

        fresh = db.query(web_api.WorkspaceTab).join(web_api.Workspace).filter(web_api.Workspace.name == "fresh").first()
        stale = db.query(web_api.WorkspaceTab).join(web_api.Workspace).filter(web_api.Workspace.name == "stale").first()

    assert fresh.session_state == "warm"
    assert stale.session_state == "cold"


def test_model_options_reflect_installed_runtimes(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", None)
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", None)
    monkeypatch.setattr(
        "bettercode.web.api._cli_discovered_model_registry",
        lambda runtime: {
            "claude": [
                {"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"},
                {"id": "claude/claude-haiku-4-5", "label": "Claude Haiku 4.5"},
            ],
            "gemini": [
                {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                {"id": "gemini/gemini-3-pro-preview", "label": "Gemini 3 Pro Preview"},
                {"id": "gemini/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview"},
                {"id": "gemini/gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite Preview"},
            ],
        }.get(runtime, []),
    )
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": True, "path": "/usr/bin/gemini", "configured": True},
    })
    monkeypatch.setattr("bettercode.web.api._codex_cached_model_registry", lambda: [
        {"id": "codex/default", "label": "Codex Default"},
        {"id": "codex/gpt-5.4", "label": "gpt-5.4"},
        {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High"},
    ])

    options = _model_options()

    assert options[0]["id"] == "smart"
    assert {option["id"] for option in options} == {
        "smart",
        "codex/gpt-5.4",
        "codex/gpt-5.4@high",
        "claude/claude-opus-4-6",
        "claude/claude-haiku-4-5",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-3-pro-preview",
        "gemini/gemini-3.1-pro-preview",
        "gemini/gemini-3.1-flash-lite-preview",
    }


def test_refresh_model_discovery_cache_rebuilds_verified_cache(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [{"id": "stale", "label": "Stale"}])
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", [{"id": "stale", "label": "Stale"}])

    def _fake_refresh(force_refresh=False):
        web_api.MODEL_DISCOVERY_CACHE["registry"] = [{"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"}]
        web_api.MODEL_DISCOVERY_CACHE["options"] = [
            {"id": "smart", "label": "Auto Model Select"},
            {"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"},
        ]
        return {"models": web_api.MODEL_DISCOVERY_CACHE["options"]}

    monkeypatch.setattr(web_api, "refresh_model_options_payload", _fake_refresh)

    web_api._refresh_model_discovery_cache(verified=True)

    assert web_api.MODEL_DISCOVERY_CACHE["registry"] == [{"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"}]
    assert web_api.MODEL_DISCOVERY_CACHE["options"] == [
        {"id": "smart", "label": "Auto Model Select"},
        {"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"},
    ]


def test_refresh_model_discovery_cache_clears_stale_cache_on_failure(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [{"id": "stale", "label": "Stale"}])
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", [{"id": "stale", "label": "Stale"}])
    monkeypatch.setattr(
        web_api,
        "refresh_model_options_payload",
        lambda force_refresh=False: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    web_api._refresh_model_discovery_cache(verified=True)

    assert web_api.MODEL_DISCOVERY_CACHE["registry"] is None
    assert web_api.MODEL_DISCOVERY_CACHE["options"] is None


def test_require_selector_for_app_startup_returns_error_payload_on_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        "bettercode.web.bootstrap.require_selector_runtime",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("selector missing")),
    )
    monkeypatch.setattr(
        "bettercode.web.bootstrap.selector_status",
        lambda: {"installed": False, "running": False, "model_ready": False, "model": ""},
    )

    result = _require_selector_for_app_startup()

    assert result["ok"] is False
    assert result["error"] == "selector missing"
    assert result["status"]["running"] is False


def test_create_app_startup_schedules_selector_warmup(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    calls = {"warmup": 0, "model_warmup": []}
    monkeypatch.setattr(web_api, "_start_selector_warmup", lambda: calls.__setitem__("warmup", calls["warmup"] + 1))
    monkeypatch.setattr(web_api, "_start_model_discovery_warmup", lambda verified=False: calls["model_warmup"].append(verified))

    app = create_app()
    with TestClient(app):
        pass

    assert calls["warmup"] == 1
    assert calls["model_warmup"] == [False]


def test_refresh_model_options_payload_skips_verified_probe_while_chat_active(monkeypatch):
    class FakeProcess:
        pid = 999

        def poll(self):
            return None

    with web_api.ACTIVE_CHAT_PROCESSES_LOCK:
        web_api.ACTIVE_CHAT_PROCESSES[1] = FakeProcess()
    with web_api.ACTIVE_CHAT_PROCESS_META_LOCK:
        web_api.ACTIVE_CHAT_PROCESS_META[1] = {"pid": 999}
    monkeypatch.setattr(web_api, "_model_options_for_app_info", lambda: [{"id": "smart", "label": "Auto Model Select"}])
    monkeypatch.setattr(
        web_api,
        "_discover_model_registry",
        lambda verified=False, runtimes=None: (_ for _ in ()).throw(AssertionError("verified discovery should not run")),
    )

    try:
        payload = web_api.refresh_model_options_payload()
    finally:
        web_api._clear_active_chat_process(1)

    assert payload["models"] == [{"id": "smart", "label": "Auto Model Select"}]


def test_selector_warmup_noops_when_local_preprocess_off(monkeypatch):
    import bettercode.web.bootstrap as web_bootstrap

    started = {"count": 0}

    class FakeThread:
        def __init__(self, *args, **kwargs):
            started["count"] += 1

        def start(self):
            started["count"] += 10

    monkeypatch.setattr(web_bootstrap, "get_local_preprocess_mode", lambda: "off")
    monkeypatch.setattr(web_bootstrap.threading, "Thread", FakeThread)

    web_bootstrap._start_selector_warmup()

    assert started["count"] == 0


def test_chat_status_endpoint_returns_active_process_payload(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    workspace_payload = create_workspace_payload(str(tmp_path))
    workspace_id = workspace_payload["workspace"]["id"]
    app = create_app()

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    web_api._register_active_chat_process(workspace_id, FakeProcess(), "claude")
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/workspaces/{workspace_id}/chat/status")
    finally:
        web_api._clear_active_chat_process(workspace_id)

    assert response.status_code == 200
    assert response.json()["chat"]["active"] is True
    assert response.json()["chat"]["pid"] == 4242
    assert response.json()["chat"]["runtime"] == "claude"


def test_stop_chat_endpoint_stops_active_process(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()
    workspace_payload = create_workspace_payload(str(tmp_path))
    workspace_id = workspace_payload["workspace"]["id"]
    app = create_app()
    killed = {}

    class FakeProcess:
        pid = 8484

        def poll(self):
            return None

    monkeypatch.setattr(web_api, "_kill_process_tree", lambda process: killed.setdefault("pid", process.pid))
    web_api._register_active_chat_process(workspace_id, FakeProcess(), "codex")
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/workspaces/{workspace_id}/chat/stop")
            assert response.status_code == 200
            assert response.json() == {"stopped": True, "already_finished": False}
            status = client.get(f"/api/workspaces/{workspace_id}/chat/status")
    finally:
        web_api._clear_active_chat_process(workspace_id)

    assert killed["pid"] == 8484
    assert status.status_code == 200
    assert status.json()["chat"]["stop_requested"] is True


def test_model_options_do_not_probe_runtime_models_on_startup(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", None)
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", None)
    monkeypatch.setattr(
        "bettercode.web.api._cli_discovered_model_registry",
        lambda runtime: {
            "claude": [
                {"id": "claude/claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
                {"id": "claude/claude-sonnet-4-5-20250929", "label": "Claude Sonnet 4.5 (20250929)"},
            ],
            "gemini": [
                {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
                {"id": "gemini/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview"},
            ],
        }.get(runtime, []),
    )
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": True, "path": "/usr/bin/gemini", "configured": True},
    })
    monkeypatch.setattr("bettercode.web.api._codex_cached_model_registry", lambda: [
        {"id": "codex/default", "label": "Codex Default"},
    ])
    monkeypatch.setattr(
        "bettercode.web.api._probe_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("startup model discovery should not probe runtimes")),
    )

    options = _model_options()

    assert {option["id"] for option in options} == {
        "smart",
        "claude/claude-sonnet-4-6",
        "claude/claude-sonnet-4-5-20250929",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-3.1-pro-preview",
    }


def test_refresh_model_options_payload_returns_only_verified_models(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", None)
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "registry", None)
    monkeypatch.setattr(
        "bettercode.web.api._cli_discovered_model_registry",
        lambda runtime: {
            "claude": [
                {"id": "claude/claude-opus-4-6", "label": "Claude Opus 4.6"},
                {"id": "claude/claude-opus-4-5-20251101", "label": "Claude Opus 4.5 (20251101)"},
            ],
            "gemini": [
                {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                {"id": "gemini/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview"},
            ],
        }.get(runtime, []),
    )
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": True, "path": "/usr/bin/gemini", "configured": True},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })
    monkeypatch.setattr("bettercode.web.api._codex_cached_model_registry", lambda: [
        {"id": "codex/default", "label": "Codex Default"},
        {"id": "codex/gpt-5.4", "label": "gpt-5.4"},
        {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High"},
    ])
    monkeypatch.setattr(
        "bettercode.web.api._probe_model",
        lambda model_id, **_kwargs: model_id in {"claude/claude-opus-4-6", "gemini/gemini-2.5-pro"},
    )

    payload = refresh_model_options_payload()

    assert [model["id"] for model in payload["models"]] == [
        "smart",
        "codex/gpt-5.4",
        "codex/gpt-5.4@high",
        "claude/claude-opus-4-6",
        "gemini/gemini-2.5-pro",
    ]


def test_verified_claude_registry_probes_base_model_once_and_keeps_effort_variants(monkeypatch):
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": False, "path": None, "configured": False},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })
    monkeypatch.setattr(
        "bettercode.web.api._cli_discovered_model_registry",
        lambda runtime: [
            {"id": "claude/claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
            {"id": "claude/claude-sonnet-4-6@low", "label": "Claude Sonnet 4.6 / Low"},
            {"id": "claude/claude-sonnet-4-6@medium", "label": "Claude Sonnet 4.6 / Medium"},
            {"id": "claude/claude-opus-4-0", "label": "Claude Opus 4.0"},
            {"id": "claude/claude-opus-4-0@high", "label": "Claude Opus 4.0 / High"},
        ] if runtime == "claude" else [],
    )
    probed = []
    monkeypatch.setattr(
        "bettercode.web.api._probe_model",
        lambda model_id, **_kwargs: probed.append(model_id) or model_id == "claude/claude-sonnet-4-6",
    )

    payload = web_api._verified_runtime_model_registry("claude")

    assert [entry["id"] for entry in payload] == [
        "claude/claude-sonnet-4-6",
        "claude/claude-sonnet-4-6@low",
        "claude/claude-sonnet-4-6@medium",
    ]
    assert probed == [
        "claude/claude-sonnet-4-6",
        "claude/claude-opus-4-0",
    ]


def test_model_options_exclude_unconfigured_runtimes(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", None)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": False},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": False},
        "gemini": {"available": True, "path": "/usr/bin/gemini", "configured": False},
    })

    assert _model_options() == []


def test_generated_files_payload_lists_workspace_outputs(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    workspace_payload = create_workspace_payload(str(tmp_path))
    workspace_id = workspace_payload["workspace"]["id"]
    generated_root = web_api._workspace_generated_dir(workspace_id, create=True)
    (generated_root / "report.txt").write_text("done\n", encoding="utf-8")

    payload = web_api.generated_files_payload(workspace_id)

    assert payload["workspace"]["generated_files_count"] == 1
    assert payload["generated_root"] == str(generated_root)
    assert payload["generated_files"] == [{
        "path": "report.txt",
        "name": "report.txt",
        "absolute_path": str(generated_root / "report.txt"),
        "size": 5,
        "modified_at": payload["generated_files"][0]["modified_at"],
    }]


def test_open_generated_file_payload_opens_selected_generated_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    workspace_payload = create_workspace_payload(str(tmp_path))
    workspace_id = workspace_payload["workspace"]["id"]
    generated_root = web_api._workspace_generated_dir(workspace_id, create=True)
    file_path = generated_root / "report.pdf"
    file_path.write_text("pdf\n", encoding="utf-8")
    opened = {}

    monkeypatch.setattr(web_api, "_open_with_system_default", lambda path: opened.setdefault("path", path))

    payload = web_api.open_generated_file_payload(workspace_id, "report.pdf")

    assert payload["opened"] is True
    assert payload["path"] == "report.pdf"
    assert payload["absolute_path"] == str(file_path)
    assert opened["path"] == file_path


def test_open_generated_file_payload_rejects_path_escape(monkeypatch, tmp_path):
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    init_db()

    workspace_payload = create_workspace_payload(str(tmp_path))
    workspace_id = workspace_payload["workspace"]["id"]

    with pytest.raises(web_api.HTTPException) as exc:
        web_api.open_generated_file_payload(workspace_id, "../outside.txt")

    assert exc.value.status_code == 400


def test_open_with_system_default_uses_open_on_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        web_api.shutil,
        "which",
        lambda command: "/usr/bin/open" if command == "open" else None,
    )
    captured = {}

    def fake_launch(command, workspace_path=None):
        captured["command"] = command
        captured["workspace_path"] = workspace_path

    monkeypatch.setattr(web_api, "_launch_detached_command", fake_launch)

    web_api._open_with_system_default(tmp_path / "report.pdf")

    assert captured == {
        "command": ["/usr/bin/open", str(tmp_path / "report.pdf")],
        "workspace_path": None,
    }


def test_open_with_system_default_uses_cmd_start_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(web_api.os, "name", "nt", raising=False)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    captured = {}

    def fake_launch(command, workspace_path=None):
        captured["command"] = command
        captured["workspace_path"] = workspace_path

    monkeypatch.setattr(web_api, "_launch_detached_command", fake_launch)

    web_api._open_with_system_default(tmp_path / "report.pdf")

    assert captured == {
        "command": [r"C:\Windows\System32\cmd.exe", "/c", "start", '""', str(tmp_path / "report.pdf")],
        "workspace_path": None,
    }


def test_open_with_system_default_falls_back_to_gio_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        web_api.shutil,
        "which",
        lambda command: "/usr/bin/gio" if command == "gio" else None,
    )
    captured = {}

    def fake_launch(command, workspace_path=None):
        captured["command"] = command
        captured["workspace_path"] = workspace_path

    monkeypatch.setattr(web_api, "_launch_detached_command", fake_launch)

    web_api._open_with_system_default(tmp_path / "report.pdf")

    assert captured == {
        "command": ["/usr/bin/gio", "open", str(tmp_path / "report.pdf")],
        "workspace_path": None,
    }


def test_build_prompt_text_routes_new_files_through_workspace_staging_dir():
    prompt = web_api._build_prompt_text(
        "Generate a PDF.",
        [],
        workspace_context="Workspace context",
        generated_files_dir="/Users/mitch/.bettercode/generated-files/workspace-1",
        generated_files_staging_dir="/repo/.bettercode-generated",
    )

    assert "Do not try to write brand-new files directly to the final generated-files directory" in prompt
    assert "For generated outputs that should live outside the repo" in prompt
    assert "If the task is to create or scaffold real project files that belong in the repo" in prompt
    assert "/repo/.bettercode-generated" in prompt
    assert "/Users/mitch/.bettercode/generated-files/workspace-1" in prompt


def test_runtime_has_login_detects_claude_state_file(monkeypatch, tmp_path):
    claude_state_file = tmp_path / ".claude.json"
    claude_state_file.write_text(json.dumps({
        "oauthAccount": {
            "emailAddress": "mitch@example.com",
            "organizationName": "Example Org",
        }
    }), encoding="utf-8")

    monkeypatch.setattr(web_api, "CLAUDE_STATE_FILE", claude_state_file)
    monkeypatch.setattr(web_api, "RUNTIME_AUTH_FILES", {
        **web_api.RUNTIME_AUTH_FILES,
        "claude": [],
    })

    assert web_api._runtime_has_login("claude") is True
    assert web_api._runtime_access_state("claude")["configured"] is True
    assert web_api._runtime_access_state("claude")["access_label"] == "Logged in"


def test_codex_cached_model_options_include_visible_models_once(monkeypatch, tmp_path):
    models_cache = tmp_path / "models_cache.json"
    models_cache.write_text(json.dumps({
        "models": [
            {
                "slug": "gpt-5.4",
                "display_name": "gpt-5.4",
                "visibility": "list",
                "priority": 0,
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [
                    {"effort": "low"},
                    {"effort": "medium"},
                    {"effort": "high"},
                    {"effort": "xhigh"},
                ],
            },
            {
                "slug": "internal-only",
                "display_name": "internal-only",
                "visibility": "hidden",
            },
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(web_api, "CODEX_MODELS_CACHE_PATH", models_cache)

    options = web_api._codex_cached_model_options()

    assert options == [
        {"id": "codex/gpt-5.4@low", "label": "gpt-5.4 / Low"},
        {"id": "codex/gpt-5.4@medium", "label": "gpt-5.4 / Medium"},
        {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High"},
        {"id": "codex/gpt-5.4@xhigh", "label": "gpt-5.4 / XHigh"},
    ]


def test_cli_discovered_model_registry_combines_documented_and_history_models(monkeypatch):
    monkeypatch.setattr("bettercode.web.api._claude_cli_documented_model_names", lambda: ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-haiku-4-5-20251001"])
    monkeypatch.setattr("bettercode.web.api._claude_cli_model_names", lambda: ["claude-opus-4-6", "claude-sonnet-4-6"])
    monkeypatch.setattr("bettercode.web.api._gemini_cli_documented_model_names", lambda: ["gemini-3-pro-preview", "gemini-3.1-pro-preview"])
    monkeypatch.setattr("bettercode.web.api._gemini_cli_model_names", lambda: ["gemini-2.5-pro"])

    claude_registry = web_api._cli_discovered_model_registry("claude")
    gemini_registry = web_api._cli_discovered_model_registry("gemini")

    assert [entry["id"] for entry in claude_registry if "@" not in entry["id"]] == [
        "claude/claude-haiku-4-5",
        "claude/claude-opus-4-6",
        "claude/claude-sonnet-4-6",
    ]
    assert [entry["label"] for entry in claude_registry if "@" not in entry["id"]] == [
        "Claude Haiku 4.5",
        "Claude Opus 4.6",
        "Claude Sonnet 4.6",
    ]
    assert "claude/claude-sonnet-4-6@medium" in {entry["id"] for entry in claude_registry}
    assert [entry["id"] for entry in gemini_registry] == [
        "gemini/gemini-2.5-pro",
        "gemini/gemini-3-pro-preview",
        "gemini/gemini-3.1-pro-preview",
    ]


def test_claude_cli_documented_model_names_reads_active_aliases_and_full_ids(monkeypatch, tmp_path):
    package_dir = tmp_path / "claude-package"
    package_dir.mkdir()
    (package_dir / "cli.js").write_text(
        "\\n".join([
            "## Current Models (recommended)",
            "| Claude Opus 4.6 | \\`claude-opus-4-6\\` | - | 200K | 128K | Active |",
            "| Claude Haiku 4.5 | \\`claude-haiku-4-5\\` | \\`claude-haiku-4-5-20251001\\` | 200K | 64K | Active |",
            "## Legacy Models (still active)",
            "| Claude Sonnet 4.5 | \\`claude-sonnet-4-5\\` | \\`claude-sonnet-4-5-20250929\\` | Active |",
            "## Deprecated Models (retiring soon)",
            "| Claude Haiku 3 | \\`claude-3-haiku-20240307\\` | Deprecated |",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_runtime_package_dir", lambda runtime: package_dir if runtime == "claude" else None)

    assert web_api._claude_cli_documented_model_names() == [
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
    ]


def test_dedupe_claude_model_names_prefers_alias_over_dated_full_id():
    assert web_api._dedupe_claude_model_names([
        "claude-opus-4-20250514",
        "claude-opus-4-0",
        "claude-sonnet-4-5-20250929",
        "claude-sonnet-4-5",
        "claude-haiku-4-5-20251001",
        "claude-haiku-4-5",
    ]) == [
        "claude-haiku-4-5",
        "claude-opus-4-0",
        "claude-sonnet-4-5",
    ]


def test_merge_claude_model_names_prefers_documented_catalog_over_history_duplicates():
    assert web_api._merge_claude_model_names(
        ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-0"],
        ["claude-haiku-4-5-20251001", "claude-sonnet-4-6-20251101", "claude-opus-4-20250514"],
    ) == [
        "claude-haiku-4-5",
        "claude-opus-4-0",
        "claude-sonnet-4-6",
    ]


def test_merge_claude_model_names_keeps_history_only_models_when_not_documented():
    assert web_api._merge_claude_model_names(
        ["claude-sonnet-4-6"],
        ["claude-haiku-4-5-20251001", "claude-sonnet-4-6-20251101"],
    ) == [
        "claude-haiku-4-5",
        "claude-sonnet-4-6",
    ]


def test_runtime_package_dir_resolves_npm_symlink_install(monkeypatch, tmp_path):
    npm_root = tmp_path / ".npm-global"
    bin_dir = npm_root / "bin"
    package_dir = npm_root / "lib" / "node_modules" / "@google" / "gemini-cli"
    dist_dir = package_dir / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.js").write_text("export {};\n", encoding="utf-8")
    bin_dir.mkdir(parents=True)
    (bin_dir / "gemini").symlink_to(Path("../lib/node_modules/@google/gemini-cli/dist/index.js"))
    monkeypatch.setattr(web_api.shutil, "which", lambda runtime: str(bin_dir / runtime) if runtime == "gemini" else None)

    assert web_api._runtime_package_dir("gemini") == package_dir


def test_gemini_cli_documented_model_names_reads_valid_models_from_installed_cli(monkeypatch, tmp_path):
    package_dir = tmp_path / "gemini-package"
    models_dir = package_dir / "node_modules" / "@google" / "gemini-cli-core" / "dist" / "src" / "config"
    models_dir.mkdir(parents=True)
    (models_dir / "models.js").write_text(
        "\n".join([
            "export const PREVIEW_GEMINI_MODEL = 'gemini-3-pro-preview';",
            "export const PREVIEW_GEMINI_3_1_MODEL = 'gemini-3.1-pro-preview';",
            "export const PREVIEW_GEMINI_3_1_CUSTOM_TOOLS_MODEL = 'gemini-3.1-pro-preview-customtools';",
            "export const PREVIEW_GEMINI_FLASH_MODEL = 'gemini-3-flash-preview';",
            "export const PREVIEW_GEMINI_3_1_FLASH_LITE_MODEL = 'gemini-3.1-flash-lite-preview';",
            "export const DEFAULT_GEMINI_MODEL = 'gemini-2.5-pro';",
            "export const DEFAULT_GEMINI_FLASH_MODEL = 'gemini-2.5-flash';",
            "export const DEFAULT_GEMINI_FLASH_LITE_MODEL = 'gemini-2.5-flash-lite';",
            "export const VALID_GEMINI_MODELS = new Set([",
            "    PREVIEW_GEMINI_MODEL,",
            "    PREVIEW_GEMINI_3_1_MODEL,",
            "    PREVIEW_GEMINI_3_1_CUSTOM_TOOLS_MODEL,",
            "    PREVIEW_GEMINI_FLASH_MODEL,",
            "    PREVIEW_GEMINI_3_1_FLASH_LITE_MODEL,",
            "    DEFAULT_GEMINI_MODEL,",
            "    DEFAULT_GEMINI_FLASH_MODEL,",
            "    DEFAULT_GEMINI_FLASH_LITE_MODEL,",
            "]);",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_runtime_package_dir", lambda runtime: package_dir if runtime == "gemini" else None)

    assert web_api._gemini_cli_documented_model_names() == [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-3-pro-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
    ]


def test_resolve_runtime_model_supports_codex_reasoning_variants(monkeypatch):
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })

    runtime, model_name, reasoning_effort = web_api._resolve_runtime_model("codex/gpt-5.4@high")

    assert runtime == "codex"
    assert model_name == "gpt-5.4"
    assert reasoning_effort == "high"


def test_resolve_runtime_model_supports_cursor_default(monkeypatch):
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False},
        "cursor": {"available": True, "path": "/usr/bin/cursor-agent", "configured": True},
        "claude": {"available": False, "path": None, "configured": False},
        "gemini": {"available": False, "path": None, "configured": False},
    })

    runtime, model_name, reasoning_effort = web_api._resolve_runtime_model("cursor/default")

    assert runtime == "cursor"
    assert model_name is None
    assert reasoning_effort is None


def test_build_codex_command_omits_cd_on_resume(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
    })
    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Continue",
        "gpt-5.4",
        "low",
        session_id="session-123",
        json_output=True,
    )

    assert command[:2] == ["codex", "exec"]
    assert "resume" not in command
    assert "-C" in command
    assert "session-123" not in command
    assert command[-1] == "Continue"
    assert "--output-last-message" in command


def test_build_codex_command_supports_resume_when_cli_exposes_it(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": True,
        "supports_color": True,
    })

    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Continue",
        "gpt-5.4",
        "low",
        session_id="session-123",
        json_output=True,
    )

    assert command[:3] == ["codex", "exec", "resume"]
    assert "-C" not in command
    assert "session-123" in command


def test_build_codex_command_supports_terminal_resume_last(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
    })
    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Continue",
        "gpt-5.4",
        "medium",
        session_id=web_api.CODEX_LAST_SESSION_SENTINEL,
        terminal_output=True,
    )

    assert command[:2] == ["codex", "exec"]
    assert "resume" not in command
    assert "--color" in command
    assert "--progress-cursor" not in command
    assert web_api.CODEX_LAST_SESSION_SENTINEL not in command


def test_build_codex_command_supports_terminal_output_on_fresh_exec(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
    })
    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Start",
        "gpt-5.4",
        "medium",
        terminal_output=True,
    )

    assert command[:2] == ["codex", "exec"]
    assert "--color" in command
    assert "--progress-cursor" not in command
    assert "-C" in command
    assert "--output-last-message" in command


def test_build_codex_command_normalizes_xhigh_reasoning(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
    })
    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Start",
        "gpt-5.4",
        "xhigh",
    )

    assert "-c" in command
    assert 'model_reasoning_effort="high"' in command


def test_build_codex_command_uses_dangerous_bypass_when_requested(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
        "supports_dangerous_bypass": True,
    })
    command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Start",
        "gpt-5.4",
        "medium",
        bypass_sandbox=True,
    )

    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--full-auto" not in command


def test_build_codex_command_supports_plan_and_auto_edit_modes(monkeypatch):
    monkeypatch.setattr(web_api, "_codex_exec_capabilities", lambda codex_path, force_refresh=False: {
        "output_flag": "--output-last-message",
        "supports_resume": False,
        "supports_color": True,
        "supports_dangerous_bypass": True,
    })

    plan_command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Plan this",
        "gpt-5.4",
        "medium",
        agent_mode="plan",
    )
    auto_edit_command = web_api._build_codex_command(
        "codex",
        "/workspace",
        "/tmp/output.txt",
        "Edit this",
        "gpt-5.4",
        "medium",
        agent_mode="auto_edit",
    )

    assert ["-a", "never", "-s", "read-only"] == plan_command[plan_command.index("-a"):plan_command.index("-a") + 4]
    assert "--full-auto" not in plan_command
    assert ["-a", "never", "-s", "workspace-write"] == auto_edit_command[auto_edit_command.index("-a"):auto_edit_command.index("-a") + 4]
    assert "--full-auto" not in auto_edit_command


def test_extract_terminal_lines_strips_ansi_and_splits_carriage_returns():
    lines, carry = web_api._extract_terminal_lines("\x1b[32mWorking...\x1b[0m\rDone\nTail", "")

    assert lines == ["Working...", "Done"]
    assert carry == "Tail"


def test_build_claude_command_supports_resume_and_streaming():
    command = web_api._build_claude_command(
        "claude",
        "Continue",
        "sonnet",
        session_id="session-123",
        stream_json=True,
    )

    assert command == [
        "claude",
        "--dangerously-skip-permissions",
        "--resume",
        "session-123",
        "-p",
        "Continue",
        "--model",
        "sonnet",
        "--output-format",
        "stream-json",
    ]


def test_build_claude_command_supports_plan_and_auto_edit_modes():
    plan_command = web_api._build_claude_command(
        "claude",
        "Plan this",
        "sonnet",
        agent_mode="plan",
    )
    auto_edit_command = web_api._build_claude_command(
        "claude",
        "Edit this",
        "sonnet",
        agent_mode="auto_edit",
    )

    assert plan_command[:3] == ["claude", "--permission-mode", "plan"]
    assert auto_edit_command[:3] == ["claude", "--permission-mode", "acceptEdits"]


def test_run_claude_cli_parses_json_response(monkeypatch):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/claude" if command == "claude" else None)
    monkeypatch.setattr(
        "bettercode.web.api._run_external_command",
        lambda command, workspace_path, **_kwargs: _completed(
            command,
            stdout=json.dumps({
                "type": "result",
                "subtype": "success",
                "result": "Claude reply",
                "session_id": "claude-session-1",
                "is_error": False,
            }),
        ),
    )

    payload = web_api._run_claude_cli("/workspace", "Continue", "sonnet")

    assert payload == {
        "reply": "Claude reply",
        "model": "claude/sonnet",
        "runtime": "claude",
        "session_id": "claude-session-1",
    }


def test_run_cursor_cli_parses_json_response(monkeypatch):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/cursor-agent" if command == "cursor-agent" else None)
    monkeypatch.setattr(
        "bettercode.web.api._run_external_command",
        lambda command, workspace_path, **_kwargs: _completed(
            command,
            stdout=json.dumps({
                "type": "result",
                "subtype": "success",
                "result": "Cursor reply",
                "session_id": "cursor-session-1",
                "is_error": False,
            }),
        ),
    )

    payload = web_api._run_cursor_cli("/workspace", "Continue", "gpt-5")

    assert payload == {
        "reply": "Cursor reply",
        "model": "cursor/gpt-5",
        "runtime": "cursor",
        "session_id": "cursor-session-1",
    }


def test_build_gemini_command_supports_agent_modes():
    plan_command = web_api._build_gemini_command("/usr/bin/gemini", "Plan this", "gemini-2.5-pro", agent_mode="plan")
    auto_edit_command = web_api._build_gemini_command("/usr/bin/gemini", "Edit this", "gemini-2.5-pro", agent_mode="auto_edit")
    full_agentic_command = web_api._build_gemini_command("/usr/bin/gemini", "Ship this", "gemini-2.5-pro", agent_mode="full_agentic")

    assert plan_command[:3] == ["/usr/bin/gemini", "--approval-mode", "plan"]
    assert auto_edit_command[:3] == ["/usr/bin/gemini", "--approval-mode", "auto_edit"]
    assert full_agentic_command[:3] == ["/usr/bin/gemini", "--approval-mode", "yolo"]


def test_chat_payload_reuses_workspace_claude_session(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BETTERCODE_HOME", str(tmp_path / ".bettercode"))
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [
        {"id": "claude/default", "label": "Claude Default"},
    ])
    monkeypatch.setattr("bettercode.web.api.manage_workspace_context", lambda db, workspace: False)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False},
        "claude": {"available": True, "path": "/usr/bin/claude", "configured": True},
        "gemini": {"available": False, "path": None, "configured": False},
    })
    captured = {}

    def fake_run_claude_cli(workspace_path, prompt_text, model_name, session_id=None, reasoning_effort=None, agent_mode=None):
        captured["session_id"] = session_id
        return {"reply": "resumed", "model": "claude/default", "runtime": "claude", "session_id": session_id or "claude-session-1"}

    monkeypatch.setattr("bettercode.web.api._run_claude_cli", fake_run_claude_cli)
    init_db()
    _ensure_default_workspace()

    with web_api.SessionLocal() as db:
        workspace = db.query(web_api.Workspace).first()
        tab = db.query(web_api.WorkspaceTab).filter_by(workspace_id=workspace.id).first()
        tab.claude_session_id = "claude-session-123"
        db.commit()
        workspace_id = workspace.id

    payload = chat_payload(workspace_id, "Continue this project", "claude/default")

    assert payload["model"] == "claude/default"
    assert captured["session_id"] == "claude-session-123"


def test_install_runtime_payload_reuses_active_job(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [])
    with web_api.RUNTIME_JOBS_LOCK:
        web_api.RUNTIME_JOBS.clear()
        web_api.RUNTIME_JOBS["job-1"] = {
            "id": "job-1",
            "runtime": "codex",
            "action": "install",
            "status": "running",
            "message": "",
            "output": "",
            "started_at": "2026-03-18T00:00:00",
            "finished_at": "",
        }

    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": True, "path": "/usr/bin/codex", "configured": True, "job": None},
        "claude": {"available": False, "path": None, "configured": False, "job": None},
        "gemini": {"available": False, "path": None, "configured": False, "job": None},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })

    payload = web_api._install_runtime_payload("codex")

    assert payload["job"]["id"] == "job-1"
    assert payload["job"]["action"] == "install"

    with web_api.RUNTIME_JOBS_LOCK:
        web_api.RUNTIME_JOBS.clear()


def test_install_runtime_payload_installs_claude_via_npm(monkeypatch):
    monkeypatch.setitem(web_api.MODEL_DISCOVERY_CACHE, "options", [])
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False, "job": None},
        "claude": {"available": False, "path": None, "configured": False, "job": None},
        "gemini": {"available": False, "path": None, "configured": False, "job": None},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })

    captured = {}

    def fake_spawn_runtime_job(runtime, action, command, workspace_path=None):
        captured["runtime"] = runtime
        captured["action"] = action
        captured["command"] = command
        captured["workspace_path"] = workspace_path
        return {"job": {"id": "job-2", "runtime": runtime, "action": action, "status": "running"}}

    monkeypatch.setattr("bettercode.web.api._spawn_runtime_job", fake_spawn_runtime_job)

    payload = web_api._install_runtime_payload("claude")

    assert payload["job"]["runtime"] == "claude"
    assert payload["job"]["action"] == "install"
    assert captured == {
        "runtime": "claude",
        "action": "install",
        "command": ["/usr/bin/npm", "install", "-g", "@anthropic-ai/claude-code@latest"],
        "workspace_path": None,
    }


def test_terminal_command_uses_terminal_app_on_macos(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        web_api.shutil,
        "which",
        lambda command: "/usr/bin/osascript" if command == "osascript" else None,
    )

    command = web_api._terminal_command(["claude"])

    assert command == [
        "/usr/bin/osascript",
        "-e",
        'tell application "Terminal"',
        "-e",
        "activate",
        "-e",
        'do script "claude"',
        "-e",
        "end tell",
    ]


def test_terminal_command_uses_cmd_start_on_windows(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(web_api.os, "name", "nt", raising=False)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")

    command = web_api._terminal_command(["claude", "login"])

    assert command == [
        r"C:\Windows\System32\cmd.exe",
        "/c",
        "start",
        '""',
        r"C:\Windows\System32\cmd.exe",
        "/k",
        "claude login",
    ]


def test_terminal_command_keeps_linux_shell_open(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        web_api.shutil,
        "which",
        lambda command: "/usr/bin/gnome-terminal" if command == "gnome-terminal" else None,
    )

    command = web_api._terminal_command(["claude"])

    assert command[:4] == ["/usr/bin/gnome-terminal", "--", "bash", "-lc"]
    assert "claude;" in command[4]
    assert "exec bash -i" in command[4]


def test_runtime_login_payload_uses_terminal_app_on_macos(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        web_api.shutil,
        "which",
        lambda command: "/usr/bin/osascript" if command == "osascript" else None,
    )
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False, "job": None},
        "claude": {"available": True, "path": "/usr/local/bin/claude", "configured": False, "job": None},
        "gemini": {"available": False, "path": None, "configured": False, "job": None},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })

    captured = {}

    def fake_spawn_runtime_launch_job(runtime, action, command, workspace_path=None, completion_message=""):
        captured["runtime"] = runtime
        captured["action"] = action
        captured["command"] = command
        captured["workspace_path"] = workspace_path
        captured["completion_message"] = completion_message
        return {"job": {"runtime": runtime, "action": action, "status": "completed", "message": completion_message}}

    monkeypatch.setattr("bettercode.web.api._spawn_runtime_launch_job", fake_spawn_runtime_launch_job)

    payload = web_api.runtime_login_payload("claude")

    assert payload["job"]["runtime"] == "claude"
    assert payload["job"]["action"] == "login"
    assert payload["job"]["status"] == "completed"
    assert captured == {
        "runtime": "claude",
        "action": "login",
        "command": [
            "/usr/bin/osascript",
            "-e",
            'tell application "Terminal"',
            "-e",
            "activate",
            "-e",
            'do script "claude"',
            "-e",
            "end tell",
        ],
        "completion_message": "Opened the runtime login terminal. Complete sign-in there, then refresh status.",
        "workspace_path": None,
    }


def test_runtime_login_payload_launches_immediately_on_windows(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(web_api.os, "name", "nt", raising=False)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False, "job": None},
        "claude": {"available": True, "path": r"C:\claude.cmd", "configured": False, "job": None},
        "gemini": {"available": False, "path": None, "configured": False, "job": None},
        "npm": {"available": True, "path": r"C:\npm.cmd"},
    })

    captured = {}

    def fake_launch(command, workspace_path=None):
        captured["command"] = command
        captured["workspace_path"] = workspace_path

    monkeypatch.setattr("bettercode.web.api._launch_detached_command", fake_launch)

    payload = web_api.runtime_login_payload("claude")

    assert payload["job"]["runtime"] == "claude"
    assert payload["job"]["action"] == "login"
    assert payload["job"]["status"] == "completed"
    assert "Opened the runtime login terminal." in payload["job"]["message"]
    assert captured == {
        "command": [
            r"C:\Windows\System32\cmd.exe",
            "/c",
            "start",
            '""',
            r"C:\Windows\System32\cmd.exe",
            "/k",
            "claude",
        ],
        "workspace_path": None,
    }


def test_runtime_login_payload_requires_linux_terminal_emulator(monkeypatch):
    monkeypatch.setattr(web_api.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(web_api.os, "name", "posix", raising=False)
    monkeypatch.setattr(web_api.shutil, "which", lambda command: None)
    monkeypatch.setattr("bettercode.web.api._cli_runtimes", lambda: {
        "codex": {"available": False, "path": None, "configured": False, "job": None},
        "claude": {"available": True, "path": "/usr/local/bin/claude", "configured": False, "job": None},
        "gemini": {"available": False, "path": None, "configured": False, "job": None},
        "npm": {"available": True, "path": "/usr/bin/npm"},
    })

    with pytest.raises(web_api.HTTPException) as exc:
        web_api.runtime_login_payload("claude")

    assert exc.value.status_code == 400
    assert exc.value.detail == "No supported terminal emulator is available for runtime login."


def test_codex_progress_message_formats_events():
    assert web_api._codex_progress_message('{"type":"thread.started"}') == "Session started."
    assert web_api._codex_progress_message('{"type":"error","message":"Reconnecting..."}') == "Reconnecting..."
    assert "Connection issue:" in web_api._codex_progress_message(
        "2026-03-18T20:03:52.220421Z ERROR codex_api::endpoint::responses_websocket: failed to connect"
    )
    assert web_api._codex_progress_message('{"type":"item.started"}') is None
    assert web_api._codex_progress_message(
        '{"type":"item.started","item":{"type":"shell_command","command":["git","status"]}}'
    ) == "Running shell command: git status"
    assert web_api._codex_progress_message(
        '{"type":"item.completed","item":{"type":"apply_patch"}}'
    ) == "Applying patch"


def test_codex_transcript_line_preserves_cli_trace_details():
    assert web_api._codex_transcript_line('{"type":"thread.started","thread_id":"abc123"}') == "[thread.started] abc123"
    assert web_api._codex_transcript_line(
        '{"type":"item.started","item":{"type":"shell_command","command":["git","status","--short"]}}'
    ) == "[start] $ git status --short"
    assert web_api._codex_transcript_line(
        '{"type":"item.completed","item":{"type":"write_file","path":"bettercode/web/api.py"}}'
    ) == "[done] write_file bettercode/web/api.py"


def test_stream_codex_cli_pty_exits_after_process_finishes_at_eof(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/codex" if command == "codex" else None)
    monkeypatch.setattr("bettercode.web.api._codex_exec_capabilities", lambda _path: {
        "supports_resume": False,
        "supports_color": True,
        "output_flag": "--output-last-message",
    })

    def fake_build_codex_command(codex_path, workspace_path, output_path, prompt_text, model_name, reasoning_effort, **kwargs):
        Path(output_path).write_text("reply from codex", encoding="utf-8")
        return [codex_path, "exec", prompt_text]

    monkeypatch.setattr("bettercode.web.api._build_codex_command", fake_build_codex_command)
    monkeypatch.setattr("bettercode.web.api.os.openpty", lambda: (11, 12))
    monkeypatch.setattr("bettercode.web.api.os.close", lambda _fd: None)

    select_calls = {"count": 0}

    def fake_select(_read, _write, _except, _timeout):
        select_calls["count"] += 1
        if select_calls["count"] <= 2:
            return ([11], [], [])
        raise AssertionError("PTY stream kept polling after process exit.")

    monkeypatch.setattr("bettercode.web.api.select.select", fake_select)

    read_chunks = iter([
        b'{"type":"thread.started","thread_id":"thread-123"}\n',
        b"",
    ])
    monkeypatch.setattr("bettercode.web.api.os.read", lambda _fd, _size: next(read_chunks))

    class FakeProcess:
        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_codex_cli(str(tmp_path), "Fix this", "gpt-5", "high")

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "reply from codex",
        "model": "codex/gpt-5@high",
        "runtime": "codex",
        "session_id": "",
    }
    assert events[0]["type"] == "status"
    assert events[0]["message"].startswith("Starting Codex with codex/gpt-5@high")
    assert any(event["type"] == "terminal_chunk" for event in events)


def test_run_codex_cli_retries_without_sandbox_after_bwrap_failure(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/codex" if command == "codex" else None)
    monkeypatch.setattr("bettercode.web.api._codex_exec_capabilities", lambda _path: {
        "supports_resume": False,
        "supports_color": True,
        "supports_dangerous_bypass": True,
        "output_flag": "--output-last-message",
    })

    attempts = []

    def fake_build_codex_command(codex_path, workspace_path, output_path, prompt_text, model_name, reasoning_effort, **kwargs):
        bypass_sandbox = bool(kwargs.get("bypass_sandbox"))
        attempts.append(bypass_sandbox)
        if bypass_sandbox:
            Path(output_path).write_text("reply from codex", encoding="utf-8")
            return [codex_path, "exec", "bypass", output_path]
        Path(output_path).write_text("", encoding="utf-8")
        return [codex_path, "exec", "sandboxed", output_path]

    monkeypatch.setattr("bettercode.web.api._build_codex_command", fake_build_codex_command)

    class FakeProcess:
        def __init__(self, command):
            self.stdout = iter([
                "2026-04-08T00:57:34.182995Z ERROR codex_core::tools::router: error=exec_command failed: CreateProcess { message: \"Codex(Sandbox(Denied { output: ExecToolCallOutput { stderr: StreamOutput { text: \\\"bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\\\\n\\\" } })\" }\n"
            ]) if "sandboxed" in command else iter([])
            self._returncode = 1 if "sandboxed" in command else 0

        def wait(self, timeout=None):
            return self._returncode

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda command, **kwargs: FakeProcess(command))

    result = web_api._run_codex_cli(str(tmp_path), "Fix this", "gpt-5", "high")

    assert attempts == [False, True]
    assert result == {
        "reply": "reply from codex",
        "model": "codex/gpt-5@high",
        "runtime": "codex",
        "session_id": "",
    }


def test_stream_codex_cli_retries_without_sandbox_after_bwrap_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api.sys, "platform", "win32", raising=False)
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/codex" if command == "codex" else None)
    monkeypatch.setattr("bettercode.web.api._codex_exec_capabilities", lambda _path: {
        "supports_resume": False,
        "supports_color": True,
        "supports_dangerous_bypass": True,
        "output_flag": "--output-last-message",
    })
    monkeypatch.setattr("bettercode.web.api._wait_for_process", lambda process, workspace_id: process.wait())

    attempts = []

    def fake_build_codex_command(codex_path, workspace_path, output_path, prompt_text, model_name, reasoning_effort, **kwargs):
        bypass_sandbox = bool(kwargs.get("bypass_sandbox"))
        attempts.append(bypass_sandbox)
        if bypass_sandbox:
            Path(output_path).write_text("reply from codex", encoding="utf-8")
            return [codex_path, "exec", "bypass", output_path]
        Path(output_path).write_text("", encoding="utf-8")
        return [codex_path, "exec", "sandboxed", output_path]

    monkeypatch.setattr("bettercode.web.api._build_codex_command", fake_build_codex_command)

    class FakeProcess:
        def __init__(self, command):
            self.stdout = iter([
                "2026-04-08T00:57:34.182995Z ERROR codex_core::tools::router: error=exec_command failed: CreateProcess { message: \"Codex(Sandbox(Denied { output: ExecToolCallOutput { stderr: StreamOutput { text: \\\"bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\\\\n\\\" } })\" }\n"
            ]) if "sandboxed" in command else iter([])
            self.stdin = None
            self._returncode = 1 if "sandboxed" in command else 0

        def wait(self, timeout=None):
            return self._returncode

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda command, **kwargs: FakeProcess(command))

    events = []
    generator = web_api._stream_codex_cli(str(tmp_path), "Fix this", "gpt-5", "high")

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert attempts == [False, True]
    assert any(event["type"] == "status" and "Retrying without Codex sandbox" in event["message"] for event in events)
    assert result == {
        "reply": "reply from codex",
        "model": "codex/gpt-5@high",
        "runtime": "codex",
        "session_id": "",
    }


def test_claude_transcript_line_formats_assistant_and_system_events():
    assert web_api._claude_transcript_line({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Implementing the fix now."}]},
    }) == "Claude: Implementing the fix now."
    assert web_api._claude_transcript_line({
        "type": "system",
        "subtype": "tool_use",
    }) == "[system.tool_use]"


def test_extract_claude_terminal_result_payload_reads_final_result_line():
    payload = web_api._extract_claude_terminal_result_payload(
        "Claude session output\n"
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Working..."}]}}\n'
        '{"type":"result","subtype":"success","is_error":false,"result":"done","session_id":"claude-session-1"}\n'
    )

    assert payload == {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "done",
        "session_id": "claude-session-1",
    }


def test_sanitize_claude_terminal_output_removes_trailing_result_json_only():
    raw = (
        "\x1b[32mClaude Sonnet 4.6\x1b[0m\n"
        "Working...\n"
        '{"type":"result","subtype":"success","is_error":false,"result":"20"}\n'
    )

    assert web_api._sanitize_claude_terminal_output(raw) == (
        "\x1b[32mClaude Sonnet 4.6\x1b[0m\n"
        "Working...\n"
    )


def test_sanitize_claude_terminal_output_keeps_non_result_json_lines():
    raw = '{"hello":"world"}\n'

    assert web_api._sanitize_claude_terminal_output(raw) == raw


def test_extract_claude_terminal_result_payload_accepts_result_shape_without_type():
    payload = web_api._extract_claude_terminal_result_payload(
        'Prompt...\n{"result":"done","session_id":"claude-session-1","is_error":false}\n'
    )

    assert payload == {
        "result": "done",
        "session_id": "claude-session-1",
        "is_error": False,
    }


def test_gemini_transcript_line_formats_assistant_and_tool_payloads():
    assert web_api._gemini_transcript_line({
        "type": "message",
        "role": "assistant",
        "content": "Updated the file.",
    }) == "Gemini: Updated the file."
    assert web_api._gemini_transcript_line({
        "type": "tool_use",
        "tool_name": "read_file",
        "parameters": {"path": "bettercode/web/api.py"},
    }) == 'Using read_file: {"path": "bettercode/web/api.py"}'


def test_stream_gemini_cli_emits_raw_terminal_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/gemini" if command == "gemini" else None)
    monkeypatch.setattr("bettercode.web.api._build_gemini_command", lambda *args, **kwargs: ["/usr/bin/gemini", "--output-format", "stream-json"])

    class FakeProcess:
        def __init__(self):
            self.stdout = iter([
                '{"type":"init","model":"gemini-2.5-pro"}\n',
                '{"type":"message","role":"assistant","content":"Updated the file."}\n',
                '{"type":"result"}\n',
            ])
            self.stdin = None

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_gemini_cli(str(tmp_path), "Fix this", "gemini-2.5-pro")

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "Updated the file.",
        "model": "gemini/gemini-2.5-pro",
        "runtime": "gemini",
    }
    assert events[0]["type"] == "terminal_chunk"
    assert events[0]["text"] == '{"type":"init","model":"gemini-2.5-pro"}\n'
    assert any(event["type"] == "terminal_chunk" and '"type":"message"' in event["text"] for event in events)
    assert all(event.get("terminal", "") == "" for event in events if event["type"] == "status")


def test_stream_gemini_cli_prompts_for_input_and_writes_to_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/gemini" if command == "gemini" else None)
    monkeypatch.setattr("bettercode.web.api._build_gemini_command", lambda *args, **kwargs: ["/usr/bin/gemini", "--output-format", "stream-json"])
    monkeypatch.setattr("bettercode.web.api._wait_for_prompt_input", lambda workspace_id, timeout=300.0: "1")

    writes = []

    class FakeStdin:
        def write(self, text):
            writes.append(text)

        def flush(self):
            writes.append("<flush>")

    class FakeProcess:
        def __init__(self):
            self.stdout = iter([
                'Please choose one:\n',
                '{"type":"message","role":"assistant","content":"Done."}\n',
                '{"type":"result"}\n',
            ])
            self.stdin = FakeStdin()
            self.pid = 701

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_gemini_cli(str(tmp_path), "Fix this", "gemini-2.5-pro", workspace_id=7)

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "Done.",
        "model": "gemini/gemini-2.5-pro",
        "runtime": "gemini",
    }
    assert any(event["type"] == "input_required" and event["prompt"] == "Please choose one:" for event in events)
    assert writes == ["1\n", "<flush>"]


def test_stream_cursor_cli_emits_raw_terminal_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/cursor-agent" if command == "cursor-agent" else None)
    monkeypatch.setattr("bettercode.web.api._build_cursor_command", lambda *args, **kwargs: ["/usr/bin/cursor-agent", "--output-format", "stream-json"])

    class FakeProcess:
        def __init__(self):
            self.stdout = iter([
                '{"type":"system","subtype":"init","model":"gpt-5","session_id":"cursor-session-1"}\n',
                '{"type":"assistant","delta":true,"message":{"role":"assistant","content":[{"type":"text","text":"Hello world"}]}}\n',
                '{"type":"result","subtype":"success","result":"Hello world","session_id":"cursor-session-1","is_error":false}\n',
            ])
            self.stdin = None

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_cursor_cli(str(tmp_path), "Fix this", "gpt-5")

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "Hello world",
        "model": "cursor/gpt-5",
        "runtime": "cursor",
        "session_id": "cursor-session-1",
    }
    assert events[0]["type"] == "terminal_chunk"
    assert events[0]["text"] == '{"type":"system","subtype":"init","model":"gpt-5","session_id":"cursor-session-1"}\n'
    assert any(event["type"] == "terminal_chunk" and '"type":"assistant"' in event["text"] for event in events)
    assert all(event.get("terminal", "") == "" for event in events if event["type"] == "status")


def test_stream_cursor_cli_prompts_for_input_and_writes_to_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/cursor-agent" if command == "cursor-agent" else None)
    monkeypatch.setattr("bettercode.web.api._build_cursor_command", lambda *args, **kwargs: ["/usr/bin/cursor-agent", "--output-format", "stream-json"])
    monkeypatch.setattr("bettercode.web.api._wait_for_prompt_input", lambda workspace_id, timeout=300.0: "Yes")

    writes = []

    class FakeStdin:
        def write(self, text):
            writes.append(text)

        def flush(self):
            writes.append("<flush>")

    class FakeProcess:
        def __init__(self):
            self.stdout = iter([
                '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Please choose one:"}]}}\n',
                '{"type":"result","subtype":"success","result":"Done","session_id":"cursor-session-1","is_error":false}\n',
            ])
            self.stdin = FakeStdin()
            self.pid = 801

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_cursor_cli(str(tmp_path), "Fix this", "gpt-5", workspace_id=8)

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "Done",
        "model": "cursor/gpt-5",
        "runtime": "cursor",
        "session_id": "cursor-session-1",
    }
    assert any(event["type"] == "input_required" and event["prompt"] == "Please choose one:" for event in events)
    assert writes == ["Yes\n", "<flush>"]


def test_stream_claude_cli_prompts_for_input_and_writes_to_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr("bettercode.web.api.shutil.which", lambda command: "/usr/bin/claude" if command == "claude" else None)
    monkeypatch.setattr("bettercode.web.api._build_claude_command", lambda *args, **kwargs: ["/usr/bin/claude", "--output-format", "json"])
    monkeypatch.setattr("bettercode.web.api._wait_for_prompt_input", lambda workspace_id, timeout=300.0: "2")
    monkeypatch.setattr(web_api.sys, "platform", "win32")

    writes = []

    class FakeStdin:
        def write(self, text):
            writes.append(text)

        def flush(self):
            writes.append("<flush>")

    class FakeProcess:
        def __init__(self):
            self.stdout = iter([
                b"Please choose one:\n",
                b'{"result":"Done","session_id":"claude-session-1","is_error":false}\n',
            ])
            self.stdin = FakeStdin()
            self.pid = 123

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("bettercode.web.api.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    events = []
    generator = web_api._stream_claude_cli(str(tmp_path), "Fix this", "claude-sonnet", workspace_id=9)

    while True:
        try:
            events.append(json.loads(next(generator).decode("utf-8")))
        except StopIteration as stop:
            result = stop.value
            break

    assert result == {
        "reply": "Done",
        "model": "claude/claude-sonnet",
        "runtime": "claude",
        "session_id": "claude-session-1",
    }
    assert any(event["type"] == "input_required" and event["prompt"] == "Please choose one:" for event in events)
    assert writes == ["2\n", "<flush>"]
