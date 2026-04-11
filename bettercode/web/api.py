import ast
import codecs
import copy
import difflib
import hashlib
import os
import queue
import select
import shlex
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import asynccontextmanager
from pathlib import Path
import json
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Callable, Literal
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import or_

from bettercode import __version__
from bettercode.app_meta import APP_NAME, APP_SLUG
from bettercode.auth import delete_api_key, get_api_key, get_proxy_token, login, set_api_key
from bettercode.context import (
    CodeReview,
    Message,
    RouterTelemetry,
    SessionLocal,
    Workspace,
    WorkspaceTab,
    append_workspace_message_tokens,
    build_memory_context_block,
    build_workspace_context_block,
    clear_memory_entries,
    init_db,
    list_memory_entries,
    manage_workspace_context,
    prune_expired_memory_entries,
    serialize_memory_entry,
    upsert_memory_entries,
)
from bettercode.i18n import language_runtime_instruction, supported_human_languages_payload
from bettercode.web.app_payloads import app_settings_payload, build_app_info_payload
from bettercode.web.artifact_ops import (
    delete_workspace_generated_files as _delete_workspace_generated_files_base,
    generated_files_payload as _generated_files_payload_base,
    mark_generated_files_seen_payload as _mark_generated_files_seen_payload_base,
    open_generated_file_payload as _open_generated_file_payload_base,
    open_telemetry_log_payload as _open_telemetry_log_payload_base,
)
from bettercode.web.bootstrap import _require_selector_for_app_startup, _start_selector_warmup  # noqa: F401
from bettercode.web.chat_processes import (
    ACTIVE_CHAT_PROCESS_META,  # noqa: F401
    ACTIVE_CHAT_PROCESS_META_LOCK,  # noqa: F401
    ACTIVE_CHAT_PROCESSES,
    ACTIVE_CHAT_PROCESSES_LOCK,
    PENDING_CHAT_INPUT,
    PENDING_CHAT_INPUT_LOCK,
    active_chat_status_payload as _active_chat_status_payload_base,
    chat_stop_requested as _chat_stop_requested_base,
    clear_active_chat_process as _clear_active_chat_process_base,
    register_active_chat_process as _register_active_chat_process_base,
    request_chat_stop as _request_chat_stop_base,
    set_chat_input_waiting as _set_chat_input_waiting_base,
    sweep_inactive_chat_processes as _sweep_inactive_chat_processes_base,
    touch_active_chat_process as _touch_active_chat_process_base,
    wait_for_chat_input as _wait_for_chat_input_base,
)
from bettercode.web.chat_context import (
    _build_preprocessed_turn_context as _build_preprocessed_turn_context_base,
    _build_selector_context as _build_selector_context_base,
    _manual_task_analysis as _manual_task_analysis_base,
)
from bettercode.web.generated_paths import (
    _bettercode_home_dir,
    _resolve_generated_file_path,
    _workspace_generated_dir,
    _workspace_generated_staging_dir,
)
from bettercode.web.git_ops import (
    git_commit_payload as _git_commit_payload_base,
    git_fetch_payload as _git_fetch_payload_base,
    git_init_payload as _git_init_payload_base,
    git_pull_payload as _git_pull_payload_base,
    git_push_payload as _git_push_payload_base,
    git_stage_all_payload as _git_stage_all_payload_base,
    git_stage_files_payload as _git_stage_files_payload_base,
    git_status_payload as _git_status_payload_base,
    git_unstage_all_payload as _git_unstage_all_payload_base,
    git_unstage_files_payload as _git_unstage_files_payload_base,
    git_update_payload as _git_update_payload_base,
    review_files_payload as _review_files_payload_base,
)
from bettercode.web.system_actions import (
    build_terminal_command as _build_terminal_command_base,
    kill_process_tree as _kill_process_tree_base,
    launch_detached_command as _launch_detached_command_base,
    open_with_system_default as _open_with_system_default_base,
)
from bettercode.web.telemetry import duration_ms, log_event, recent_events as _recent_telemetry_events, telemetry_info_payload
from bettercode.web.telemetry import telemetry_log_path as _telemetry_log_path
from bettercode.settings import (
    get_app_settings,
    get_enable_follow_up_suggestions,
    get_enable_task_breakdown,
    get_human_language,
    has_explicit_human_language_setting,
    get_local_preprocess_mode,
    get_mock_update_version,
    set_app_settings,
)
from bettercode.router.selector import (
    apply_local_preprocess_runtime_change,
    analyze_routing_task,
    detect_project_run_config,
    installable_local_preprocess_model,
    local_preprocess_model_label,
    maybe_select_local_execution,
    plan_subtasks,
    pull_local_preprocess_model,
    require_selector_runtime,
    run_local_model_response,
    run_local_prompt_enrichment,
    select_best_model,
    select_best_model_heuristic,
    selector_status,
    stop_managed_ollama,
    suggest_follow_up_recommendations,
)
from bettercode.updater import normalize_sha256, normalize_update_platform

STATIC_DIR = Path(__file__).with_name("static")


class ChatStoppedError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class CreateWorkspaceRequest(BaseModel):
    path: str


class CreateWorkspaceFolderRequest(BaseModel):
    parent_path: str
    name: str


class RenameWorkspaceRequest(BaseModel):
    name: str


class SaveApiKeyRequest(BaseModel):
    provider: Literal["openai", "anthropic", "google", "cursor"]
    api_key: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AppSettingsRequest(BaseModel):
    performance_profile: str | None = None
    max_cost_tier: str | None = None
    auto_model_preference: str | None = None
    enable_task_breakdown: bool | None = None
    enable_follow_up_suggestions: bool | None = None
    local_preprocess_mode: str | None = None
    local_preprocess_model: str | None = None
    font_size: str | None = None
    human_language: str | None = None


class SelectorModelInstallRequest(BaseModel):
    model_id: str


class ChatAttachment(BaseModel):
    name: str
    content: str


class ChatRequest(BaseModel):
    workspace_id: int
    tab_id: int | None = None
    text: str = ""
    model: str = "smart"
    agent_mode: str | None = None
    attachments: list[ChatAttachment] = []


class GitCommitRequest(BaseModel):
    message: str


class GitFilesRequest(BaseModel):
    paths: list[str]


class ChatInputRequest(BaseModel):
    text: str


class ChatRetryRequest(BaseModel):
    stream: bool = False


class ReviewRunRequest(BaseModel):
    files: list[str] = []
    depth: str = "standard"
    primary_model: str = "smart"
    secondary_model: str = "none"


class GeneratedFileOpenRequest(BaseModel):
    path: str


class RunStartRequest(BaseModel):
    command: str
    env: dict[str, str] = {}


class UpdateRunSettingsRequest(BaseModel):
    env: dict[str, str] = {}


RUNTIME_PACKAGES = {
    "codex": "@openai/codex",
    "claude": "@anthropic-ai/claude-code",
    "gemini": "@google/gemini-cli",
}
RUNTIME_EXECUTABLES = {
    "codex": "codex",
    "claude": "claude",
    "gemini": "gemini",
    "cursor": "cursor-agent",
}
RUNTIME_LOGOUT_ARGS = {
    "codex": ["logout"],
    "claude": ["logout"],
    "gemini": ["logout"],
    "cursor": ["logout"],
}

MODEL_DISCOVERY_CACHE = {
    "options": None,
    "registry": None,
    "updated_at": 0.0,
    "verified": False,
}
CODEX_LAST_SESSION_SENTINEL = "__bettercode_codex_last__"
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
DEFAULT_TAB_TITLE = "New Tab"
LEGACY_NUMBERED_TAB_RE = re.compile(r"^tab\s+\d+$", re.IGNORECASE)
TAB_TITLE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/#:+-]*")
RUNTIME_JOBS: dict[str, dict] = {}
RUNTIME_JOBS_LOCK = threading.Lock()
ACTIVE_RUN_PROCESSES: dict[int, subprocess.Popen] = {}
ACTIVE_RUN_PROCESSES_LOCK = threading.Lock()
ORCHESTRATED_CHAT_PROCESSES: dict[int, dict[int, subprocess.Popen]] = {}
ORCHESTRATED_CHAT_META: dict[int, dict] = {}
ORCHESTRATED_CHAT_LOCK = threading.Lock()
GIT_STATUS_CACHE: dict[str, dict] = {}
GIT_STATUS_CACHE_LOCK = threading.Lock()
RECENT_FILE_ENTRIES_CACHE: dict[tuple, dict] = {}
RECENT_FILE_ENTRIES_CACHE_LOCK = threading.Lock()
GENERATED_FILE_COUNT_CACHE: dict[str, dict] = {}
GENERATED_FILE_COUNT_CACHE_LOCK = threading.Lock()
RUNTIME_COMMAND_CACHE = {
    "paths": None,
    "updated_at": 0.0,
}
COMMAND_VERSION_CACHE: dict[str, dict] = {}
RUNTIME_LOGIN_CACHE: dict[str, dict] = {}
UPDATE_CHECK_CACHE = {
    "payload": None,
    "updated_at": 0.0,
}
UPDATE_CHECK_CACHE_LOCK = threading.Lock()
MODEL_DISCOVERY_LOCK = threading.Lock()
CODEX_MODELS_CACHE_PATH = Path.home() / ".codex" / "models_cache.json"
CODEX_EXEC_CAPABILITY_CACHE: dict[str, dict] = {}
MODEL_PROBE_TIMEOUT_SECONDS = 12
MODEL_HISTORY_SCAN_LIMIT = 200
MAX_WARM_WORKSPACES = 4
WARM_SESSION_IDLE_MINUTES = 45
MAX_TURN_DIFF_FILES = 16
MAX_TURN_DIFF_LINES = 240
MAX_TURN_DIFF_FALLBACK_BYTES = 131072
MAX_TURN_SNAPSHOT_FILES = 256
MAX_TURN_SNAPSHOT_TOTAL_BYTES = 4 * 1024 * 1024
MAX_TURN_SNAPSHOT_FILE_BYTES = 262144
# Attachment content sent to paid models: 24 000 chars ≈ 6 000 tokens per file.
# Total across all attachments in one turn: 48 000 chars ≈ 12 000 tokens.
MAX_ATTACHMENT_CHARS = 24_000
MAX_ATTACHMENTS_TOTAL_CHARS = 48_000
CHAT_STALL_WARNING_SECONDS = 25
PROCESS_SWEEP_INTERVAL_SECONDS = 10.0
RUNTIME_JOB_RETENTION_SECONDS = 300.0
GIT_STATUS_CACHE_TTL_SECONDS = 2.0
RECENT_FILE_ENTRIES_CACHE_TTL_SECONDS = 6.0
GENERATED_FILE_COUNT_CACHE_TTL_SECONDS = 15.0
UPDATE_CHECK_CACHE_TTL_SECONDS = 1800.0
APP_UPDATE_DOWNLOAD_TIMEOUT_SECONDS = 30.0
APP_UPDATES_DISABLED_MESSAGE = "App updates are currently disabled."
GENERATED_ARTIFACT_DIRS = {
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    "build",
    "coverage",
    "dist",
    "out",
    "storybook-static",
    "target",
}
GENERATED_ARTIFACT_FILES = {
    ".nojekyll",
}
GENERATED_ARTIFACT_SUFFIXES = {
    ".tsbuildinfo",
}
SNAPSHOT_EXCLUDED_DIRS = {
    ".bettercode",
    ".bettercode-generated",
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}
DEFAULT_MESSAGE_PAGE_SIZE = 100
MAX_MESSAGE_PAGE_SIZE = 200
DEFAULT_REVIEW_FILE_LIMIT = 24
MEMORY_REVIEW_MESSAGE_LIMIT = 40
MEMORY_REVIEW_TRANSCRIPT_CHARS = 18_000
MEMORY_INCREMENTAL_TRANSCRIPT_CHARS = 4_000
RUNTIME_COMMAND_CACHE_TTL_SECONDS = 30.0
COMMAND_VERSION_CACHE_TTL_SECONDS = 300.0
MODEL_DISCOVERY_CACHE_TTL_SECONDS = 120.0
VERIFIED_MODEL_DISCOVERY_CACHE_TTL_SECONDS = 600.0
TASK_RESULT_SNIPPET_CHARS = 900
TASK_REPLY_SNIPPET_CHARS = 220
TASK_SYNTHESIS_TIMEOUT_SECONDS = 25.0
MAX_PARALLEL_SUBTASKS = 3
RUNTIME_LOGIN_HINTS = {
    "codex": "Launch the Codex CLI login flow in a terminal and complete the browser/device sign-in.",
    "claude": "Launch Claude Code in a terminal and complete the built-in login flow there.",
    "gemini": "Launch Gemini CLI in a terminal and complete the Google sign-in flow there.",
    "cursor": "Launch Cursor CLI in a terminal and complete the browser login flow there, or save a CURSOR_API_KEY.",
}
RUNTIME_PROVIDER = {
    "codex": "openai",
    "claude": "anthropic",
    "gemini": "google",
    "cursor": "cursor",
}
RUNTIME_AUTH_FILES = {
    "codex": [Path.home() / ".codex" / "auth.json"],
    "claude": [
        Path.home() / ".claude" / "auth.json",
        Path.home() / ".claude" / ".credentials.json",
        Path.home() / ".config" / "claude" / "auth.json",
    ],
    "gemini": [
        Path.home() / ".gemini" / "auth.json",
        Path.home() / ".gemini" / "oauth_creds.json",
        Path.home() / ".config" / "gemini" / "auth.json",
    ],
    "cursor": [
        Path.home() / ".cursor" / "auth.json",
        Path.home() / ".cursor" / ".credentials.json",
        Path.home() / ".config" / "cursor" / "auth.json",
    ],
}
RUNTIME_LOGIN_COMMANDS = {
    "codex": ["codex", "login"],
    "claude": ["claude"],
    "gemini": ["gemini"],
    "cursor": ["cursor-agent", "login"],
}
RUNTIME_TERMINALS = (
    "x-terminal-emulator",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "kitty",
    "wezterm",
    "alacritty",
    "lxterminal",
    "xterm",
)
CLAUDE_STATE_FILE = Path.home() / ".claude.json"
CLAUDE_HISTORY_DIR = Path.home() / ".claude" / "projects"
GEMINI_HISTORY_DIRS = (
    Path.home() / ".gemini" / "tmp",
    Path.home() / ".gemini" / "history",
)


def _http_json_get(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0) -> dict:
    request = urllib_request.Request(url, headers=headers or {}, method="GET")
    with urllib_request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def _label_from_model_name(name: str) -> str:
    text = name.replace("-", " ").replace("_", " ").strip()
    return re.sub(r"\s+", " ", text).title() or name


def _claude_label_from_model_name(name: str) -> str:
    match = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d+)(?:-(\d{8}))?", name)
    if not match:
        dated_zero_match = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d{8})", name)
        if dated_zero_match:
            family, major, dated_suffix = dated_zero_match.groups()
            return f"Claude {family.title()} {major}.0 ({dated_suffix})"
        return _label_from_model_name(name)

    family, major, minor, dated_suffix = match.groups()
    label = f"Claude {family.title()} {major}.{minor}"
    if dated_suffix:
        label += f" ({dated_suffix})"
    return label


def _runtime_model_label(runtime: str, model_name: str) -> str:
    if runtime == "claude":
        return _claude_label_from_model_name(model_name)
    return _label_from_model_name(model_name)


def _reasoning_effort_label(effort: str) -> str:
    return "XHigh" if effort == "xhigh" else effort.title()


_AGENT_MODE_ORDER = ["plan", "auto_edit", "full_agentic"]


def _normalize_agent_mode(raw_mode: str | None) -> str:
    return str(raw_mode or "").strip().lower()


def _sorted_agent_modes(modes: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    seen = set()
    ordered = []
    for mode in _AGENT_MODE_ORDER:
        if mode in modes and mode not in seen:
            seen.add(mode)
            ordered.append(mode)
    for mode in modes:
        normalized = _normalize_agent_mode(mode)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _runtime_agent_modes(runtime: str) -> list[str]:
    if runtime in {"codex", "claude", "gemini"}:
        return ["plan", "auto_edit", "full_agentic"]
    if runtime == "cursor":
        return ["full_agentic"]
    return []


def _default_agent_mode_from_modes(modes: list[str]) -> str:
    ordered = _sorted_agent_modes(modes)
    if "full_agentic" in ordered:
        return "full_agentic"
    if "auto_edit" in ordered:
        return "auto_edit"
    return ordered[0] if ordered else ""


def _runtime_default_agent_mode(runtime: str) -> str:
    return _default_agent_mode_from_modes(_runtime_agent_modes(runtime))


def _runtime_package_dir(runtime: str) -> Path | None:
    executable = shutil.which(runtime)
    if not executable:
        return None

    bin_path = Path(executable).expanduser()
    npm_root = bin_path.parent.parent / "lib" / "node_modules"
    package_name = {
        "claude": "@anthropic-ai/claude-code",
        "gemini": "@google/gemini-cli",
    }.get(runtime)
    if not package_name:
        return None

    package_dir = npm_root / package_name
    if package_dir.exists():
        return package_dir

    resolved_path = bin_path.resolve()
    package_parts = package_name.split("/")
    parents = [resolved_path.parent, *resolved_path.parents]
    for parent in parents:
        if list(parent.parts[-len(package_parts):]) == package_parts:
            return parent

    return None


def _model_family(model_name: str) -> str:
    normalized = model_name.replace("_", "-")
    if normalized.startswith("gpt-"):
        parts = normalized.split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else normalized
    if normalized.startswith("claude-"):
        parts = normalized.split("-")
        return "-".join(parts[:3]) if len(parts) >= 3 else normalized
    if normalized.startswith("gemini-"):
        parts = normalized.split("-")
        return "-".join(parts[:3]) if len(parts) >= 3 else normalized
    return normalized.split("-", 1)[0]


def _model_registry_sort_key(entry: dict) -> tuple:
    model_id = str(entry.get("id") or "")
    _, _, model_name = model_id.partition("/")
    default_rank = 0 if model_name == "default" else 1
    preview_rank = 1 if any(token in model_name for token in ("preview", "exp", "experimental")) else 0
    reasoning_effort = str(entry.get("reasoning_effort") or "")
    # Base model (no effort) sorts first (rank -1), then variants low→medium→high→xhigh→max
    effort_rank = -1 if not reasoning_effort else {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}.get(reasoning_effort, 5)
    return (
        model_id.split("/", 1)[0],
        default_rank,
        preview_rank,
        _model_family(model_name.split("@", 1)[0]) if model_name else "",
        effort_rank,
        str(entry.get("label") or model_id).lower(),
    )


def _dedupe_model_registry(entries: list[dict]) -> list[dict]:
    deduped = {}
    for entry in entries:
        model_id = entry.get("id")
        if model_id and model_id not in deduped:
            deduped[model_id] = entry
    return sorted(deduped.values(), key=_model_registry_sort_key)


def _recent_history_paths(roots: tuple[Path, ...], pattern: str, limit: int = MODEL_HISTORY_SCAN_LIMIT) -> list[Path]:
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob(pattern):
                if path.is_file():
                    candidates.append(path)
        except OSError:
            continue

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    candidates.sort(key=_mtime, reverse=True)
    return candidates[:limit]


def _claude_cli_model_names() -> list[str]:
    models = set()
    for path in _recent_history_paths((CLAUDE_HISTORY_DIR,), "*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        models.update(re.findall(r'"model":"(claude-[^"]+)"', text))
    return sorted(models)


def _claude_cli_documented_model_names() -> list[str]:
    package_dir = _runtime_package_dir("claude")
    if not package_dir:
        return []

    cli_path = package_dir / "cli.js"
    try:
        text = cli_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    start_marker = "## Current Models (recommended)"
    end_marker = "## Deprecated Models (retiring soon)"
    start_index = text.find(start_marker)
    end_index = text.find(end_marker, start_index if start_index >= 0 else 0)
    active_models_block = text[start_index:end_index] if start_index >= 0 and end_index > start_index else text

    return sorted(set(re.findall(r"claude-[a-z0-9-]+", active_models_block)))


def _gemini_cli_model_names() -> list[str]:
    models = set()
    for path in _recent_history_paths(GEMINI_HISTORY_DIRS, "*.json"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        models.update(re.findall(r'"model"\s*:\s*"(gemini-[^"]+)"', text))
    return sorted(models)


def _gemini_cli_documented_model_names() -> list[str]:
    package_dir = _runtime_package_dir("gemini")
    if not package_dir:
        return []

    models_path = package_dir / "node_modules" / "@google" / "gemini-cli-core" / "dist" / "src" / "config" / "models.js"
    try:
        text = models_path.read_text(encoding="utf-8")
    except OSError:
        return []

    exported_models = {
        name: value
        for name, value in re.findall(r"export const ([A-Z0-9_]+) = '(gemini-[^']+)';", text)
    }
    valid_models_match = re.search(r"VALID_GEMINI_MODELS = new Set\(\[(.*?)\]\);", text, flags=re.DOTALL)
    if not valid_models_match:
        return []

    models = {
        exported_models[token]
        for token in re.findall(r"\b[A-Z0-9_]+\b", valid_models_match.group(1))
        if token in exported_models
    }
    return sorted(models)


def _claude_canonical_model_name(name: str) -> str:
    dated_zero_match = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d{8})", name)
    if dated_zero_match:
        family, major, _dated_suffix = dated_zero_match.groups()
        return f"claude-{family}-{major}-0"

    explicit_minor_match = re.fullmatch(r"(claude-[a-z]+-\d+-\d+)(?:-\d{8})?", name)
    if explicit_minor_match:
        return explicit_minor_match.group(1)

    return name


def _dedupe_claude_model_names(model_names: list[str]) -> list[str]:
    canonical = {}
    for name in sorted(set(model_names)):
        key = _claude_canonical_model_name(name)
        preferred = canonical.get(key)
        if preferred is None:
            canonical[key] = name
            continue

        preferred_is_alias = preferred == key
        current_is_alias = name == key
        if current_is_alias and not preferred_is_alias:
            canonical[key] = name
            continue
        if current_is_alias == preferred_is_alias and len(name) < len(preferred):
            canonical[key] = name

    return sorted(canonical.values())


def _merge_claude_model_names(documented_names: list[str], history_names: list[str]) -> list[str]:
    documented = sorted({_claude_canonical_model_name(name) for name in documented_names})
    if not documented:
        return sorted({_claude_canonical_model_name(name) for name in history_names})

    merged = set(documented)
    for name in history_names:
        key = _claude_canonical_model_name(name)
        if key in merged:
            continue
        merged.add(key)
    return sorted(merged)


_CLAUDE_EFFORT_LEVELS = ["low", "medium", "high", "max"]


def _cli_discovered_model_registry(runtime: str) -> list[dict]:
    if runtime == "cursor":
        return [
            _build_model_entry(
                model_id="cursor/default",
                label="Cursor Default",
                provider="cursor",
                runtime="cursor",
                family="default",
                source="cli-local",
            )
        ]
    if runtime == "claude":
        model_names = _merge_claude_model_names(
            _claude_cli_documented_model_names(),
            _claude_cli_model_names(),
        )
    elif runtime == "gemini":
        model_names = sorted(set(_gemini_cli_documented_model_names()) | set(_gemini_cli_model_names()))
    else:
        model_names = []

    if not model_names:
        return []

    provider = RUNTIME_PROVIDER.get(runtime) or runtime
    registry = []
    for model_name in model_names:
        base_label = _runtime_model_label(runtime, model_name)
        registry.append(
            _build_model_entry(
                model_id=f"{runtime}/{model_name}",
                label=base_label,
                provider=provider,
                runtime=runtime,
                family=_model_family(model_name),
                source="cli-local",
            )
        )
        if runtime == "claude":
            for effort in _CLAUDE_EFFORT_LEVELS:
                registry.append(
                    _build_model_entry(
                        model_id=f"{runtime}/{model_name}@{effort}",
                        label=f"{base_label} / {_reasoning_effort_label(effort)}",
                        provider=provider,
                        runtime=runtime,
                        family=_model_family(model_name),
                        source="cli-local",
                        reasoning_effort=effort,
                        supported_reasoning_efforts=_CLAUDE_EFFORT_LEVELS,
                    )
                )
    return _dedupe_model_registry(registry)


def _heuristic_model_metadata(provider: str, model_name: str, reasoning_effort: str | None = None) -> dict:
    lower = model_name.lower()
    cost_tier = "medium"
    speed_tier = "medium"
    capability_tier = "high"
    stability = "stable"
    suggested_uses = ["general coding"]

    if "preview" in lower or "exp" in lower or "experimental" in lower:
        stability = "preview"

    if any(token in lower for token in ("low", "mini", "flash-lite", "flash", "haiku")):
        cost_tier = "low"
        speed_tier = "high"
        capability_tier = "medium"
        suggested_uses = ["small edits", "quick answers", "cheap fast-path"]
    elif any(token in lower for token in ("high", "xhigh", "opus", "pro")):
        cost_tier = "high"
        speed_tier = "medium"
        capability_tier = "very_high"
        suggested_uses = ["debugging", "large edits", "review", "multi-file work"]
    elif any(token in lower for token in ("sonnet", "default")):
        cost_tier = "medium"
        speed_tier = "medium"
        capability_tier = "high"
        suggested_uses = ["general coding", "standard implementation"]

    if provider == "openai" and model_name.startswith("gpt-5.4"):
        capability_tier = "very_high" if reasoning_effort in {"high", "xhigh"} else "high"
        cost_tier = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}.get(reasoning_effort or "medium", cost_tier)
        speed_tier = {"low": "high", "medium": "medium", "high": "medium", "xhigh": "low"}.get(reasoning_effort or "medium", speed_tier)
        suggested_uses = {
            "low": ["small edits", "quick fixes"],
            "medium": ["general coding", "standard implementation"],
            "high": ["debugging", "multi-file edits", "reviews"],
            "xhigh": ["architecture", "deep reasoning", "hard debugging"],
        }.get(reasoning_effort or "medium", suggested_uses)
    elif provider == "openai" and reasoning_effort:
        effort = reasoning_effort.lower()
        capability_tier = "very_high" if effort in {"high", "xhigh"} else "high"
        cost_tier = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}.get(effort, cost_tier)
        speed_tier = {"low": "high", "medium": "medium", "high": "medium", "xhigh": "low"}.get(effort, speed_tier)
        suggested_uses = {
            "low": ["small edits", "quick fixes"],
            "medium": ["general coding", "standard implementation"],
            "high": ["debugging", "multi-file edits", "reviews"],
            "xhigh": ["architecture", "deep reasoning", "hard debugging"],
        }.get(effort, suggested_uses)
    elif provider == "openai" and any(token in lower for token in ("mini", "nano")):
        cost_tier = "low"
        speed_tier = "high"
        capability_tier = "medium" if "mini" in lower else "low"
        suggested_uses = ["small edits", "quick answers", "cheap fast-path"]
    elif provider == "anthropic":
        if "opus" in lower:
            cost_tier = "high"
            speed_tier = "medium"
            capability_tier = "very_high"
            suggested_uses = ["advanced coding", "complex reasoning", "architecture", "debugging", "review", "multi-file work"]
        elif "sonnet" in lower:
            cost_tier = "medium"
            speed_tier = "medium"
            capability_tier = "high"
            suggested_uses = ["general coding", "balanced implementation", "debugging", "review", "multi-file work"]
        elif "haiku" in lower:
            cost_tier = "low"
            speed_tier = "high"
            capability_tier = "medium"
            suggested_uses = ["small edits", "fast responses", "cheap fast-path"]
        if reasoning_effort:
            effort = reasoning_effort.lower()
            capability_tier = "very_high" if effort in {"high", "max", "xhigh"} else capability_tier
            cost_tier = {"low": "low", "medium": cost_tier, "high": "high", "max": "high", "xhigh": "high"}.get(effort, cost_tier)
            speed_tier = {"low": "high", "medium": "medium", "high": "medium", "max": "low", "xhigh": "low"}.get(effort, speed_tier)
            suggested_uses = {
                "low": ["small edits", "quick answers", "fast responses"],
                "medium": suggested_uses,
                "high": ["debugging", "multi-file edits", "review", "deep reasoning"],
                "max": ["architecture", "complex reasoning", "hard debugging", "multi-file work"],
                "xhigh": ["architecture", "complex reasoning", "hard debugging", "multi-file work"],
            }.get(effort, suggested_uses)
    elif provider == "google":
        if "flash-lite" in lower:
            cost_tier = "low"
            speed_tier = "high"
            capability_tier = "medium"
            suggested_uses = ["small edits", "high-volume tasks", "cheap fast-path"]
        elif "flash" in lower:
            cost_tier = "low"
            speed_tier = "high"
            capability_tier = "high"
            suggested_uses = ["low-latency reasoning", "general coding", "high-volume tasks", "quick debugging"]
        elif "pro" in lower:
            cost_tier = "high"
            speed_tier = "medium"
            capability_tier = "very_high"
            suggested_uses = ["deep reasoning", "complex coding", "architecture", "review", "multi-file work"]

    return {
        "family": _model_family(model_name),
        "cost_tier": cost_tier,
        "speed_tier": speed_tier,
        "capability_tier": capability_tier,
        "stability": stability,
        "suggested_uses": suggested_uses,
    }


def _build_model_entry(
    *,
    model_id: str,
    label: str,
    provider: str,
    runtime: str,
    family: str | None = None,
    reasoning_effort: str | None = None,
    default_reasoning_effort: str | None = None,
    supported_reasoning_efforts: list[str] | None = None,
    agent_modes: list[str] | None = None,
    default_agent_mode: str | None = None,
    context_window: int | None = None,
    output_token_limit: int | None = None,
    tool_support: list[str] | None = None,
    multimodal: bool | None = None,
    cost_tier: str | None = None,
    speed_tier: str | None = None,
    capability_tier: str | None = None,
    stability: str | None = None,
    suggested_uses: list[str] | None = None,
    source: str = "heuristic",
) -> dict:
    model_name = model_id.split("/", 1)[1] if "/" in model_id else model_id
    heuristics = _heuristic_model_metadata(provider, model_name, reasoning_effort)
    resolved_agent_modes = _sorted_agent_modes(agent_modes or _runtime_agent_modes(runtime))
    return {
        "id": model_id,
        "label": label,
        "provider": provider,
        "runtime": runtime,
        "family": family or heuristics["family"],
        "reasoning_effort": reasoning_effort,
        "default_reasoning_effort": default_reasoning_effort,
        "supported_reasoning_efforts": supported_reasoning_efforts or [],
        "agent_modes": resolved_agent_modes,
        "default_agent_mode": default_agent_mode or _default_agent_mode_from_modes(resolved_agent_modes),
        "context_window": context_window,
        "output_token_limit": output_token_limit,
        "tool_support": tool_support or [],
        "multimodal": bool(multimodal),
        "cost_tier": cost_tier or heuristics["cost_tier"],
        "speed_tier": speed_tier or heuristics["speed_tier"],
        "capability_tier": capability_tier or heuristics["capability_tier"],
        "stability": stability or heuristics["stability"],
        "suggested_uses": suggested_uses or heuristics["suggested_uses"],
        "source": source,
    }


def _serialize_workspace(workspace: Workspace) -> dict:
    active_tabs = _sorted_workspace_tabs(workspace.tabs or [], archived=False)
    archived_tabs = _sorted_workspace_tabs(workspace.tabs or [], archived=True)
    display_tab = _workspace_display_tab(active_tabs)
    generated_files_count = _workspace_generated_file_count(workspace)
    has_context = _tab_has_context(display_tab) or bool((getattr(workspace, "context_summary", "") or "").strip())
    last_model = (
        display_tab.last_model if display_tab is not None and (display_tab.last_model or "").strip()
        else getattr(workspace, "last_model", "") or ""
    )
    last_runtime = (
        display_tab.last_runtime if display_tab is not None and (display_tab.last_runtime or "").strip()
        else getattr(workspace, "last_runtime", "") or ""
    )
    session_runtime = _tab_session_runtime(display_tab) or last_runtime
    return {
        "id": workspace.id,
        "name": workspace.name,
        "path": workspace.path,
        "session_state": display_tab.session_state if display_tab is not None else "cold",
        "has_session": _workspace_has_session(display_tab),
        "has_context": has_context,
        "session_runtime": session_runtime,
        "last_model": last_model,
        "last_runtime": last_runtime,
        "has_generated_files": generated_files_count > 0,
        "generated_files_count": generated_files_count,
        "generated_files_seen_count": int(getattr(workspace, "generated_files_seen_count", 0) or 0),
        "generated_files_unseen_count": max(
            0,
            generated_files_count - int(getattr(workspace, "generated_files_seen_count", 0) or 0),
        ),
        "last_used_at": workspace.last_used_at.isoformat() if workspace.last_used_at else None,
        "created_at": workspace.created_at.isoformat(),
        "tabs": [_serialize_tab(tab) for tab in active_tabs],
        "tab_history": [_serialize_tab(tab) for tab in archived_tabs],
    }


def _sorted_workspace_tabs(tabs: list[WorkspaceTab], archived: bool) -> list[WorkspaceTab]:
    filtered = [tab for tab in tabs if bool(tab.archived_at) is archived]
    if archived:
        return sorted(
            filtered,
            key=lambda tab: (
                _coerce_utc(tab.archived_at) or _coerce_utc(tab.updated_at) or _coerce_utc(tab.created_at) or _utcnow(),
                tab.id,
            ),
            reverse=True,
        )
    return sorted(filtered, key=lambda tab: (int(tab.sort_order or 0), tab.id))


def _workspace_display_tab(tabs: list[WorkspaceTab]) -> WorkspaceTab | None:
    if not tabs:
        return None
    return max(
        tabs,
        key=lambda tab: (
            _coerce_utc(tab.last_used_at) or _coerce_utc(tab.updated_at) or _coerce_utc(tab.created_at) or _utcnow(),
            tab.id,
        ),
    )


def _tab_session_runtime(tab: WorkspaceTab | None) -> str:
    if tab is None:
        return ""
    return tab.last_runtime or (
        "codex" if tab.codex_session_id
        else "cursor" if getattr(tab, "cursor_session_id", "")
        else "claude" if tab.claude_session_id
        else ""
    )


def _tab_has_context(tab: WorkspaceTab | None) -> bool:
    if tab is None:
        return False
    return bool((tab.context_summary or "").strip() or int(tab.active_message_tokens or 0) > 0)


def _serialize_tab(tab: WorkspaceTab) -> dict:
    return {
        "id": tab.id,
        "workspace_id": tab.workspace_id,
        "title": tab.title or DEFAULT_TAB_TITLE,
        "sort_order": int(tab.sort_order or 0),
        "archived": bool(tab.archived_at),
        "archived_at": tab.archived_at.isoformat() if tab.archived_at else None,
        "session_state": tab.session_state or "cold",
        "has_session": _workspace_has_session(tab),
        "has_context": _tab_has_context(tab),
        "session_runtime": _tab_session_runtime(tab),
        "last_model": tab.last_model or "",
        "last_runtime": tab.last_runtime or "",
        "last_used_at": tab.last_used_at.isoformat() if tab.last_used_at else None,
        "created_at": tab.created_at.isoformat() if tab.created_at else None,
        "updated_at": tab.updated_at.isoformat() if tab.updated_at else None,
    }


def _serialize_message(message: Message) -> dict:
    activity_log = _deserialize_json_list(message.activity_log)
    history_log = _deserialize_json_list(message.history_log)
    change_log = _deserialize_json_list(message.change_log)
    recommendations = _deserialize_json_list(message.recommendations)
    routing_meta = _deserialize_json_object(message.routing_meta)

    return {
        "id": message.id,
        "tab_id": message.tab_id,
        "role": message.role,
        "content": message.content,
        "activity_log": activity_log,
        "history_log": history_log,
        "terminal_log": message.terminal_log or "",
        "change_log": change_log,
        "recommendations": recommendations,
        "routing_meta": routing_meta,
        "created_at": message.created_at.isoformat(),
    }


def _persist_workspace_message(db, workspace: Workspace, tab: WorkspaceTab, role: str, content: str, **fields) -> Message:
    message = Message(
        workspace_id=workspace.id,
        tab_id=tab.id,
        role=role,
        content=content,
        token_count=append_workspace_message_tokens(workspace, content, tab=tab),
        **fields,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    db.refresh(tab)
    return message


def _auth_status() -> dict:
    return {
        "has_anthropic_key": bool(get_api_key("anthropic")),
        "has_cursor_key": bool(get_api_key("cursor")),
        "has_google_key": bool(get_api_key("google")),
        "has_openai_key": bool(get_api_key("openai")),
        "has_subscription": bool(get_proxy_token()),
    }


def _deserialize_json_list(raw_value: str | None) -> list:
    if not raw_value:
        return []
    try:
        value = json.loads(raw_value)
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _deserialize_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _memory_bucket_label(bucket: str) -> str:
    return {
        "short": "Short-term",
        "medium": "Medium-term",
        "long": "Long-term",
    }.get(bucket, bucket.title())


def _memory_command(text: str) -> dict | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    match = re.fullmatch(r"/memory(?:\s+(.*))?", stripped, flags=re.IGNORECASE)
    if not match:
        return None
    args = (match.group(1) or "").strip().lower()
    if not args or args == "review":
        return {"action": "review"}
    if args in {"show", "list", "status"}:
        return {"action": "show"}
    if args.startswith("clear"):
        parts = args.split()
        bucket = parts[1] if len(parts) > 1 else "all"
        if bucket not in {"all", "short", "medium", "long"}:
            raise HTTPException(
                status_code=400,
                detail="Use /memory, /memory show, or /memory clear [short|medium|long|all].",
            )
        return {"action": "clear", "bucket": bucket}
    raise HTTPException(
        status_code=400,
        detail="Use /memory, /memory show, or /memory clear [short|medium|long|all].",
    )


def _memory_review_messages(
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    limit: int = MEMORY_REVIEW_MESSAGE_LIMIT,
) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.workspace_id == workspace.id, Message.tab_id == tab.id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )


def _messages_transcript(messages: list[Message], max_chars: int) -> str:
    ordered = list(reversed(messages))
    lines = [f"{message.role}: {message.content}" for message in ordered if (message.content or "").strip()]
    transcript = "\n".join(lines).strip()
    if len(transcript) <= max_chars:
        return transcript
    return "… [earlier chat trimmed]\n" + transcript[-max_chars:]


def _parse_memory_review_response(raw_text: str) -> list[dict]:
    if not raw_text:
        return []
    try:
        payload = json.loads(raw_text)
    except Exception:
        try:
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            payload = json.loads(raw_text[start:end]) if start >= 0 and end > start else {}
        except Exception:
            payload = {}
    memories = payload.get("memories") if isinstance(payload, dict) else []
    if not isinstance(memories, list):
        return []
    entries = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        bucket = str(item.get("bucket") or "").strip().lower()
        kind = str(item.get("kind") or "").strip().lower()
        content = " ".join(str(item.get("content") or "").split()).strip()
        if bucket not in {"short", "medium", "long"} or len(content) < 8:
            continue
        entries.append({"bucket": bucket, "kind": kind or "fact", "content": content[:400]})
    return entries


def _memory_review_prompt(
    transcript: str,
    existing_memory: list[dict],
    mode: str,
) -> str:
    mode_label = "full current-chat review" if mode == "review" else "incremental turn review"
    return (
        "Review this coding chat and decide what should be stored as memory.\n"
        f"Mode: {mode_label}.\n"
        "Return ONLY a JSON object with this shape:\n"
        '{"memories":[{"bucket":"short|medium|long","kind":"preference|constraint|task|project|fact","content":"memory text"}]}\n\n'
        "Bucket rules:\n"
        "- short: active-session context, immediate next steps, temporary working facts.\n"
        "- medium: useful for the next 48 hours, such as the active bug, branch focus, or temporary project constraints.\n"
        "- long: durable user preferences, persistent project conventions, or facts that should survive until cleared.\n\n"
        "Kind rules:\n"
        "- preference: user style or behavioral preferences.\n"
        "- constraint: rules or limitations that should be respected.\n"
        "- task: current work, next steps, or active focus.\n"
        "- project: repo structure, files, branch, architecture, or project-specific facts.\n"
        "- fact: other useful durable facts.\n\n"
        "Rules:\n"
        "- Store only concrete details that will help future turns.\n"
        "- Skip filler, greetings, generic summaries, copied code, and transient status messages.\n"
        "- Prefer 0 to 6 memory items total.\n"
        "- Keep each content string under 160 characters.\n"
        "- Do not repeat an existing memory unless the stronger bucket is clearly warranted.\n\n"
        "Existing memory:\n"
        f"{json.dumps(existing_memory, ensure_ascii=True)}\n\n"
        "Conversation:\n"
        f"{transcript}"
    )


def _review_chat_memory(
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    *,
    mode: str,
    transcript: str,
) -> tuple[list[dict], dict | None]:
    existing_memory = [
        {"bucket": entry.bucket, "kind": entry.kind or "fact", "content": entry.content}
        for entry in list_memory_entries(db, workspace, tab)
    ]
    prompt = _memory_review_prompt(transcript, existing_memory, mode)
    result = run_local_model_response(
        prompt,
        timeout=45.0 if mode == "review" else 20.0,
        human_language=get_human_language(),
    )
    parsed_entries = _parse_memory_review_response(result.get("reply", ""))
    stored_entries = upsert_memory_entries(db, workspace, tab, parsed_entries, source=mode)
    return [serialize_memory_entry(entry) for entry in stored_entries], result


def _memory_text_response(entries: list[dict]) -> str:
    if not entries:
        return "No active memory saved for this chat."
    grouped = {"short": [], "medium": [], "long": []}
    for entry in entries:
        bucket = str(entry.get("bucket") or "").strip().lower()
        if bucket in grouped:
            kind = str(entry.get("kind") or "fact").strip().lower()
            grouped[bucket].append(f"[{kind}] {str(entry.get('content') or '').strip()}")
    lines = ["Current chat memory:"]
    for bucket in ("short", "medium", "long"):
        items = grouped[bucket]
        if not items:
            continue
        lines.append(f"{_memory_bucket_label(bucket)}:")
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def _memory_review_response_text(entries: list[dict]) -> str:
    if not entries:
        return "No new memory was added from this chat review."
    lines = ["Memory updated:"]
    for bucket in ("short", "medium", "long"):
        bucket_items = [entry for entry in entries if entry.get("bucket") == bucket]
        if not bucket_items:
            continue
        lines.append(f"{_memory_bucket_label(bucket)}:")
        lines.extend(f"- [{entry.get('kind') or 'fact'}] {entry['content']}" for entry in bucket_items)
    return "\n".join(lines)


def _memory_clear_response_text(bucket: str, deleted: int) -> str:
    if deleted <= 0:
        if bucket == "all":
            return "No memory was cleared for this chat."
        return f"No {_memory_bucket_label(bucket).lower()} memory was cleared for this chat."
    if bucket == "all":
        return f"Cleared {deleted} memory item{'s' if deleted != 1 else ''} for this chat."
    return f"Cleared {deleted} {_memory_bucket_label(bucket).lower()} memory item{'s' if deleted != 1 else ''} for this chat."


def _runtime_job_payload(job: dict | None) -> dict | None:
    if not job:
        return None
    return {
        "id": job["id"],
        "runtime": job["runtime"],
        "action": job["action"],
        "status": job["status"],
        "message": job.get("message") or "",
        "output": job.get("output") or "",
        "started_at": job.get("started_at") or "",
        "finished_at": job.get("finished_at") or "",
    }


def _active_runtime_job(runtime: str) -> dict | None:
    with RUNTIME_JOBS_LOCK:
        for job in RUNTIME_JOBS.values():
            if job["runtime"] == runtime and job["status"] == "running":
                return dict(job)
    return None


def _runtime_job_or_404(job_id: str) -> dict:
    with RUNTIME_JOBS_LOCK:
        job = RUNTIME_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Runtime job not found.")
        return dict(job)


def _clear_model_discovery_cache():
    with MODEL_DISCOVERY_LOCK:
        MODEL_DISCOVERY_CACHE["registry"] = None
        MODEL_DISCOVERY_CACHE["options"] = None
        MODEL_DISCOVERY_CACHE["updated_at"] = 0.0
        MODEL_DISCOVERY_CACHE["verified"] = False


def _invalidate_runtime_caches():
    RUNTIME_COMMAND_CACHE["paths"] = None
    RUNTIME_COMMAND_CACHE["updated_at"] = 0.0
    COMMAND_VERSION_CACHE.clear()
    RUNTIME_LOGIN_CACHE.clear()


def _model_discovery_cache_is_fresh(verified_required: bool = False) -> bool:
    if MODEL_DISCOVERY_CACHE.get("registry") is None or MODEL_DISCOVERY_CACHE.get("options") is None:
        return False
    updated_at = float(MODEL_DISCOVERY_CACHE.get("updated_at") or 0.0)
    if updated_at <= 0:
        return True
    ttl = VERIFIED_MODEL_DISCOVERY_CACHE_TTL_SECONDS if MODEL_DISCOVERY_CACHE.get("verified") else MODEL_DISCOVERY_CACHE_TTL_SECONDS
    if verified_required and not MODEL_DISCOVERY_CACHE.get("verified"):
        return False
    return (time.monotonic() - updated_at) < ttl


def _cached_runtime_paths(force_refresh: bool = False) -> dict[str, str | None]:
    now = time.monotonic()
    cached = RUNTIME_COMMAND_CACHE.get("paths")
    updated_at = float(RUNTIME_COMMAND_CACHE.get("updated_at") or 0.0)
    if not force_refresh and cached is not None and (now - updated_at) < RUNTIME_COMMAND_CACHE_TTL_SECONDS:
        return dict(cached)

    paths = {
        "codex": shutil.which("codex"),
        "claude": shutil.which("claude"),
        "gemini": shutil.which("gemini"),
        "cursor": shutil.which("cursor-agent"),
        "npm": shutil.which("npm"),
    }
    RUNTIME_COMMAND_CACHE["paths"] = dict(paths)
    RUNTIME_COMMAND_CACHE["updated_at"] = now
    return paths


def _refresh_model_discovery_cache(verified: bool = True):
    try:
        if verified:
            refresh_model_options_payload(force_refresh=True)
        else:
            _model_options()
    except Exception:
        _clear_model_discovery_cache()


def _start_update_check_warmup() -> threading.Thread:
    def _run():
        time.sleep(20)  # Let startup finish before hitting the network
        while True:
            try:
                app_update_payload(force_refresh=False)
            except Exception:
                pass
            time.sleep(UPDATE_CHECK_CACHE_TTL_SECONDS)

    thread = threading.Thread(target=_run, daemon=True, name="bettercode-update-check")
    thread.start()
    return thread


def _start_model_discovery_warmup(verified: bool = False) -> threading.Thread:
    thread = threading.Thread(
        target=_refresh_model_discovery_cache,
        kwargs={"verified": verified},
        daemon=True,
        name="bettercode-model-warmup",
    )
    thread.start()
    return thread


def update_check_cached_payload() -> dict | None:
    with UPDATE_CHECK_CACHE_LOCK:
        payload = UPDATE_CHECK_CACHE.get("payload")
        return dict(payload) if isinstance(payload, dict) else None


def _disabled_app_update_payload() -> dict:
    return {
        "enabled": False,
        "source": "disabled",
        "update_available": False,
        "latest_version": None,
        "release_name": "",
        "release_url": "",
        "download_url": "",
        "asset_name": "",
        "sha256": "",
        "error": APP_UPDATES_DISABLED_MESSAGE,
    }


def _mock_app_update_payload() -> dict | None:
    latest_version = get_mock_update_version()
    if not latest_version:
        return None

    platform = normalize_update_platform(sys.platform)
    if platform == "macos":
        suffix = ".dmg"
    elif platform == "windows":
        suffix = ".exe"
    else:
        suffix = ".AppImage"

    asset_name = f"{APP_NAME}-{latest_version}{suffix}"
    download_url = f"https://example.invalid/{asset_name}"
    return {
        "source": "mock",
        "mock": True,
        "manifest_url": "",
        "channel": "stable",
        "platform": platform,
        "current_version": __version__,
        "checked_at": datetime.now(UTC).isoformat(),
        "update_available": True,
        "latest_version": latest_version,
        "release_name": f"{APP_NAME} {latest_version}",
        "release_url": download_url,
        "download_url": download_url,
        "asset_name": asset_name,
        "sha256": "0" * 64,
        "error": "",
    }


def app_update_payload(force_refresh: bool = False) -> dict:
    del force_refresh
    return _disabled_app_update_payload()


def _app_update_download_dir() -> Path:
    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.is_dir():
        return downloads_dir / APP_NAME
    return _bettercode_home_dir() / "downloads"


def _app_update_asset_name(update_payload: dict) -> str:
    explicit_name = Path(str(update_payload.get("asset_name") or "")).name.strip()
    if explicit_name:
        return explicit_name

    download_url = str(update_payload.get("download_url") or "").strip()
    parsed_name = Path(urllib_parse.urlparse(download_url).path).name.strip()
    if parsed_name:
        return parsed_name

    latest_version = str(update_payload.get("latest_version") or "").strip()
    if latest_version:
        return f"{APP_SLUG}-{latest_version}"
    return f"{APP_SLUG}-update"


def _verify_downloaded_update_asset(path: Path, expected_sha256: str | None) -> None:
    normalized_sha256 = normalize_sha256(expected_sha256)
    if not normalized_sha256:
        raise HTTPException(status_code=409, detail="No verified installer is available for this platform.")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to verify the downloaded update: {exc}") from exc
    if digest.hexdigest() != normalized_sha256:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=502, detail="Downloaded app update failed checksum verification.")


def _download_update_asset(
    download_url: str,
    destination: Path,
    *,
    timeout: float = APP_UPDATE_DOWNLOAD_TIMEOUT_SECONDS,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.name}.download")
    request = urllib_request.Request(
        download_url,
        headers={"User-Agent": f"BetterCode/{__version__}"},
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response, temp_path.open("wb") as output_file:
            shutil.copyfileobj(response, output_file)
        temp_path.replace(destination)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=502, detail=f"Unable to download app update: {exc}") from exc
    return destination


def _launch_downloaded_update_asset(path: Path) -> None:
    if not path.exists():
        raise HTTPException(status_code=500, detail="Downloaded app update could not be found.")
    if sys.platform.startswith("linux") and path.suffix.lower() == ".appimage":
        try:
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Unable to mark the downloaded update as executable: {exc}") from exc
        _launch_detached_command([str(path)])
        return
    _open_with_system_default(path)


def app_update_install_payload(force_refresh: bool = True) -> dict:
    del force_refresh
    raise HTTPException(status_code=409, detail=APP_UPDATES_DISABLED_MESSAGE)


def _workspace_generated_file_entries(workspace: Workspace | int) -> list[dict]:
    generated_root = _workspace_generated_dir(workspace, create=False)
    if not generated_root.exists():
        return []

    items = []
    for root, dirs, files in os.walk(generated_root, topdown=True):
        dirs[:] = sorted(dirs)
        root_path = Path(root)
        for filename in sorted(files):
            file_path = root_path / filename
            signature = _file_stat_signature(file_path)
            if not signature:
                continue
            items.append({
                "path": str(file_path.relative_to(generated_root)),
                "name": file_path.name,
                "absolute_path": str(file_path),
                "size": int(signature["size"]),
                "modified_at": datetime.fromtimestamp(int(signature["mtime_ns"]) / 1_000_000_000).isoformat(),
                "_mtime_ns": int(signature["mtime_ns"]),
            })

    items.sort(key=lambda item: (item["_mtime_ns"], item["path"]), reverse=True)
    for item in items:
        item.pop("_mtime_ns", None)
    return items


def _workspace_generated_file_count(workspace: Workspace | int) -> int:
    workspace_id = workspace if isinstance(workspace, int) else workspace.id
    cache_key = f"gen_count:{workspace_id}"
    cached = _cache_get(GENERATED_FILE_COUNT_CACHE, GENERATED_FILE_COUNT_CACHE_LOCK, cache_key, GENERATED_FILE_COUNT_CACHE_TTL_SECONDS)
    if cached is not None:
        return int(cached)
    count = len(_workspace_generated_file_entries(workspace))
    _cache_set(GENERATED_FILE_COUNT_CACHE, GENERATED_FILE_COUNT_CACHE_LOCK, cache_key, count)
    return count


def _invalidate_generated_file_count_cache(workspace_id: int) -> None:
    cache_key = f"gen_count:{workspace_id}"
    with GENERATED_FILE_COUNT_CACHE_LOCK:
        GENERATED_FILE_COUNT_CACHE.pop(cache_key, None)


def _normalize_workspace_path(raw_path: str) -> str:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="Workspace path must point to an existing directory.")
    return str(path)


def _normalize_workspace_name(raw_name: str) -> str:
    name = " ".join(raw_name.split()).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Workspace name cannot be empty.")
    return name


def _normalize_workspace_folder_name(raw_name: str) -> str:
    name = _normalize_workspace_name(raw_name)
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Project name must be a single directory name.")
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1:
        raise HTTPException(status_code=400, detail="Project name must be a single directory name.")
    return name


def _resolve_workspace_relative_path(
    workspace_path: str,
    relative_path: str,
    *,
    require_file: bool = False,
) -> Path:
    normalized = str(relative_path or "").strip().replace("\\", "/")
    if not normalized:
        raise HTTPException(status_code=400, detail="File path is required.")

    relative = Path(normalized)
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="File path must be relative to the workspace.")

    workspace_root = Path(workspace_path).resolve()
    candidate = (workspace_root / relative).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="File path must stay inside the workspace.") from exc

    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {normalized}")
    if require_file and not candidate.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {normalized}")
    return candidate


def _normalize_commit_message(raw_message: str) -> str:
    message = raw_message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Commit message cannot be empty.")
    return message


def _normalize_chat_text(raw_text: str) -> str:
    return raw_text.strip()


def _is_default_tab_title(title: str | None) -> bool:
    normalized = " ".join((title or "").split()).strip()
    if not normalized:
        return True
    if normalized.lower() == DEFAULT_TAB_TITLE.lower():
        return True
    return bool(LEGACY_NUMBERED_TAB_RE.fullmatch(normalized))


def _tab_has_messages(db, tab: WorkspaceTab) -> bool:
    return db.query(Message.id).filter(Message.tab_id == tab.id).first() is not None


def _tab_title_tokens(raw_text: str) -> list[str]:
    return [token[:24] for token in TAB_TITLE_TOKEN_RE.findall(raw_text or "")]


def _coerce_tab_title(candidate: str, fallback_text: str) -> str:
    generated_tokens = _tab_title_tokens(candidate)
    fallback_tokens = _tab_title_tokens(fallback_text)

    # Keep generated titles to 3-4 words; if the model misses the format, fall back.
    if len(generated_tokens) < 3:
        generated_tokens = []

    tokens = generated_tokens or fallback_tokens
    if not tokens:
        return DEFAULT_TAB_TITLE

    unique_tokens: list[str] = []
    seen = set()
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        unique_tokens.append(token)
        seen.add(key)
        if len(unique_tokens) >= 4:
            break

    filler_tokens = ("Task", "Context", "Chat")
    for token in filler_tokens:
        if len(unique_tokens) >= 3:
            break
        key = token.lower()
        if key in seen:
            continue
        unique_tokens.append(token)
        seen.add(key)

    return " ".join(unique_tokens[:4]) or DEFAULT_TAB_TITLE


def _generate_tab_title_with_local_model(request_text: str) -> str:
    title_prompt = (
        "Create a concise chat tab title for this request.\n"
        "Return ONLY the title.\n"
        "Rules:\n"
        "- 3 to 4 words.\n"
        "- No punctuation except hyphen or slash when necessary.\n"
        "- Reflect the request intent.\n\n"
        f"Request:\n{request_text}\n\n"
        "Title:"
    )
    result = run_local_model_response(title_prompt, timeout=18.0)
    return (result.get("reply") or "").strip()


def _auto_title_tab_from_request(db, tab: WorkspaceTab, request_text: str) -> None:
    if not request_text.strip():
        return
    if not _is_default_tab_title(tab.title):
        return
    if _tab_has_messages(db, tab):
        return

    generated_title = ""
    if get_local_preprocess_mode() != "off":
        try:
            generated_title = _generate_tab_title_with_local_model(request_text)
        except Exception:
            generated_title = ""

    resolved_title = _coerce_tab_title(generated_title, request_text)
    if not resolved_title:
        return
    if resolved_title == (tab.title or "").strip():
        return

    tab.title = resolved_title
    tab.updated_at = _utcnow()


def _normalize_cli_reply(reply: str, runtime: str) -> str:
    """Strip ANSI escape codes and hollow filler preambles from CLI replies."""
    # Remove ANSI color / cursor codes
    text = re.sub(r"\x1b\[[0-9;]*[mGKHFJA-Z]", "", reply).strip()
    # Remove hollow opener lines that add no value (e.g. "Sure!", "Certainly, I'll …")
    text = re.sub(
        r"^(Sure[,!]?|Certainly[,!]?|Of course[,!]?|Happy to help[,!]?|"
        r"Absolutely[,!]?|Great[,!]?|I\'ll|I will|Let me)[^\n]{0,160}\n+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return text or reply.strip()


def _runtime_prompt_suffix(runtime: str) -> str:
    """Short runtime-specific addendum appended to the prompt just before execution."""
    if runtime == "codex":
        return (
            "\n\nCodex-specific guidance:\n"
            "- Prefer patch-based edits (apply_patch) over full file rewrites.\n"
            "- Use file search tools before assuming paths or file contents."
        )
    if runtime == "gemini":
        return (
            "\n\nGemini-specific guidance:\n"
            "- Do not echo file contents back in your final reply.\n"
            "- Keep the closing summary to one concise paragraph."
        )
    return ""


def _normalize_git_paths(raw_paths: list[str]) -> list[str]:
    paths = []
    seen = set()

    for raw_path in raw_paths:
        path = raw_path.strip()
        if not path or path in seen:
            continue
        paths.append(path)
        seen.add(path)

    if not paths:
        raise HTTPException(status_code=400, detail="Select at least one file.")

    return paths


def _decode_git_path(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return ""
    if value.startswith('"') and value.endswith('"'):
        try:
            decoded = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
        if isinstance(decoded, str):
            return decoded
    return value


def _normalize_chat_attachments(raw_attachments: list[ChatAttachment]) -> list[dict]:
    attachments = []

    for attachment in raw_attachments:
        name = attachment.name.strip()
        content = attachment.content.strip()
        if not name or not content:
            continue

        attachments.append({"name": name, "content": content})

    return attachments


def _cli_runtimes(force_refresh: bool = False, quick: bool = False) -> dict:
    paths = _cached_runtime_paths(force_refresh=force_refresh)
    codex_path = paths["codex"]
    claude_path = paths["claude"]
    gemini_path = paths["gemini"]
    cursor_path = paths["cursor"]
    npm_path = paths["npm"]

    return {
        "codex": {
            "available": bool(codex_path),
            "path": codex_path,
            "version": _command_version(codex_path, force_refresh=force_refresh, allow_probe=not quick),
            "job": _runtime_job_payload(_active_runtime_job("codex")),
            **_runtime_access_state("codex"),
        },
        "claude": {
            "available": bool(claude_path),
            "path": claude_path,
            "version": _command_version(claude_path, force_refresh=force_refresh, allow_probe=not quick),
            "job": _runtime_job_payload(_active_runtime_job("claude")),
            **_runtime_access_state("claude"),
        },
        "gemini": {
            "available": bool(gemini_path),
            "path": gemini_path,
            "version": _command_version(gemini_path, force_refresh=force_refresh, allow_probe=not quick),
            "job": _runtime_job_payload(_active_runtime_job("gemini")),
            **_runtime_access_state("gemini"),
        },
        "cursor": {
            "available": bool(cursor_path),
            "path": cursor_path,
            "version": _command_version(cursor_path, force_refresh=force_refresh, allow_probe=not quick),
            "job": _runtime_job_payload(_active_runtime_job("cursor")),
            **_runtime_access_state("cursor"),
        },
        "npm": {
            "available": bool(npm_path),
            "path": npm_path,
            "version": _command_version(npm_path, force_refresh=force_refresh, allow_probe=not quick),
        },
    }


def _runtime_has_login(runtime: str) -> bool:
    for path in RUNTIME_AUTH_FILES.get(runtime, []):
        try:
            if path.exists() and path.stat().st_size > 0:
                return True
        except OSError:
            continue

    if runtime == "claude":
        try:
            if CLAUDE_STATE_FILE.exists() and CLAUDE_STATE_FILE.stat().st_size > 0:
                payload = json.loads(CLAUDE_STATE_FILE.read_text(encoding="utf-8"))
                oauth_account = payload.get("oauthAccount")
                if isinstance(oauth_account, dict) and oauth_account:
                    return True
        except Exception:
            pass

    if runtime == "cursor":
        return _cursor_has_login()

    return False


def _cursor_has_login(force_refresh: bool = False) -> bool:
    runtime_path = _cached_runtime_paths(force_refresh=force_refresh).get("cursor")
    if not runtime_path:
        return False

    now = time.monotonic()
    cached = RUNTIME_LOGIN_CACHE.get(runtime_path)
    if (
        not force_refresh
        and cached is not None
        and (now - float(cached.get("updated_at") or 0.0)) < RUNTIME_COMMAND_CACHE_TTL_SECONDS
    ):
        return bool(cached.get("has_login"))

    has_login = False
    try:
        result = subprocess.run(
            [runtime_path, "status"],
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
        has_login = bool(output) and "not authenticated" not in output and "not logged in" not in output
    except Exception:
        has_login = False

    RUNTIME_LOGIN_CACHE[runtime_path] = {
        "has_login": has_login,
        "updated_at": now,
    }
    return has_login


def _runtime_access_state(runtime: str) -> dict:
    provider = RUNTIME_PROVIDER.get(runtime)
    has_login = _runtime_has_login(runtime)
    has_key = bool(get_api_key(provider)) if provider else False
    configured = has_login or has_key

    if has_login and has_key:
        access_label = "Logged in and API key saved"
    elif has_login:
        access_label = "Logged in"
    elif has_key:
        access_label = "API key saved"
    else:
        access_label = "Not configured"

    return {
        "provider": provider,
        "configured": configured,
        "has_login": has_login,
        "has_key": has_key,
        "access_label": access_label,
        "login_hint": RUNTIME_LOGIN_HINTS.get(runtime, ""),
    }


def _codex_models_cache_payload() -> dict:
    if not CODEX_MODELS_CACHE_PATH.exists():
        return {}

    try:
        return json.loads(CODEX_MODELS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _visible_model_registry_entries(entries: list[dict]) -> list[dict]:
    return [
        entry
        for entry in (entries or [])
        if str(entry.get("id") or "").strip() != "codex/default"
    ]


def _codex_cached_model_registry() -> list[dict]:
    payload = _codex_models_cache_payload()
    if not payload:
        return []

    registry = []
    seen = set()
    models = sorted(
        payload.get("models", []),
        key=lambda model: (
            int(model.get("priority", 0)),
            str(model.get("display_name") or model.get("slug") or "").lower(),
        ),
    )

    for model in models:
        if model.get("visibility") != "list":
            continue

        slug = model.get("slug")
        if not slug or slug == "default":
            continue

        label = model.get("display_name") or slug
        model_id = f"codex/{slug}"
        supported_efforts = [
            level.get("effort")
            for level in model.get("supported_reasoning_levels", [])
            if isinstance(level, dict) and level.get("effort")
        ]
        default_effort = model.get("default_reasoning_level")
        base_entry = {
            "provider": "openai",
            "runtime": "codex",
            "family": _model_family(slug),
            "default_reasoning_effort": default_effort,
            "supported_reasoning_efforts": supported_efforts,
            "multimodal": bool(model.get("supports_images")),
            "context_window": model.get("context_window") if isinstance(model.get("context_window"), int) else None,
            "output_token_limit": model.get("max_output_tokens") if isinstance(model.get("max_output_tokens"), int) else None,
            "source": "codex-cache",
        }

        if supported_efforts:
            for effort in supported_efforts:
                effort_model_id = f"{model_id}@{effort}"
                if effort_model_id in seen:
                    continue
                registry.append(
                    _build_model_entry(
                        model_id=effort_model_id,
                        label=f"{label} / {_reasoning_effort_label(effort)}",
                        reasoning_effort=effort,
                        **base_entry,
                    )
                )
                seen.add(effort_model_id)
            continue

        if model_id not in seen:
            registry.append(_build_model_entry(model_id=model_id, label=label, **base_entry))
            seen.add(model_id)

    return _visible_model_registry_entries(_dedupe_model_registry(registry))


def _codex_cached_model_options() -> list[dict]:
    return [{"id": entry["id"], "label": entry["label"]} for entry in _visible_model_registry_entries(_codex_cached_model_registry())]


def _anthropic_model_catalog() -> list[dict]:
    api_key = get_api_key("anthropic")
    if not api_key:
        return []

    try:
        payload = _http_json_get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=5.0,
        )
    except Exception:
        return []

    catalog = []
    for model in payload.get("data", []):
        model_id = model.get("id")
        if not model_id:
            continue
        catalog.append(
            _build_model_entry(
                model_id=f"claude/{model_id}",
                label=model.get("display_name") or _label_from_model_name(model_id),
                provider="anthropic",
                runtime="claude",
                family=_model_family(model_id),
                source="anthropic-api",
            )
        )
    return catalog


def _gemini_model_catalog() -> list[dict]:
    api_key = get_api_key("google")
    if not api_key:
        return []

    page_token = ""
    catalog = []
    try:
        while True:
            query = {"key": api_key}
            if page_token:
                query["pageToken"] = page_token
            payload = _http_json_get(
                f"https://generativelanguage.googleapis.com/v1beta/models?{urllib_parse.urlencode(query)}",
                timeout=5.0,
            )
            for model in payload.get("models", []):
                name = model.get("name", "")
                if not name.startswith("models/"):
                    continue
                short_name = name.split("/", 1)[1]
                methods = model.get("supportedGenerationMethods", []) or []
                if methods and "generateContent" not in methods:
                    continue
                catalog.append(
                    _build_model_entry(
                        model_id=f"gemini/{short_name}",
                        label=model.get("displayName") or _label_from_model_name(short_name),
                        provider="google",
                        runtime="gemini",
                        family=_model_family(short_name),
                        context_window=model.get("inputTokenLimit") if isinstance(model.get("inputTokenLimit"), int) else None,
                        output_token_limit=model.get("outputTokenLimit") if isinstance(model.get("outputTokenLimit"), int) else None,
                        tool_support=methods,
                        multimodal=any("image" in method.lower() or "content" in method.lower() for method in methods) if methods else None,
                        source="gemini-api",
                    )
                )
            page_token = payload.get("nextPageToken") or ""
            if not page_token:
                break
    except Exception:
        return []

    return catalog


def _configured_runtime_model_registry(runtime: str, runtimes: dict | None = None) -> list[dict]:
    runtimes = runtimes or _cli_runtimes()
    runtime_state = runtimes.get(runtime, {})
    if not runtime_state.get("available") or not runtime_state.get("configured"):
        return []

    discovered = _cli_discovered_model_registry(runtime)
    return discovered


def _verified_runtime_model_registry(runtime: str, runtimes: dict | None = None) -> list[dict]:
    runtimes = runtimes or _cli_runtimes()
    runtime_state = runtimes.get(runtime, {})
    if not runtime_state.get("available") or not runtime_state.get("configured"):
        return []

    discovered = _cli_discovered_model_registry(runtime)
    if runtime == "claude":
        verified = []
        base_verification: dict[str, bool] = {}
        for entry in discovered:
            model_id = str(entry.get("id") or "")
            base_model_id = model_id.split("@", 1)[0]
            if base_model_id not in base_verification:
                base_verification[base_model_id] = _probe_model(base_model_id, timeout_seconds=MODEL_PROBE_TIMEOUT_SECONDS)
            if base_verification[base_model_id]:
                verified.append({**entry, "source": "cli-probe"})
        return verified

    verified = []
    for entry in discovered:
        if _probe_model(entry["id"], timeout_seconds=MODEL_PROBE_TIMEOUT_SECONDS):
            verified.append({**entry, "source": "cli-probe"})
    return verified


def _discover_model_registry(verified: bool = False, runtimes: dict | None = None) -> list[dict]:
    runtimes = runtimes or _cli_runtimes()
    registry = []

    if runtimes.get("codex", {}).get("available") and runtimes.get("codex", {}).get("configured"):
        registry.extend(_visible_model_registry_entries(_codex_cached_model_registry()))
    runtime_registry = _verified_runtime_model_registry if verified else _configured_runtime_model_registry
    registry.extend(runtime_registry("cursor", runtimes=runtimes))
    registry.extend(runtime_registry("claude", runtimes=runtimes))
    registry.extend(runtime_registry("gemini", runtimes=runtimes))

    return registry


def _smart_model_entry(registry: list[dict]) -> dict:
    smart_modes = _sorted_agent_modes(
        mode
        for entry in registry
        for mode in (entry.get("agent_modes") or [])
    )
    return {
        "id": "smart",
        "label": "Auto Model Select",
        "provider": "smart",
        "runtime": "smart",
        "family": "smart",
        "agent_modes": smart_modes,
        "default_agent_mode": _default_agent_mode_from_modes(smart_modes),
        "source": "virtual",
    }


def _discover_model_options(verified: bool = False, runtimes: dict | None = None) -> list[dict]:
    discovered = _discover_model_registry(verified=verified, runtimes=runtimes)
    if not discovered:
        return []
    return [_smart_model_entry(discovered), *discovered]


def _model_registry() -> list[dict]:
    cached = MODEL_DISCOVERY_CACHE.get("registry")
    if cached is not None and MODEL_DISCOVERY_CACHE.get("options") is None:
        return _visible_model_registry_entries(cached)
    updated_at = float(MODEL_DISCOVERY_CACHE.get("updated_at") or 0.0)
    if cached is not None and (updated_at <= 0 or _model_discovery_cache_is_fresh()):
        return _visible_model_registry_entries(cached)
    registry = _visible_model_registry_entries(_discover_model_registry(verified=False))
    with MODEL_DISCOVERY_LOCK:
        MODEL_DISCOVERY_CACHE["registry"] = registry
        MODEL_DISCOVERY_CACHE["updated_at"] = time.monotonic()
        MODEL_DISCOVERY_CACHE["verified"] = False
    return registry


def _model_options() -> list[dict]:
    cached = MODEL_DISCOVERY_CACHE.get("options")
    if cached is not None and MODEL_DISCOVERY_CACHE.get("registry") is None:
        return _visible_model_registry_entries(cached)
    updated_at = float(MODEL_DISCOVERY_CACHE.get("updated_at") or 0.0)
    if cached is not None and (updated_at <= 0 or _model_discovery_cache_is_fresh()):
        return _visible_model_registry_entries(cached)
    options = _visible_model_registry_entries(_discover_model_options(verified=False))
    with MODEL_DISCOVERY_LOCK:
        MODEL_DISCOVERY_CACHE["options"] = options
        MODEL_DISCOVERY_CACHE["updated_at"] = time.monotonic()
        MODEL_DISCOVERY_CACHE["verified"] = False
    return options


def _default_agent_mode_for_model(model_id: str, available_models: list[dict] | None = None) -> str:
    normalized_model_id = str(model_id or "").strip()
    if not normalized_model_id:
        return ""
    entries = available_models or _model_options()
    for entry in entries:
        if entry.get("id") == normalized_model_id:
            return _normalize_agent_mode(entry.get("default_agent_mode"))
    runtime, _, _ = _resolve_runtime_model(normalized_model_id)
    return _runtime_default_agent_mode(runtime)


def _supported_agent_modes_for_model(model_id: str, available_models: list[dict] | None = None) -> list[str]:
    normalized_model_id = str(model_id or "").strip()
    if not normalized_model_id:
        return []
    entries = available_models or _model_options()
    for entry in entries:
        if entry.get("id") == normalized_model_id:
            return _sorted_agent_modes(entry.get("agent_modes") or [])
    runtime, _, _ = _resolve_runtime_model(normalized_model_id)
    return _runtime_agent_modes(runtime)


def _resolve_requested_agent_mode(
    model_id: str,
    requested_mode: str | None,
    available_models: list[dict] | None = None,
) -> str:
    supported_modes = _supported_agent_modes_for_model(model_id, available_models=available_models)
    if not supported_modes:
        return ""
    normalized_mode = _normalize_agent_mode(requested_mode)
    if normalized_mode in supported_modes:
        return normalized_mode
    return _default_agent_mode_for_model(model_id, available_models=available_models) or supported_modes[0]


def _filter_models_for_agent_mode(available_models: list[dict], agent_mode: str | None) -> list[dict]:
    normalized_mode = _normalize_agent_mode(agent_mode)
    if not normalized_mode:
        return list(available_models or [])
    filtered = [
        entry
        for entry in (available_models or [])
        if normalized_mode in (entry.get("agent_modes") or [])
    ]
    return filtered or list(available_models or [])


def _normalize_selected_model(raw_model: str) -> str:
    model = raw_model.strip() or "smart"
    available_ids = {option["id"] for option in _model_options()}
    if model not in available_ids:
        raise HTTPException(status_code=400, detail="Selected model is not available in this environment.")

    return model


def _build_user_message_content(text: str, attachments: list[dict]) -> str:
    parts = []
    if text:
        parts.append(text)

    if attachments:
        names = ", ".join(attachment["name"] for attachment in attachments)
        parts.append(f"Attached files: {names}")

    content = "\n\n".join(parts).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Enter a message or attach at least one file.")

    return content


def _record_last_chat_request(
    tab: WorkspaceTab,
    text: str,
    attachments: list[dict],
    requested_model: str,
    requested_agent_mode: str,
) -> None:
    tab.last_request_text = text or ""
    tab.last_request_model = requested_model or "smart"
    tab.last_request_agent_mode = requested_agent_mode or ""
    tab.last_request_attachments = json.dumps(attachments or [])


def _last_chat_request_or_400(tab: WorkspaceTab) -> tuple[str, str, str, list[ChatAttachment]]:
    text = (tab.last_request_text or "").strip()
    model = (tab.last_request_model or "").strip() or "smart"
    agent_mode = _normalize_agent_mode(tab.last_request_agent_mode)
    try:
        raw_attachments = json.loads(tab.last_request_attachments or "[]")
    except Exception:
        raw_attachments = []
    attachments = [
        ChatAttachment(
            name=str(item.get("name") or ""),
            content=str(item.get("content") or ""),
        )
        for item in raw_attachments
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if not text and not attachments:
        raise HTTPException(status_code=404, detail="No retryable chat turn exists for this tab.")
    return text, model, agent_mode, attachments


_CODEBASE_IDENT_RE = re.compile(
    r'\b(?:'
    r'[A-Z][a-z][a-zA-Z0-9]+'          # CamelCase (UserProfile, LoginButton)
    r'|[a-z][a-z0-9]+_[a-z][a-z0-9_]+'  # snake_case (handle_login, my_func_name)
    r'|[a-zA-Z][a-zA-Z0-9]{7,}'          # long single word 8+ chars
    r')\b'
    r'|(?:[a-zA-Z][a-zA-Z0-9]*)(?:\.[a-zA-Z][a-zA-Z0-9]*)+'  # dotted.path
)
_CODEBASE_SKIP_WORDS = frozenset({
    "function", "variable", "component", "something", "everything", "anything",
    "implement", "refactor", "existing", "following", "different", "whatever",
    "whenever", "important", "necessary", "currently", "typically", "actually",
    "basically", "specific", "generally", "normally", "probably", "definitely",
    "obviously", "essentially", "regarding", "potential", "possible", "previous",
    "multiple", "yourself", "together", "directly", "structure", "instance",
    "example", "response", "request", "because", "between", "through", "without",
    "getting", "looking", "working", "running", "clicking", "updating", "creating",
    "deleting", "reading", "writing", "changing", "removing", "breaking", "testing",
    "checking", "finding", "showing", "allowing", "passing", "returning", "calling",
    "handling", "features", "methods", "classes", "modules", "objects", "functions",
    "variables", "constants", "parameters", "arguments", "results", "dashboard",
    "settings", "options", "application", "interface", "behavior", "condition",
})


def _search_codebase_context(workspace_path: str, prompt_text: str, max_snippets: int = 4) -> str:
    """Grep the workspace for identifiers found in the prompt. Returns formatted snippets."""
    terms: list[str] = []
    seen: set[str] = set()
    for m in _CODEBASE_IDENT_RE.finditer(prompt_text or ""):
        term = m.group(0)
        norm = term.lower()
        if norm not in _CODEBASE_SKIP_WORDS and norm not in seen and len(term) >= 3:
            seen.add(norm)
            terms.append(term)

    if not terms:
        return ""

    rg = shutil.which("rg")
    if not rg:
        return ""

    snippets: list[str] = []
    seen_files: set[str] = set()

    for term in terms[:10]:
        if len(snippets) >= max_snippets:
            break
        try:
            files_result = subprocess.run(
                [
                    rg, "--files-with-matches", "--max-count=1",
                    "--glob=!node_modules", "--glob=!.git", "--glob=!dist",
                    "--glob=!build", "--glob=!__pycache__", "--glob=!*.min.js",
                    "--glob=!*.lock", "--glob=!*.map",
                    "--type-add", "src:*.{py,js,ts,jsx,tsx,go,rs,rb,java,cs}",
                    "--type=src",
                    term, workspace_path,
                ],
                capture_output=True, text=True, timeout=3.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue

        files = [f for f in (files_result.stdout or "").strip().split("\n") if f and f not in seen_files]
        for fpath in files[:2]:
            seen_files.add(fpath)
            try:
                lines_result = subprocess.run(
                    [rg, "--no-heading", "-n", "--context=2", "--max-count=3", term, fpath],
                    capture_output=True, text=True, timeout=2.0,
                )
            except (subprocess.TimeoutExpired, OSError):
                continue
            out = (lines_result.stdout or "").strip()
            if not out:
                continue
            try:
                rel = os.path.relpath(fpath, workspace_path)
            except ValueError:
                rel = fpath
            snippets.append(f"# {rel}\n{out[:500]}")
            if len(snippets) >= max_snippets:
                break

    return "\n\n".join(snippets)


def _enrich_cli_prompt(
    request_text: str,
    workspace_path: str,
    task_analysis: dict | None,
) -> str | None:
    """
    For non-trivial tasks: search the codebase for relevant code and use the local model
    to produce a structured context brief for the CLI model.
    Returns an enriched context string, or None to skip.
    """
    analysis = task_analysis or {}
    complexity = float(analysis.get("complexity") or 0)
    task_type = str(analysis.get("task_type") or "").lower()
    word_count = len((request_text or "").split())

    # Skip for clearly simple / trivial requests
    if complexity < 0.2 and word_count <= 8:
        return None
    if task_type == "general" and complexity < 0.25 and word_count < 10:
        return None

    snippets = _search_codebase_context(workspace_path, request_text)

    # If codebase search found nothing and complexity is low, not worth the local model call
    if not snippets and complexity < 0.35:
        return None

    try:
        return run_local_prompt_enrichment(request_text, snippets)
    except Exception:
        # Fall back to raw snippets for clearly complex tasks if model unavailable
        if snippets and complexity >= 0.5:
            return f"Relevant codebase context:\n{snippets}"
        return None


def _build_prompt_text(
    text: str,
    attachments: list[dict],
    workspace_context: str = "",
    generated_files_dir: str = "",
    generated_files_staging_dir: str = "",
    human_language: str | None = None,
) -> str:
    parts = []
    parts.append(language_runtime_instruction(human_language))
    parts.append(
        "Execution guidance:\n"
        "- Use the minimum necessary tokens.\n"
        "- Read only the files needed for the task.\n"
        "- Avoid repeating the provided context back verbatim.\n"
        "- Keep plans and explanations brief unless deeper detail is required.\n"
        "- Prefer targeted edits and concise outputs.\n"
        "- Do not mention missing tests or unrun tests unless it is directly relevant.\n"
        "- If tests would be valuable, recommend adding them briefly instead of repeating that they were not run."
    )
    if generated_files_dir:
        parts.append(
            "Generated file rule:\n"
            "- Do not try to write brand-new files directly to the final generated-files directory because the runtime sandbox may block that path.\n"
            f"- For generated outputs that should live outside the repo, create them in this staging directory inside the workspace: {generated_files_staging_dir or '.bettercode-generated'}\n"
            f"- BetterCode will move those staged generated files after the turn into the final generated-files directory: {generated_files_dir}\n"
            "- Examples of generated outputs: exports, reports, PDFs, CSVs, standalone HTML deliverables, and similar artifacts.\n"
            "- If the task is to create or scaffold real project files that belong in the repo, create them normally in the workspace instead.\n"
            "- Modify existing project files in place when needed.\n"
            "- If you mention a generated file in your response, use its final absolute path."
        )
    if workspace_context:
        parts.append(workspace_context)

    if text:
        parts.append(text)

    if attachments:
        parts.append("Attached file context:")
        total_chars = 0
        for attachment in attachments:
            content = attachment["content"] or ""
            if total_chars >= MAX_ATTACHMENTS_TOTAL_CHARS:
                parts.append(f"File: {attachment['name']}\n[Omitted — total attachment budget ({MAX_ATTACHMENTS_TOTAL_CHARS // 1000}K chars) reached]")
                continue
            remaining_budget = MAX_ATTACHMENTS_TOTAL_CHARS - total_chars
            cap = min(MAX_ATTACHMENT_CHARS, remaining_budget)
            if len(content) > cap:
                content = content[:cap] + f"\n\n… [truncated — {len(attachment['content']) - cap:,} chars omitted to save tokens]"
            total_chars += len(content)
            parts.append(f"File: {attachment['name']}\n```text\n{content}\n```")

    content = "\n\n".join(parts).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Enter a message or attach at least one file.")

    return content


def _build_selector_request_text(text: str, attachments: list[dict]) -> str:
    parts = []
    if text:
        parts.append(text)
    if attachments:
        parts.append("Attachments: " + ", ".join(attachment["name"] for attachment in attachments))
    return "\n\n".join(parts).strip()


def _build_workspace_prompt_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    tab: WorkspaceTab | None = None,
) -> str:
    resolved_tab = tab or _workspace_display_tab(_sorted_workspace_tabs(workspace.tabs or [], archived=False))
    if resolved_tab is None:
        resolved_tab = _ensure_workspace_tab(db, workspace)

    preprocessed = _build_preprocessed_turn_context(
        db,
        workspace,
        request_text,
        attachments,
        tab=tab,
    )
    parts = [
        "Execution brief:\n"
        f"- Goal: {preprocessed['goal']}\n"
        f"- Task type: {(preprocessed['task_analysis'].get('task_type') or 'general').replace('_', ' ')}\n"
        f"- Execution mode: {preprocessed['execution_mode']}\n"
        f"- Success criteria: {preprocessed['success_criteria']}\n"
        f"- Focus files: {', '.join(preprocessed['target_files']) if preprocessed['target_files'] else 'None'}\n"
        f"- Attachments: {', '.join(preprocessed['attachment_names']) if preprocessed['attachment_names'] else 'None'}",
        build_workspace_context_block(workspace, tab=tab),
        build_memory_context_block(db, workspace, tab=resolved_tab, request_text=request_text),
    ]
    if preprocessed["ambiguity_note"]:
        parts.append(f"Ambiguity handling:\n- {preprocessed['ambiguity_note']}")
    if preprocessed["recent_history"]:
        parts.append("Relevant recent conversation:\n" + "\n".join(preprocessed["recent_history"]))
    parts.extend([
        f"Generated file staging directory: {_workspace_generated_staging_dir(workspace, create=True)}",
        f"Generated files directory: {_workspace_generated_dir(workspace, create=True)}",
    ])
    return "\n\n".join(part for part in parts if part).strip()


def _build_local_turn_prompt(
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    request_text: str,
) -> str:
    parts = []
    summary_block = build_workspace_context_block(workspace, tab=tab)
    memory_block = build_memory_context_block(db, workspace, tab=tab, request_text=request_text, limit=6)
    if summary_block:
        parts.append(summary_block)
    if memory_block:
        parts.append(memory_block)
    parts.append(f"User request:\n{request_text.strip()}")
    return "\n\n".join(part for part in parts if part).strip()


def _command_version(command_path: str | None, force_refresh: bool = False, allow_probe: bool = True) -> str | None:
    if not command_path:
        return None

    now = time.monotonic()
    cached = COMMAND_VERSION_CACHE.get(command_path)
    if (
        not force_refresh
        and cached is not None
        and (now - float(cached.get("updated_at") or 0.0)) < COMMAND_VERSION_CACHE_TTL_SECONDS
    ):
        return cached.get("version")

    if not allow_probe:
        return cached.get("version") if cached else None

    try:
        result = subprocess.run(
            [command_path, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except Exception:
        return None

    version = (result.stdout or result.stderr).strip().splitlines()
    first_line = version[0] if version else None
    COMMAND_VERSION_CACHE[command_path] = {
        "version": first_line,
        "updated_at": now,
    }
    return first_line


def _model_options_cached_only() -> list[dict]:
    cached = MODEL_DISCOVERY_CACHE.get("options")
    if cached is None:
        return []
    return _visible_model_registry_entries(list(cached))


def _model_options_for_app_info() -> list[dict]:
    cached = _model_options_cached_only()
    if cached:
        return cached
    return _discover_model_options(verified=False, runtimes=_cli_runtimes(quick=True))


def _has_active_cli_activity() -> bool:
    with ACTIVE_CHAT_PROCESSES_LOCK:
        if any(process.poll() is None for process in ACTIVE_CHAT_PROCESSES.values()):
            return True
    with ACTIVE_RUN_PROCESSES_LOCK:
        if any(process.poll() is None for process in ACTIVE_RUN_PROCESSES.values()):
            return True
    with RUNTIME_JOBS_LOCK:
        if any(job.get("status") == "running" for job in RUNTIME_JOBS.values()):
            return True
    return False


def _codex_exec_capabilities(codex_path: str, force_refresh: bool = False) -> dict:
    now = time.monotonic()
    cached = CODEX_EXEC_CAPABILITY_CACHE.get(codex_path)
    if (
        not force_refresh
        and cached is not None
        and (now - float(cached.get("updated_at") or 0.0)) < COMMAND_VERSION_CACHE_TTL_SECONDS
    ):
        return dict(cached)

    help_text = ""
    try:
        result = subprocess.run(
            [codex_path, "exec", "--help"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        help_text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    except Exception:
        help_text = ""

    capabilities = {
        "output_flag": "--output-last-message" if "--output-last-message" in help_text else "-o",
        "supports_resume": bool(re.search(r"^\s+resume\b", help_text, re.MULTILINE)),
        "supports_color": "--color" in help_text,
        "supports_dangerous_bypass": "--dangerously-bypass-approvals-and-sandbox" in help_text,
        "updated_at": now,
    }
    CODEX_EXEC_CAPABILITY_CACHE[codex_path] = capabilities
    return dict(capabilities)


def _codex_reasoning_effort(reasoning_effort: str | None) -> str:
    effort = (reasoning_effort or "").strip().lower()
    if not effort:
        return "medium"
    if effort == "xhigh":
        return "high"
    if effort in {"minimal", "low", "medium", "high"}:
        return effort
    return "medium"


def _runtime_package(runtime: str) -> str:
    try:
        return RUNTIME_PACKAGES[runtime]
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="This runtime does not support npm installation.") from exc


def _runtime_or_404(runtime: str) -> str:
    if runtime not in RUNTIME_EXECUTABLES:
        raise HTTPException(status_code=404, detail="Unknown runtime.")
    return runtime


def _cursor_install_command() -> list[str]:
    if sys.platform == "win32":
        raise HTTPException(status_code=400, detail="Cursor CLI install is supported from macOS, Linux, or WSL. Install Cursor first, then add cursor-agent to PATH.")
    bash_path = shutil.which("bash")
    curl_path = shutil.which("curl")
    if not bash_path or not curl_path:
        raise HTTPException(status_code=400, detail="Cursor CLI install requires bash and curl.")
    return [bash_path, "-lc", f"{curl_path} https://cursor.com/install -fsS | bash"]


def _terminal_command(inner_command: list[str]) -> list[str]:
    return _build_terminal_command_base(inner_command, RUNTIME_TERMINALS)


def _register_runtime_job(runtime: str, action: str) -> dict:
    active = _active_runtime_job(runtime)
    if active:
        return active

    job = {
        "id": uuid.uuid4().hex,
        "runtime": runtime,
        "action": action,
        "status": "running",
        "message": "",
        "output": "",
        "started_at": _utcnow().isoformat(),
        "finished_at": "",
    }
    with RUNTIME_JOBS_LOCK:
        RUNTIME_JOBS[job["id"]] = job
    return dict(job)


def _update_runtime_job(job_id: str, **updates):
    with RUNTIME_JOBS_LOCK:
        job = RUNTIME_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)


def _run_runtime_job(job_id: str, command: list[str], workspace_path: str):
    try:
        result = _run_external_command(command, workspace_path)
        output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            _update_runtime_job(
                job_id,
                status="failed",
                message=output or "Runtime action failed.",
                output=output,
                finished_at=_utcnow().isoformat(),
            )
            return

        _invalidate_runtime_caches()
        _clear_model_discovery_cache()
        _update_runtime_job(
            job_id,
            status="completed",
            message=output or "Completed.",
            output=output,
            finished_at=_utcnow().isoformat(),
        )
    except HTTPException as exc:
        _update_runtime_job(
            job_id,
            status="failed",
            message=str(exc.detail),
            output=str(exc.detail),
            finished_at=_utcnow().isoformat(),
        )
    except Exception as exc:
        _update_runtime_job(
            job_id,
            status="failed",
            message=str(exc),
            output=str(exc),
            finished_at=_utcnow().isoformat(),
        )


def _launch_detached_command(command: list[str], workspace_path: str | None = None) -> None:
    _launch_detached_command_base(command, workspace_path=workspace_path)


def _spawn_runtime_launch_job(
    runtime: str,
    action: str,
    command: list[str],
    workspace_path: str | None = None,
    completion_message: str = "Opened terminal. Complete the runtime login there, then refresh status.",
) -> dict:
    active = _active_runtime_job(runtime)
    if active:
        return {
            "job": _runtime_job_payload(active),
            "runtimes": _cli_runtimes(),
            "models": _model_options(),
        }

    job = _register_runtime_job(runtime, action)
    try:
        _launch_detached_command(command, workspace_path=workspace_path)
        _update_runtime_job(
            job["id"],
            status="completed",
            message=completion_message,
            output=completion_message,
            finished_at=_utcnow().isoformat(),
        )
    except HTTPException as exc:
        _update_runtime_job(
            job["id"],
            status="failed",
            message=str(exc.detail),
            output=str(exc.detail),
            finished_at=_utcnow().isoformat(),
        )
    return {
        "job": _runtime_job_payload(_runtime_job_or_404(job["id"])),
        "runtimes": _cli_runtimes(),
        "models": _model_options(),
    }


def _spawn_runtime_job(runtime: str, action: str, command: list[str], workspace_path: str | None = None) -> dict:
    active = _active_runtime_job(runtime)
    if active:
        return {
            "job": _runtime_job_payload(active),
            "runtimes": _cli_runtimes(),
            "models": _model_options(),
        }

    job = _register_runtime_job(runtime, action)
    thread = threading.Thread(
        target=_run_runtime_job,
        args=(job["id"], command, workspace_path or os.getcwd()),
        daemon=True,
    )
    thread.start()
    return {
        "job": _runtime_job_payload(job),
        "runtimes": _cli_runtimes(),
        "models": _model_options(),
    }


def _install_runtime_payload(runtime: str) -> dict:
    _runtime_or_404(runtime)
    if runtime == "cursor":
        return _spawn_runtime_job(runtime, "install", _cursor_install_command())
    runtimes = _cli_runtimes()
    if not runtimes["npm"]["available"]:
        raise HTTPException(status_code=400, detail="npm is required to install CLI runtimes.")

    package_name = _runtime_package(runtime)
    return _spawn_runtime_job(
        runtime,
        "install",
        [runtimes["npm"]["path"], "install", "-g", f"{package_name}@latest"],
    )


def runtime_login_payload(runtime: str) -> dict:
    runtime = _runtime_or_404(runtime)
    runtimes = _cli_runtimes()
    runtime_state = runtimes.get(runtime, {})
    if not runtime_state.get("available"):
        raise HTTPException(status_code=400, detail=f"{runtime.title()} CLI is not installed.")

    command = _terminal_command(RUNTIME_LOGIN_COMMANDS[runtime])
    completion_message = "Opened the runtime login terminal. Complete sign-in there, then refresh status."
    return _spawn_runtime_launch_job(runtime, "login", command, completion_message=completion_message)


def _clear_runtime_auth_files(runtime: str):
    for path in RUNTIME_AUTH_FILES.get(runtime, []):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def runtime_logout_payload(runtime: str) -> dict:
    runtime = _runtime_or_404(runtime)
    runtimes = _cli_runtimes()
    provider = RUNTIME_PROVIDER.get(runtime)
    runtime_state = runtimes.get(runtime, {})
    output_lines = []

    if provider and runtime_state.get("has_key"):
        delete_api_key(provider)
        output_lines.append("Removed saved API key.")

    if runtime_state.get("has_login") and runtime_state.get("path"):
        command = [runtime_state["path"], *RUNTIME_LOGOUT_ARGS.get(runtime, ["logout"])]
        result = _run_external_command(command, os.getcwd())
        if result.returncode == 0:
            output = (result.stdout or result.stderr).strip()
            if output:
                output_lines.append(output)

    if runtime_state.get("has_login"):
        _clear_runtime_auth_files(runtime)
        output_lines.append("Cleared saved runtime login.")

    _invalidate_runtime_caches()
    _clear_model_discovery_cache()
    return {
        "runtime": runtime,
        "output": "\n".join(output_lines).strip(),
        "runtimes": _cli_runtimes(),
        "models": refresh_model_options_payload()["models"],
    }


def runtime_job_payload(job_id: str) -> dict:
    job = _runtime_job_or_404(job_id)
    if job["status"] == "completed":
        models = refresh_model_options_payload()["models"]
    else:
        models = _model_options()
    return {
        "job": _runtime_job_payload(job),
        "runtimes": _cli_runtimes(),
        "models": models,
    }


def _probe_model(selected_model: str, timeout_seconds: int = 1800) -> bool:
    try:
        runtime, model_name, reasoning_effort = _resolve_runtime_model(selected_model)
        probe_prompt = "Reply with OK."
        with tempfile.TemporaryDirectory(prefix="bettercode-model-check-") as temp_dir:
            workspace_path = temp_dir
            if runtime == "codex":
                _run_codex_cli(workspace_path, probe_prompt, model_name, reasoning_effort, timeout_seconds=timeout_seconds)
                return True
            if runtime == "cursor":
                _run_cursor_cli(
                    workspace_path,
                    probe_prompt,
                    model_name,
                    timeout_seconds=timeout_seconds,
                )
                return True
            if runtime == "claude":
                _run_claude_cli(workspace_path, probe_prompt, model_name, timeout_seconds=timeout_seconds, reasoning_effort=reasoning_effort)
                return True
            if runtime == "gemini":
                _run_gemini_cli(workspace_path, probe_prompt, model_name, timeout_seconds=timeout_seconds)
                return True
            return False
    except Exception:
        return False


def refresh_model_options_payload(force_refresh: bool = False) -> dict:
    with MODEL_DISCOVERY_LOCK:
        if not force_refresh and _has_active_cli_activity():
            return {"models": _model_options_for_app_info()}
        if not force_refresh and _model_discovery_cache_is_fresh(verified_required=True):
            return {"models": _visible_model_registry_entries(MODEL_DISCOVERY_CACHE.get("options") or [])}

        registry = _discover_model_registry(verified=True)
        options = _visible_model_registry_entries([_smart_model_entry(registry), *registry] if registry else [])
        MODEL_DISCOVERY_CACHE["registry"] = registry
        MODEL_DISCOVERY_CACHE["options"] = options
        MODEL_DISCOVERY_CACHE["updated_at"] = time.monotonic()
        MODEL_DISCOVERY_CACHE["verified"] = True
        return {"models": options}


def _resolve_runtime_model(selected_model: str) -> tuple[str, str | None, str | None]:
    runtimes = _cli_runtimes()

    if selected_model == "smart":
        if runtimes.get("codex", {}).get("available"):
            return "codex", None, None
        if runtimes.get("cursor", {}).get("available"):
            return "cursor", None, None
        if runtimes.get("claude", {}).get("available"):
            return "claude", None, None
        if runtimes.get("gemini", {}).get("available"):
            return "gemini", None, None
        raise HTTPException(status_code=400, detail="No supported coding CLI is installed. Install Codex, Cursor CLI, Claude CLI, or Gemini CLI.")

    if selected_model.startswith("local/"):
        model = selected_model.split("/", 1)[1]
        if not model:
            raise HTTPException(status_code=400, detail="Local model is not supported.")
        return "local", model, None

    if selected_model.startswith("codex/"):
        if not runtimes.get("codex", {}).get("available"):
            raise HTTPException(status_code=400, detail="Codex CLI is not installed.")
        model = selected_model.split("/", 1)[1]
        reasoning_effort = None
        if "@" in model:
            model, reasoning_effort = model.rsplit("@", 1)
        return "codex", None if model == "default" else model, reasoning_effort

    if selected_model.startswith("cursor/"):
        if not runtimes.get("cursor", {}).get("available"):
            raise HTTPException(status_code=400, detail="Cursor CLI is not installed.")
        model = selected_model.split("/", 1)[1]
        return "cursor", None if model == "default" else model, None

    if selected_model.startswith("claude/"):
        if not runtimes.get("claude", {}).get("available"):
            raise HTTPException(status_code=400, detail="Claude CLI is not installed.")
        model = selected_model.split("/", 1)[1]
        reasoning_effort = None
        if "@" in model:
            model, reasoning_effort = model.rsplit("@", 1)
        return "claude", None if model == "default" else model, reasoning_effort

    if selected_model.startswith("gemini/"):
        if not runtimes.get("gemini", {}).get("available"):
            raise HTTPException(status_code=400, detail="Gemini CLI is not installed.")
        model = selected_model.split("/", 1)[1]
        return "gemini", None if model == "default" else model, None

    raise HTTPException(status_code=400, detail="Selected model is not supported.")


def _run_external_command(command: list[str], workspace_path: str, timeout_seconds: int = 1800) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command,
            cwd=workspace_path,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Required command is not installed: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"{command[0]} timed out before producing a reply.") from exc

    return result


def _codex_model_label(model_name: str | None, reasoning_effort: str | None) -> str:
    if model_name and reasoning_effort:
        return f"codex/{model_name}@{reasoning_effort}"
    if model_name:
        return f"codex/{model_name}"
    return "codex/default"


def _resolved_runtime_model_id(runtime: str, model_name: str | None, reasoning_effort: str | None = None) -> str:
    if runtime == "local":
        return f"local/{model_name}" if model_name else "local/default"
    if runtime == "codex":
        return _codex_model_label(model_name, reasoning_effort)
    if runtime == "cursor":
        return f"cursor/{model_name}" if model_name else "cursor/default"
    if runtime == "claude":
        base = f"claude/{model_name}" if model_name else "claude/default"
        return f"{base}@{reasoning_effort}" if reasoning_effort else base
    if runtime == "gemini":
        return f"gemini/{model_name}" if model_name else "gemini/default"
    return runtime


def _build_codex_command(
    codex_path: str,
    workspace_path: str,
    output_path: str,
    prompt_text: str,
    model_name: str | None,
    reasoning_effort: str | None,
    agent_mode: str | None = None,
    session_id: str | None = None,
    json_output: bool = False,
    ephemeral: bool = False,
    terminal_output: bool = False,
    bypass_sandbox: bool = False,
) -> list[str]:
    capabilities = _codex_exec_capabilities(codex_path)
    effective_session_id = session_id if capabilities["supports_resume"] else None
    effective_agent_mode = _normalize_agent_mode(agent_mode) or _runtime_default_agent_mode("codex")
    command = [codex_path, "exec"]
    resume_last = effective_session_id == CODEX_LAST_SESSION_SENTINEL
    if resume_last:
        command.extend(["resume", "--last"])
    elif effective_session_id:
        command.append("resume")
    if json_output:
        command.append("--json")
    if bypass_sandbox and capabilities.get("supports_dangerous_bypass"):
        command.append("--dangerously-bypass-approvals-and-sandbox")
    elif effective_agent_mode == "plan":
        command.extend(["-a", "never", "-s", "read-only"])
    elif effective_agent_mode == "auto_edit":
        command.extend(["-a", "never", "-s", "workspace-write"])
    else:
        command.append("--full-auto")
    command.append("--skip-git-repo-check")
    if terminal_output and not effective_session_id and capabilities["supports_color"]:
        command.extend(["--color", "always"])
    if not effective_session_id:
        command.extend([
            "-C",
            workspace_path,
        ])
    command.extend([
        capabilities["output_flag"],
        output_path,
    ])
    if ephemeral:
        command.append("--ephemeral")
    if model_name:
        command.extend(["-m", model_name])
    command.extend(["-c", f'model_reasoning_effort="{_codex_reasoning_effort(reasoning_effort)}"'])
    if effective_session_id and not resume_last:
        command.append(effective_session_id)
    command.append(prompt_text)
    return command


def _is_codex_sandbox_bootstrap_failure(detail: str) -> bool:
    lowered = str(detail or "").strip().lower()
    if not lowered:
        return False
    return (
        ("sandbox(denied" in lowered or "bwrap:" in lowered or "failed rtm_newaddr" in lowered)
        and ("operation not permitted" in lowered or "createprocess" in lowered or "sandbox" in lowered)
    )


def _codex_retry_without_sandbox_message() -> str:
    return "Codex sandbox failed to start in this environment. Retrying without Codex sandbox..."


def _codex_thread_id(raw_line: str) -> str | None:
    try:
        payload = json.loads(raw_line.strip())
    except Exception:
        return None

    if payload.get("type") == "thread.started":
        return payload.get("thread_id")
    return None


def _run_codex_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
    session_id: str | None = None,
    ephemeral: bool = False,
    timeout_seconds: int = 1800,
) -> dict:
    codex_path = shutil.which("codex")
    if not codex_path:
        raise HTTPException(status_code=400, detail="Codex CLI is not installed.")
    capabilities = _codex_exec_capabilities(codex_path)
    bypass_sandbox = False

    while True:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as output_file:
            output_path = output_file.name

        try:
            command = _build_codex_command(
                codex_path,
                workspace_path,
                output_path,
                prompt_text,
                model_name,
                reasoning_effort,
                agent_mode=agent_mode,
                session_id=session_id,
                json_output=True,
                ephemeral=ephemeral,
                bypass_sandbox=bypass_sandbox,
            )

            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            active_session_id = session_id
            progress_lines = []
            assert process.stdout is not None
            for line in process.stdout:
                active_session_id = _codex_thread_id(line) or active_session_id
                message = _codex_progress_message(line)
                if message:
                    progress_lines.append(message)

            returncode = process.wait(timeout=timeout_seconds)
            output = Path(output_path).read_text(encoding="utf-8").strip()
            if returncode != 0:
                detail = _codex_failure_detail(output, progress_lines)
                if (
                    not bypass_sandbox
                    and capabilities.get("supports_dangerous_bypass")
                    and _is_codex_sandbox_bootstrap_failure(detail)
                ):
                    bypass_sandbox = True
                    continue
                raise HTTPException(status_code=400, detail=detail)

            reply = output.strip()
            if not reply:
                raise HTTPException(status_code=500, detail="Codex CLI returned no output.")

            return {
                "reply": reply,
                "model": _codex_model_label(model_name, reasoning_effort),
                "runtime": "codex",
                "session_id": active_session_id if capabilities["supports_resume"] else "",
            }
        finally:
            Path(output_path).unlink(missing_ok=True)


def _build_cursor_command(
    cursor_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    stream_json: bool = False,
    agent_mode: str | None = None,
) -> list[str]:
    command = [cursor_path, "--force", "--print"]
    if session_id:
        command.extend(["--resume", session_id])
    command.extend(["-p", prompt_text])
    if model_name:
        command.extend(["--model", model_name])
    command.extend(["--output-format", "stream-json" if stream_json else "json"])
    return command


def _cursor_session_id(payload: dict) -> str | None:
    if payload.get("session_id"):
        return str(payload["session_id"])
    message = payload.get("message")
    if isinstance(message, dict) and message.get("session_id"):
        return str(message["session_id"])
    return None


def _cursor_message_text(payload: dict) -> str:
    if isinstance(payload.get("result"), str):
        return payload["result"].strip()
    if isinstance(payload.get("content"), str):
        return payload["content"].strip()

    message = payload.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
            continue
        if isinstance(item.get("text"), str) and item.get("text").strip():
            parts.append(item["text"])
    return "\n".join(part for part in parts if part).strip()


def _cursor_tool_message(payload: dict, transcript: bool = False) -> str | None:
    tool_name = ""
    args = {}

    if payload.get("type") in {"tool_call", "tool_use"}:
        tool_name = str(payload.get("tool_name") or payload.get("name") or payload.get("tool") or "")
        raw_args = payload.get("parameters") or payload.get("arguments") or payload.get("args") or payload.get("input") or {}
        if isinstance(raw_args, dict):
            args = raw_args
    else:
        tool_call = payload.get("tool_call") or payload.get("toolCall")
        if isinstance(tool_call, dict) and tool_call:
            raw_name, raw_args = next(iter(tool_call.items()))
            tool_name = str(raw_name or "")
            if isinstance(raw_args, dict):
                args = raw_args

    if not tool_name:
        return None

    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", tool_name.replace("ToolCall", "").replace("tool_call", "")).replace("-", "_").lower()
    path = str(args.get("path") or args.get("file_path") or args.get("file") or args.get("filename") or args.get("relative_path") or "").strip()
    query = str(args.get("query") or args.get("pattern") or args.get("search") or args.get("term") or "").strip()
    cmd = str(args.get("command") or args.get("cmd") or "").strip()

    if normalized in {"read", "read_file", "open", "view_file", "cat"}:
        return f"Reading file: {path}" if path else "Reading file."
    if normalized in {"write", "write_file", "edit", "edit_file", "apply_patch", "replace", "str_replace"}:
        return f"Updating file: {path}" if path else "Updating file."
    if normalized in {"search", "grep", "find", "find_files", "glob", "search_files"}:
        target = query or path
        return f"Searching: {target}" if target else "Searching codebase."
    if normalized in {"run_command", "bash", "shell", "exec", "run", "terminal"}:
        return f"Running shell command: {cmd}" if cmd else "Running command."
    if normalized in {"list_files", "ls", "list_directory", "readdir"}:
        return f"Listing directory: {path}" if path else "Listing files."
    if transcript and args:
        return f"Using {tool_name}: {_compact_cli_payload(args)}"
    return f"Using {tool_name}."


def _cursor_progress_message(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    subtype = payload.get("subtype") or ""

    if event_type == "system" and subtype == "init":
        model = payload.get("model") or ""
        return f"Starting Cursor{' with ' + str(model) if model else ''}..."
    if event_type == "assistant":
        text = _cursor_message_text(payload)
        return text if text else "Cursor is responding..."
    if event_type in {"tool_call", "tool_use"} or payload.get("tool_call") or payload.get("toolCall"):
        return _cursor_tool_message(payload)
    if event_type == "result":
        if payload.get("is_error"):
            return payload.get("result") or "Cursor reported an error."
        return "Turn complete."
    if event_type == "system" and payload.get("message"):
        return str(payload["message"])
    if event_type == "error":
        return str(payload.get("message") or "Cursor reported an error.")
    if subtype:
        return subtype.replace("_", " ").title()
    if event_type and event_type != "user":
        return event_type.replace("_", " ").title()
    return None


def _cursor_transcript_line(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    subtype = payload.get("subtype") or ""

    if event_type == "system" and subtype == "init":
        model = payload.get("model") or "Cursor"
        return f"Cursor session started with {model}."
    if event_type == "assistant":
        text = _cursor_message_text(payload)
        if text:
            return f"Cursor: {text}"
        return None
    if event_type in {"tool_call", "tool_use"} or payload.get("tool_call") or payload.get("toolCall"):
        return _cursor_tool_message(payload, transcript=True)
    if event_type == "result":
        if payload.get("is_error"):
            return payload.get("result") or "Cursor reported an error."
        return "Cursor turn complete."
    if event_type == "error":
        return str(payload.get("message") or "Cursor reported an error.")
    if event_type == "system" and payload.get("message"):
        return str(payload["message"])
    if subtype:
        return f"[{event_type}.{subtype}]"
    if event_type and event_type != "user":
        return f"[{event_type}]"
    return None


def _run_cursor_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    timeout_seconds: int = 1800,
    agent_mode: str | None = None,
) -> dict:
    cursor_path = shutil.which("cursor-agent")
    if not cursor_path:
        raise HTTPException(status_code=400, detail="Cursor CLI is not installed.")

    command = _build_cursor_command(
        cursor_path,
        prompt_text,
        model_name,
        session_id=session_id,
        stream_json=False,
        agent_mode=agent_mode,
    )
    result = _run_external_command(command, workspace_path, timeout_seconds=timeout_seconds)
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=output or "Cursor CLI failed.")
    if not output:
        raise HTTPException(status_code=500, detail="Cursor CLI returned no output.")

    try:
        payload = json.loads(output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Cursor CLI returned invalid JSON.") from exc

    if payload.get("is_error"):
        raise HTTPException(status_code=400, detail=payload.get("result") or "Cursor CLI failed.")

    reply = _cursor_message_text(payload)
    if not reply:
        raise HTTPException(status_code=500, detail="Cursor CLI returned no output.")

    return {
        "reply": reply,
        "model": _resolved_runtime_model_id("cursor", model_name),
        "runtime": "cursor",
        "session_id": _cursor_session_id(payload) or session_id or "",
    }


def _build_claude_command(
    claude_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    stream_json: bool = False,
    verbose: bool = False,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
) -> list[str]:
    effective_agent_mode = _normalize_agent_mode(agent_mode) or _runtime_default_agent_mode("claude")
    command = [claude_path]
    if effective_agent_mode == "plan":
        command.extend(["--permission-mode", "plan"])
    elif effective_agent_mode == "auto_edit":
        command.extend(["--permission-mode", "acceptEdits"])
    else:
        command.append("--dangerously-skip-permissions")
    if session_id:
        command.extend(["--resume", session_id])
    command.extend(["-p", prompt_text])
    if model_name:
        command.extend(["--model", model_name])
    if reasoning_effort:
        command.extend(["--effort", reasoning_effort])
    if stream_json:
        command.extend(["--output-format", "stream-json"])
    else:
        command.extend(["--output-format", "json"])
    if verbose:
        command.append("--verbose")
    return command


def _claude_session_id(payload: dict) -> str | None:
    if payload.get("session_id"):
        return payload.get("session_id")
    message = payload.get("message")
    if isinstance(message, dict) and message.get("session_id"):
        return message.get("session_id")
    return None


def _claude_message_text(payload: dict) -> str:
    if isinstance(payload.get("result"), str):
        return payload["result"].strip()
    message = payload.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(part for part in parts if part).strip()


def _claude_progress_message(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    subtype = payload.get("subtype") or ""

    if event_type == "init":
        return "Session started."
    if event_type == "assistant":
        text = _claude_message_text(payload)
        return text if text else "Claude is responding..."
    if event_type == "user":
        return None
    if event_type == "result":
        if payload.get("is_error"):
            return payload.get("result") or "Claude reported an error."
        return "Turn complete."
    if event_type == "system" and payload.get("message"):
        return str(payload["message"])
    if subtype:
        return subtype.replace("_", " ").title()
    if event_type:
        return event_type.replace("_", " ").replace(".", " ").title()
    return None


def _claude_terminal_output(payload: dict) -> str | None:
    """Format a Claude CLI stream-json event into human-readable terminal lines."""
    event_type = payload.get("type") or ""
    subtype = payload.get("subtype") or ""

    if event_type == "system":
        if subtype == "init":
            model = payload.get("model") or "Claude"
            return f"◆ Session · {model}"
        if subtype == "api_retry":
            attempt = payload.get("attempt")
            max_retries = payload.get("max_retries")
            error_text = payload.get("error") or "retrying"
            suffix = f" ({attempt}/{max_retries})" if attempt and max_retries else ""
            return f"⚠ API retry{suffix}: {error_text}"
        msg = payload.get("message")
        if msg:
            return f"  {msg}"
        return None

    if event_type == "assistant":
        message = payload.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            return None
        lines = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type") or ""
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif btype == "tool_use":
                name = block.get("name") or "tool"
                inp = block.get("input") or {}
                path = (
                    inp.get("file_path")
                    or inp.get("path")
                    or inp.get("relative_path")
                    or inp.get("notebook_path")
                    or ""
                )
                cmd = inp.get("command") or inp.get("cmd") or ""
                pattern = inp.get("pattern") or inp.get("query") or inp.get("description") or ""
                if path:
                    lines.append(f"▶ {name}  {path}")
                elif cmd:
                    short_cmd = cmd[:120] + "…" if len(cmd) > 120 else cmd
                    lines.append(f"▶ {name}  {short_cmd}")
                elif pattern:
                    short_pat = pattern[:120] + "…" if len(pattern) > 120 else pattern
                    lines.append(f"▶ {name}  {short_pat}")
                else:
                    lines.append(f"▶ {name}")
            elif btype == "thinking":
                thought = (block.get("thinking") or "").strip()
                if thought:
                    preview = thought[:200] + "…" if len(thought) > 200 else thought
                    lines.append(f"  [thinking] {preview}")
        return "\n".join(lines) if lines else None

    if event_type == "user":
        message = payload.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            return None
        lines = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                rc = block.get("content") or ""
                if isinstance(rc, list):
                    text = "\n".join(
                        b.get("text", "") for b in rc if isinstance(b, dict) and b.get("type") == "text"
                    ).strip()
                else:
                    text = str(rc).strip()
                if text:
                    preview = text[:300] + "…" if len(text) > 300 else text
                    lines.append(preview)
        return "\n".join(lines) if lines else None

    if event_type == "result":
        if payload.get("is_error"):
            return f"✗ {payload.get('result') or 'Error'}"
        return "✓ Done"

    return None


def _claude_transcript_line(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    subtype = payload.get("subtype") or ""

    if event_type == "system" and subtype == "init":
        model = payload.get("model") or "Claude"
        return f"Claude session started with {model}."
    if event_type == "system" and subtype == "api_retry":
        attempt = payload.get("attempt")
        max_retries = payload.get("max_retries")
        error_text = payload.get("error") or "unknown error"
        if attempt and max_retries:
            return f"Claude API retry {attempt}/{max_retries}: {error_text}"
        return f"Claude API retry: {error_text}"
    if event_type == "assistant":
        text = _claude_message_text(payload)
        if text:
            return f"Claude: {text}"
    if event_type == "result":
        if payload.get("is_error"):
            return payload.get("result") or "Claude reported an error."
        return "Claude turn complete."
    if event_type == "system" and payload.get("message"):
        return str(payload["message"])
    if subtype:
        return f"[{event_type}.{subtype}]"
    if event_type and event_type != "user":
        return f"[{event_type}]"
    return None


def _json_object_line_payload(line: str) -> dict | None:
    stripped = str(line or "").strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _is_claude_result_payload(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("type") == "result":
        return True
    return "result" in payload and "is_error" in payload


def _extract_claude_terminal_result_payload(output_text: str) -> dict | None:
    for line in reversed(str(output_text or "").splitlines()):
        payload = _json_object_line_payload(line)
        if _is_claude_result_payload(payload):
            return payload
    return None


def _sanitize_claude_terminal_output(output_text: str) -> str:
    lines = str(output_text or "").splitlines(keepends=True)
    if not lines:
        return ""

    trailing_blank_count = 0
    index = len(lines) - 1
    while index >= 0 and not lines[index].strip():
        trailing_blank_count += 1
        index -= 1

    if index < 0:
        return ""

    payload = _json_object_line_payload(lines[index])
    if not _is_claude_result_payload(payload):
        return str(output_text or "")

    sanitized = "".join(lines[:index] + lines[index + 1:])
    if trailing_blank_count:
        sanitized = sanitized.rstrip("\r\n")
    return sanitized


def _run_claude_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    timeout_seconds: int = 1800,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
) -> dict:
    claude_path = shutil.which("claude")
    if not claude_path:
        raise HTTPException(status_code=400, detail="Claude CLI is not installed.")

    command = _build_claude_command(
        claude_path,
        prompt_text,
        model_name,
        session_id=session_id,
        stream_json=False,
        reasoning_effort=reasoning_effort,
        agent_mode=agent_mode,
    )
    result = _run_external_command(command, workspace_path, timeout_seconds=timeout_seconds)
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=output or "Claude CLI failed.")
    if not output:
        raise HTTPException(status_code=500, detail="Claude CLI returned no output.")

    try:
        payload = json.loads(output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Claude CLI returned invalid JSON.") from exc

    if payload.get("is_error"):
        raise HTTPException(status_code=400, detail=payload.get("result") or "Claude CLI failed.")

    reply = _claude_message_text(payload)
    if not reply:
        raise HTTPException(status_code=500, detail="Claude CLI returned no output.")

    return {
        "reply": reply,
        "model": _resolved_runtime_model_id("claude", model_name, reasoning_effort),
        "runtime": "claude",
        "session_id": _claude_session_id(payload),
    }


def _run_gemini_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    timeout_seconds: int = 1800,
    agent_mode: str | None = None,
) -> dict:
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        raise HTTPException(status_code=400, detail="Gemini CLI is not installed.")

    command = _build_gemini_command(gemini_path, prompt_text, model_name, agent_mode=agent_mode)

    result = _run_external_command(command, workspace_path, timeout_seconds=timeout_seconds)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Gemini CLI failed.").strip()
        raise HTTPException(status_code=400, detail=detail)

    reply = (result.stdout or result.stderr).strip()
    if not reply:
        raise HTTPException(status_code=500, detail="Gemini CLI returned no output.")

    return {
        "reply": reply,
        "model": f"gemini/{model_name}" if model_name else "gemini/default",
        "runtime": "gemini",
    }


def _run_orchestrated_codex_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
    workspace_id: int | None = None,
    stream_handler: Callable[[dict], None] | None = None,
) -> dict:
    codex_path = shutil.which("codex")
    if not codex_path:
        raise HTTPException(status_code=400, detail="Codex CLI is not installed.")
    capabilities = _codex_exec_capabilities(codex_path)

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as output_file:
        output_path = output_file.name

    process = None
    try:
        active_session_id = ""
        progress_lines = []
        if sys.platform != "win32" and hasattr(os, "openpty") and capabilities["supports_color"]:
            command = _build_codex_command(
                codex_path,
                workspace_path,
                output_path,
                prompt_text,
                model_name,
                reasoning_effort,
                agent_mode=agent_mode,
                terminal_output=True,
                ephemeral=True,
            )
            master_fd, slave_fd = os.openpty()
            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                env={
                    **os.environ,
                    "TERM": os.environ.get("TERM") or "xterm-256color",
                },
            )
            os.close(slave_fd)
            _register_orchestrated_process(workspace_id, process, "multi")

            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            line_carry = ""
            last_prompt = ""
            try:
                while True:
                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                    if ready:
                        try:
                            chunk = os.read(master_fd, 4096)
                        except OSError:
                            chunk = b""
                        if chunk:
                            text = decoder.decode(chunk)
                            if text:
                                _touch_active_chat_process(workspace_id)
                                _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=text)
                                lines, line_carry = _extract_terminal_lines(text, line_carry)
                                progress_lines.extend(lines)
                                for line in lines:
                                    _emit_orchestrated_stream_event(stream_handler, "history_line", text=line)
                                    normalized_prompt = _pending_input_prompt(line, last_prompt)
                                    if workspace_id is None or not normalized_prompt:
                                        continue
                                    last_prompt = normalized_prompt
                                    _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                                    _write_chat_input_to_fd(master_fd, _wait_for_prompt_input(workspace_id))
                        elif process.poll() is not None:
                            break

                    if process.poll() is not None and not ready:
                        break
            finally:
                try:
                    remainder = decoder.decode(b"", final=True)
                except Exception:
                    remainder = ""
                if remainder:
                    _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=remainder)
                    lines, line_carry = _extract_terminal_lines(remainder, line_carry)
                    progress_lines.extend(lines)
                    for line in lines:
                        _emit_orchestrated_stream_event(stream_handler, "history_line", text=line)
                if line_carry.strip():
                    final_line = line_carry.strip()
                    progress_lines.append(final_line)
                    _emit_orchestrated_stream_event(stream_handler, "history_line", text=final_line)
                try:
                    os.close(master_fd)
                except OSError:
                    pass
        else:
            command = _build_codex_command(
                codex_path,
                workspace_path,
                output_path,
                prompt_text,
                model_name,
                reasoning_effort,
                agent_mode=agent_mode,
                json_output=True,
                ephemeral=True,
            )
            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
            )
            _register_orchestrated_process(workspace_id, process, "multi")

            last_prompt = ""
            assert process.stdout is not None
            for line in process.stdout:
                raw_line = _raw_cli_output_line(line)
                if raw_line:
                    _touch_active_chat_process(workspace_id)
                    _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=line)
                active_session_id = _codex_thread_id(line) or active_session_id
                message = _codex_progress_message(line)
                terminal = _codex_transcript_line(line)
                if message:
                    progress_lines.append(message)
                    _touch_active_chat_process(workspace_id)
                if terminal:
                    _emit_orchestrated_stream_event(stream_handler, "history_line", text=terminal)
                normalized_prompt = _pending_input_prompt(message or terminal, last_prompt)
                if workspace_id is not None and normalized_prompt:
                    last_prompt = normalized_prompt
                    _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                    _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))

        returncode = _wait_for_process(process, workspace_id)
        output = Path(output_path).read_text(encoding="utf-8").strip()
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        if returncode != 0:
            detail = _codex_failure_detail(output, progress_lines)
            raise HTTPException(status_code=400, detail=detail)

        reply = output.strip()
        if not reply:
            raise HTTPException(status_code=500, detail="Codex CLI returned no output.")

        return {
            "reply": reply,
            "model": _codex_model_label(model_name, reasoning_effort),
            "runtime": "codex",
            "session_id": active_session_id if capabilities["supports_resume"] else "",
        }
    finally:
        if process is not None:
            _unregister_orchestrated_process(workspace_id, process.pid)
        Path(output_path).unlink(missing_ok=True)


def _run_orchestrated_cursor_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    agent_mode: str | None = None,
    workspace_id: int | None = None,
    stream_handler: Callable[[dict], None] | None = None,
) -> dict:
    cursor_path = shutil.which("cursor-agent")
    if not cursor_path:
        raise HTTPException(status_code=400, detail="Cursor CLI is not installed.")

    command = _build_cursor_command(
        cursor_path,
        prompt_text,
        model_name,
        session_id=session_id,
        stream_json=True,
        agent_mode=agent_mode,
    )
    process = subprocess.Popen(
        command,
        cwd=workspace_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
    )
    _register_orchestrated_process(workspace_id, process, "multi")

    reply_parts = []
    final_reply = ""
    progress_lines = []
    active_session_id = session_id or ""
    last_prompt = ""
    assert process.stdout is not None
    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            raw_line = _raw_cli_output_line(line)
            if raw_line:
                _touch_active_chat_process(workspace_id)
                _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=line)

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                progress_lines.append(stripped)
                _touch_active_chat_process(workspace_id)
                _emit_orchestrated_stream_event(stream_handler, "history_line", text=stripped)
                normalized_prompt = _pending_input_prompt(stripped, last_prompt)
                if workspace_id is not None and normalized_prompt:
                    last_prompt = normalized_prompt
                    _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                    _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))
                continue

            active_session_id = _cursor_session_id(payload) or active_session_id
            prompt_candidate = ""
            if payload.get("type") == "assistant":
                content = _cursor_message_text(payload)
                if content:
                    if payload.get("delta") or payload.get("subtype") in {"delta", "message_delta"}:
                        reply_parts.append(content)
                    elif not reply_parts:
                        reply_parts.append(content)
                    prompt_candidate = content
            if payload.get("type") == "result" and isinstance(payload.get("result"), str):
                final_reply = payload["result"].strip()

            message = _cursor_progress_message(payload)
            transcript = _cursor_transcript_line(payload)
            if message:
                progress_lines.append(message)
                _touch_active_chat_process(workspace_id)
            if transcript:
                _emit_orchestrated_stream_event(stream_handler, "history_line", text=transcript)
            normalized_prompt = _pending_input_prompt(prompt_candidate or message, last_prompt)
            if workspace_id is not None and normalized_prompt:
                last_prompt = normalized_prompt
                _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))

        returncode = _wait_for_process(process, workspace_id)
        reply = (final_reply or "".join(reply_parts)).strip()
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        if returncode != 0:
            detail = reply or (progress_lines[-1] if progress_lines else "Cursor CLI failed.")
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Cursor CLI returned no output.")

        return {
            "reply": reply,
            "model": _resolved_runtime_model_id("cursor", model_name),
            "runtime": "cursor",
            "session_id": active_session_id,
        }
    finally:
        _unregister_orchestrated_process(workspace_id, process.pid)


def _run_orchestrated_claude_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
    workspace_id: int | None = None,
    stream_handler: Callable[[dict], None] | None = None,
) -> dict:
    claude_path = shutil.which("claude")
    if not claude_path:
        raise HTTPException(status_code=400, detail="Claude CLI is not installed.")

    command = _build_claude_command(
        claude_path,
        prompt_text,
        model_name,
        stream_json=False,
        reasoning_effort=reasoning_effort,
        agent_mode=agent_mode,
    )
    process = None
    active_session_id = ""
    reply = ""
    progress_lines = []
    use_pty = sys.platform != "win32" and hasattr(os, "openpty")
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text_accumulator: list[str] = []
    line_carry = ""
    last_prompt = ""

    def _drain_chunk(raw_bytes: bytes | str):
        nonlocal line_carry, last_prompt
        text = decoder.decode(raw_bytes) if isinstance(raw_bytes, bytes) else str(raw_bytes)
        if not text:
            return
        _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=text)
        stripped = _strip_ansi(text)
        text_accumulator.append(stripped)
        lines, line_carry = _extract_terminal_lines(stripped, line_carry)
        progress_lines.extend(lines)
        for line in lines:
            normalized_prompt = _pending_input_prompt(line, last_prompt)
            if workspace_id is None or not normalized_prompt:
                continue
            last_prompt = normalized_prompt
            _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
            user_input = _wait_for_prompt_input(workspace_id)
            if use_pty:
                _write_chat_input_to_fd(master_fd, user_input)
            else:
                _write_chat_input_to_process(process, user_input)
        if stripped.strip():
            _touch_active_chat_process(workspace_id)

    def _extract_final_json() -> dict | None:
        full_text = "".join(text_accumulator)
        for line in reversed(full_text.splitlines()):
            stripped = line.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    continue
        return None

    try:
        if use_pty:
            master_fd, slave_fd = os.openpty()
            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                env={**os.environ, "TERM": "xterm-256color"},
            )
            os.close(slave_fd)
            _register_orchestrated_process(workspace_id, process, "multi")

            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        chunk = b""
                    if chunk:
                        _touch_active_chat_process(workspace_id)
                        _drain_chunk(chunk)
                    elif process.poll() is not None:
                        break
                elif process.poll() is not None:
                    break

            try:
                remainder = decoder.decode(b"", final=True)
            except Exception:
                remainder = ""
            if remainder:
                _drain_chunk(remainder)
            try:
                os.close(master_fd)
            except OSError:
                pass
        else:
            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
            )
            _register_orchestrated_process(workspace_id, process, "multi")

            assert process.stdout is not None
            for raw_bytes in process.stdout:
                _touch_active_chat_process(workspace_id)
                _drain_chunk(raw_bytes)

        returncode = _wait_for_process(process, workspace_id)
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        final_payload = _extract_final_json()
        if final_payload is not None:
            active_session_id = _claude_session_id(final_payload) or active_session_id
            if final_payload.get("is_error"):
                raise HTTPException(
                    status_code=400,
                    detail=final_payload.get("result") or "Claude CLI failed.",
                )
            reply = _claude_message_text(final_payload) or reply
        if returncode != 0:
            detail = reply or (progress_lines[-1] if progress_lines else "Claude CLI failed.")
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Claude CLI returned no output.")

        return {
            "reply": reply,
            "model": _resolved_runtime_model_id("claude", model_name, reasoning_effort),
            "runtime": "claude",
            "session_id": active_session_id,
        }
    finally:
        if process is not None:
            _unregister_orchestrated_process(workspace_id, process.pid)


def _run_orchestrated_gemini_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    agent_mode: str | None = None,
    workspace_id: int | None = None,
    stream_handler: Callable[[dict], None] | None = None,
) -> dict:
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        raise HTTPException(status_code=400, detail="Gemini CLI is not installed.")

    command = _build_gemini_command(gemini_path, prompt_text, model_name, stream_json=True, agent_mode=agent_mode)
    process = subprocess.Popen(
        command,
        cwd=workspace_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
    )
    _register_orchestrated_process(workspace_id, process, "multi")

    reply_parts = []
    progress_lines = []
    last_prompt = ""
    assert process.stdout is not None
    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            raw_line = _raw_cli_output_line(line)
            if raw_line:
                _touch_active_chat_process(workspace_id)
                _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=line)

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                progress_lines.append(stripped)
                _touch_active_chat_process(workspace_id)
                _emit_orchestrated_stream_event(stream_handler, "history_line", text=stripped)
                normalized_prompt = _pending_input_prompt(stripped, last_prompt)
                if workspace_id is not None and normalized_prompt:
                    last_prompt = normalized_prompt
                    _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                    _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))
                continue

            prompt_candidate = ""
            if payload.get("type") == "message" and payload.get("role") == "assistant":
                content = str(payload.get("content") or "")
                if content:
                    if payload.get("delta"):
                        reply_parts.append(content)
                    elif not reply_parts:
                        reply_parts.append(content)
                    prompt_candidate = content.strip()

            message = _gemini_progress_message(payload)
            terminal = _gemini_transcript_line(payload)
            if message:
                progress_lines.append(message)
                _touch_active_chat_process(workspace_id)
            if terminal:
                _emit_orchestrated_stream_event(stream_handler, "history_line", text=terminal)
            normalized_prompt = _pending_input_prompt(prompt_candidate, last_prompt)
            if workspace_id is not None and normalized_prompt:
                last_prompt = normalized_prompt
                _emit_orchestrated_stream_event(stream_handler, "input_required", prompt=normalized_prompt)
                _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))

        returncode = _wait_for_process(process, workspace_id)
        reply = "".join(reply_parts).strip()
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        if returncode != 0:
            detail = reply or (progress_lines[-1] if progress_lines else "Gemini CLI failed.")
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Gemini CLI returned no output.")

        return {
            "reply": reply,
            "model": f"gemini/{model_name}" if model_name else "gemini/default",
            "runtime": "gemini",
        }
    finally:
        _unregister_orchestrated_process(workspace_id, process.pid)


def _run_orchestrated_task_cli(
    workspace_path: str,
    prompt_text: str,
    selected_model: str,
    agent_mode: str | None = None,
    workspace_id: int | None = None,
    stream_handler: Callable[[dict], None] | None = None,
) -> dict:
    runtime, model_name, reasoning_effort = _resolve_runtime_model(selected_model)
    runtime_prompt = prompt_text + _runtime_prompt_suffix(runtime)
    if runtime == "local":
        result = run_local_model_response(
            prompt_text,
            model_id=model_name,
            human_language=get_human_language(),
        )
    elif runtime == "codex":
        result = _run_orchestrated_codex_cli(
            workspace_path,
            runtime_prompt,
            model_name,
            reasoning_effort=reasoning_effort,
            agent_mode=agent_mode,
            workspace_id=workspace_id,
            stream_handler=stream_handler,
        )
    elif runtime == "cursor":
        result = _run_orchestrated_cursor_cli(
            workspace_path,
            runtime_prompt,
            model_name,
            agent_mode=agent_mode,
            workspace_id=workspace_id,
            stream_handler=stream_handler,
        )
    elif runtime == "claude":
        result = _run_orchestrated_claude_cli(
            workspace_path,
            runtime_prompt,
            model_name,
            reasoning_effort=reasoning_effort,
            agent_mode=agent_mode,
            workspace_id=workspace_id,
            stream_handler=stream_handler,
        )
    else:
        result = _run_orchestrated_gemini_cli(
            workspace_path,
            runtime_prompt,
            model_name,
            agent_mode=agent_mode,
            workspace_id=workspace_id,
            stream_handler=stream_handler,
        )
    result["reply"] = _normalize_cli_reply(result.get("reply", ""), runtime)
    return result


def _build_gemini_command(
    gemini_path: str,
    prompt_text: str,
    model_name: str | None,
    stream_json: bool = False,
    agent_mode: str | None = None,
) -> list[str]:
    effective_agent_mode = _normalize_agent_mode(agent_mode) or _runtime_default_agent_mode("gemini")
    approval_mode = {
        "plan": "plan",
        "auto_edit": "auto_edit",
        "full_agentic": "yolo",
    }.get(effective_agent_mode, "yolo")
    command = [gemini_path, "--approval-mode", approval_mode, "-p", prompt_text]
    if model_name:
        command.extend(["-m", model_name])
    if stream_json:
        command.extend(["--output-format", "stream-json"])
    return command


def _gemini_progress_message(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    if event_type == "init":
        model = payload.get("model") or ""
        return f"Starting Gemini{' with ' + model if model else ''}..."
    if event_type == "tool_use":
        tool_name = str(payload.get("tool_name") or "tool").lower().replace("-", "_")
        params = payload.get("parameters") or {}
        path = params.get("path") or params.get("file") or params.get("filename") or ""
        query = params.get("query") or params.get("pattern") or params.get("search") or ""
        cmd = params.get("command") or params.get("cmd") or ""
        if tool_name in ("read_file", "read", "open", "view_file", "cat"):
            return f"Reading file: {path}" if path else "Reading file."
        if tool_name in ("write_file", "write", "create_file", "save_file"):
            return f"Updating file: {path}" if path else "Updating file."
        if tool_name in ("edit_file", "apply_patch", "patch", "replace", "str_replace"):
            return f"Applying changes: {path}" if path else "Applying changes."
        if tool_name in ("search", "grep", "find", "find_files", "glob", "search_files"):
            target = query or path
            return f"Searching: {target}" if target else "Searching codebase."
        if tool_name in ("run_command", "bash", "shell", "exec", "run"):
            return f"Running shell command: {cmd}" if cmd else "Running command."
        if tool_name in ("list_files", "ls", "list_directory", "readdir"):
            return f"Listing directory: {path}" if path else "Listing files."
        return f"Using {tool_name}."
    if event_type == "tool_result":
        status = payload.get("status") or "ok"
        output = str(payload.get("output") or "").strip()
        if output and len(output) < 120:
            return f"Tool result: {output}"
        return f"Tool result: {status}."
    if event_type == "error":
        return payload.get("message") or "Gemini reported an error."
    if event_type == "result":
        error_payload = payload.get("error")
        if isinstance(error_payload, dict) and error_payload.get("message"):
            return error_payload["message"]
        return "Turn complete."
    if event_type:
        return event_type.replace("_", " ").replace(".", " ").title()
    return None


def _gemini_transcript_line(payload: dict) -> str | None:
    event_type = payload.get("type") or ""
    if event_type == "init":
        model = payload.get("model") or "Gemini"
        return f"Gemini session started with {model}."
    if event_type == "message":
        role = payload.get("role")
        content = str(payload.get("content") or "").strip()
        if role == "assistant" and content and not payload.get("delta"):
            return f"Gemini: {content}"
        return None
    if event_type == "tool_use":
        tool_name = payload.get("tool_name") or "tool"
        parameters = payload.get("parameters")
        if isinstance(parameters, dict) and parameters:
            return f"Using {tool_name}: {_compact_cli_payload(parameters)}"
        return f"Using {tool_name}."
    if event_type == "tool_result":
        status = payload.get("status") or "unknown"
        output = str(payload.get("output") or "").strip()
        if output:
            return f"Tool result ({status}): {output}"
        error_payload = payload.get("error")
        if isinstance(error_payload, dict) and error_payload.get("message"):
            return f"Tool result ({status}): {error_payload['message']}"
        return f"Tool result: {status}."
    if event_type == "error":
        return payload.get("message") or "Gemini reported an error."
    if event_type == "result":
        error_payload = payload.get("error")
        if isinstance(error_payload, dict) and error_payload.get("message"):
            return error_payload["message"]
        return "Gemini turn complete."
    if event_type:
        return f"[{event_type}]"
    return None


def _stream_cursor_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    agent_mode: str | None = None,
    activity_log: list[str] | None = None,
    history_log: list[str] | None = None,
    workspace_id: int | None = None,
    terminal_log: list[str] | None = None,
):
    cursor_path = shutil.which("cursor-agent")
    if not cursor_path:
        raise HTTPException(status_code=400, detail="Cursor CLI is not installed.")

    command = _build_cursor_command(
        cursor_path,
        prompt_text,
        model_name,
        session_id=session_id,
        stream_json=True,
        agent_mode=agent_mode,
    )
    process = subprocess.Popen(
        command,
        cwd=workspace_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
    )
    if workspace_id is not None:
        _register_active_chat_process(workspace_id, process, "cursor")

    reply_parts = []
    final_reply = ""
    progress_lines = []
    active_session_id = session_id or ""
    last_prompt = ""
    assert process.stdout is not None
    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            raw_line = _raw_cli_output_line(line)
            if raw_line:
                _append_terminal_chunk(terminal_log, line)
                _touch_active_chat_process(workspace_id)
                yield _stream_event_bytes("terminal_chunk", text=line)

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                progress_lines.append(stripped)
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    transcript=raw_line,
                )
                normalized_prompt = _pending_input_prompt(stripped, last_prompt)
                if workspace_id is not None and normalized_prompt:
                    last_prompt = normalized_prompt
                    yield _stream_event_bytes("input_required", prompt=normalized_prompt)
                    _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))
                continue

            active_session_id = _cursor_session_id(payload) or active_session_id
            if payload.get("type") == "assistant":
                content = _cursor_message_text(payload)
                if content:
                    if payload.get("delta") or payload.get("subtype") in {"delta", "message_delta"}:
                        reply_parts.append(content)
                    elif not reply_parts:
                        reply_parts.append(content)
            prompt_candidate = ""
            if payload.get("type") == "assistant":
                prompt_candidate = _cursor_message_text(payload)
            if payload.get("type") == "result" and isinstance(payload.get("result"), str):
                final_reply = payload["result"].strip()

            message = _cursor_progress_message(payload)
            transcript = _cursor_transcript_line(payload)
            if message:
                progress_lines.append(message)
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    message=message,
                    transcript=raw_line,
                )
            elif transcript:
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    transcript=raw_line,
                )
            normalized_prompt = _pending_input_prompt(prompt_candidate or message, last_prompt)
            if workspace_id is not None and normalized_prompt:
                last_prompt = normalized_prompt
                yield _stream_event_bytes("input_required", prompt=normalized_prompt)
                _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))

        returncode = _wait_for_process(process, workspace_id)
        reply = (final_reply or "".join(reply_parts)).strip()
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        if returncode != 0:
            detail = reply or (progress_lines[-1] if progress_lines else "Cursor CLI failed.")
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Cursor CLI returned no output.")

        return {
            "reply": reply,
            "model": _resolved_runtime_model_id("cursor", model_name),
            "runtime": "cursor",
            "session_id": active_session_id,
        }
    finally:
        if workspace_id is not None:
            _clear_active_chat_process(workspace_id)


def _stream_gemini_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    agent_mode: str | None = None,
    activity_log: list[str] | None = None,
    history_log: list[str] | None = None,
    workspace_id: int | None = None,
    terminal_log: list[str] | None = None,
):
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        raise HTTPException(status_code=400, detail="Gemini CLI is not installed.")

    command = _build_gemini_command(gemini_path, prompt_text, model_name, stream_json=True, agent_mode=agent_mode)
    process = subprocess.Popen(
        command,
        cwd=workspace_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
    )
    if workspace_id is not None:
        _register_active_chat_process(workspace_id, process, "gemini")

    reply_parts = []
    progress_lines = []
    last_prompt = ""
    assert process.stdout is not None
    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            raw_line = _raw_cli_output_line(line)
            if raw_line:
                _touch_active_chat_process(workspace_id)
                _append_terminal_chunk(terminal_log, line)
                yield _stream_event_bytes("terminal_chunk", text=line)

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                progress_lines.append(stripped)
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    transcript=raw_line,
                )
                normalized_prompt = _pending_input_prompt(stripped, last_prompt)
                if workspace_id is not None and normalized_prompt:
                    last_prompt = normalized_prompt
                    yield _stream_event_bytes("input_required", prompt=normalized_prompt)
                    _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))
                continue

            if payload.get("type") == "message" and payload.get("role") == "assistant":
                content = str(payload.get("content") or "")
                if content:
                    if payload.get("delta"):
                        reply_parts.append(content)
                    elif not reply_parts:
                        reply_parts.append(content)
            prompt_candidate = ""
            if payload.get("type") == "message" and payload.get("role") == "assistant":
                prompt_candidate = str(payload.get("content") or "").strip()

            message = _gemini_progress_message(payload)
            transcript = _gemini_transcript_line(payload)
            if message:
                progress_lines.append(message)
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    message=message,
                    transcript=raw_line,
                )
            elif transcript:
                _touch_active_chat_process(workspace_id)
                yield _emit_status_event(
                    activity_log,
                    history_log,
                    transcript=raw_line,
                )
            normalized_prompt = _pending_input_prompt(prompt_candidate, last_prompt)
            if workspace_id is not None and normalized_prompt:
                last_prompt = normalized_prompt
                yield _stream_event_bytes("input_required", prompt=normalized_prompt)
                _write_chat_input_to_process(process, _wait_for_prompt_input(workspace_id))

        returncode = _wait_for_process(process, workspace_id)
        reply = "".join(reply_parts).strip()
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")
        if returncode != 0:
            detail = reply or (progress_lines[-1] if progress_lines else "Gemini CLI failed.")
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Gemini CLI returned no output.")

        return {
            "reply": reply,
            "model": f"gemini/{model_name}" if model_name else "gemini/default",
            "runtime": "gemini",
        }
    finally:
        if workspace_id is not None:
            _clear_active_chat_process(workspace_id)


def _run_chat_cli(workspace_path: str, prompt_text: str, selected_model: str, agent_mode: str | None = None) -> dict:
    runtime, model_name, reasoning_effort = _resolve_runtime_model(selected_model)
    if runtime == "codex":
        return _run_codex_cli(workspace_path, prompt_text, model_name, reasoning_effort, agent_mode=agent_mode)
    if runtime == "cursor":
        return _run_cursor_cli(workspace_path, prompt_text, model_name, agent_mode=agent_mode)
    if runtime == "claude":
        return _run_claude_cli(workspace_path, prompt_text, model_name, reasoning_effort=reasoning_effort, agent_mode=agent_mode)
    return _run_gemini_cli(workspace_path, prompt_text, model_name, agent_mode=agent_mode)


def _stream_event_bytes(event_type: str, **payload) -> bytes:
    return (json.dumps({"type": event_type, **payload}) + "\n").encode("utf-8")


def _is_input_prompt(text: str) -> bool:
    """Return True if the text looks like the model is asking the user to choose or reply."""
    stripped = text.strip()
    if not stripped or len(stripped) > 800:
        return False
    # Explicit yes/no choice markers
    if re.search(r"\(\s*[Yy]\s*/\s*[Nn]\s*\)", stripped):
        return True
    if re.search(r"\[\s*[Yy]\s*/\s*[Nn]\s*\]", stripped):
        return True
    if re.search(r"\(\s*yes\s*/\s*no\s*\)", stripped, re.IGNORECASE):
        return True
    # Numbered option list (at least two options)
    if len(re.findall(r"^\s*[1-9]\.\s+\w", stripped, re.MULTILINE)) >= 2:
        return True
    # Explicit invitation phrases
    lower = stripped.lower()
    if any(lower.startswith(p) for p in (
        "please select", "please choose", "which option", "please enter",
        "please provide", "select one", "choose one",
    )):
        return True
    return False


def _pending_input_prompt(prompt: str | None, last_prompt: str = "") -> str:
    normalized = str(prompt or "").strip()
    if not normalized or normalized == last_prompt or not _is_input_prompt(normalized):
        return ""
    return normalized


def _wait_for_prompt_input(workspace_id: int | None, timeout: float = 300.0) -> str | None:
    if workspace_id is None:
        return None
    _set_chat_input_waiting(workspace_id, True)
    try:
        return _wait_for_chat_input(workspace_id, timeout=timeout)
    finally:
        _set_chat_input_waiting(workspace_id, False)


def _write_chat_input_to_process(process: subprocess.Popen | None, text: str | None) -> bool:
    if process is None or text is None or text == "" or not getattr(process, "stdin", None):
        return False
    try:
        process.stdin.write(text + "\n")
        process.stdin.flush()
        return True
    except OSError:
        return False


def _write_chat_input_to_fd(fd: int | None, text: str | None) -> bool:
    if fd is None or text is None or text == "":
        return False
    try:
        os.write(fd, (text + "\n").encode("utf-8"))
        return True
    except OSError:
        return False


def _wait_for_chat_input(workspace_id: int, timeout: float = 300.0) -> str | None:
    return _wait_for_chat_input_base(workspace_id, timeout=timeout)


def _append_activity_line(activity_log: list[str], message: str | None):
    if not message:
        return
    if activity_log and activity_log[-1] == message:
        return
    activity_log.append(message)


def _append_history_line(history_log: list[str] | None, message: str | None):
    if history_log is None or not message:
        return
    history_log.append(message)


def _append_terminal_chunk(terminal_log: list[str] | None, chunk: str | None):
    if terminal_log is None or not chunk:
        return
    terminal_log.append(chunk)


def _workspace_cache_path(workspace_path: str) -> str:
    return str(Path(workspace_path).expanduser().resolve())


def _cache_get(cache: dict, lock: threading.Lock, key, ttl_seconds: float):
    now = time.monotonic()
    with lock:
        entry = cache.get(key)
        if not entry:
            return None
        if now - float(entry.get("stored_at") or 0.0) > ttl_seconds:
            cache.pop(key, None)
            return None
        return copy.deepcopy(entry.get("value"))


def _cache_set(cache: dict, lock: threading.Lock, key, value) -> None:
    with lock:
        cache[key] = {
            "stored_at": time.monotonic(),
            "value": copy.deepcopy(value),
        }


def _invalidate_workspace_caches(workspace_path: str) -> None:
    normalized_path = _workspace_cache_path(workspace_path)
    with GIT_STATUS_CACHE_LOCK:
        GIT_STATUS_CACHE.pop(normalized_path, None)
    with RECENT_FILE_ENTRIES_CACHE_LOCK:
        stale_keys = [key for key in RECENT_FILE_ENTRIES_CACHE if key and key[0] == normalized_path]
        for key in stale_keys:
            RECENT_FILE_ENTRIES_CACHE.pop(key, None)


def _wait_for_process(process: subprocess.Popen, workspace_id: int | None, poll_interval: float = 5.0, max_wait: float = 1800.0) -> int:
    """Wait for a subprocess to finish, checking for a stop request every poll_interval seconds.

    If stop is requested the process tree is killed immediately and -1 is returned so the
    caller's subsequent _chat_stop_requested check can raise ChatStoppedError.
    """
    elapsed = 0.0
    while elapsed < max_wait:
        try:
            return process.wait(timeout=poll_interval)
        except subprocess.TimeoutExpired:
            elapsed += poll_interval
            if _chat_stop_requested(workspace_id):
                _kill_process_tree(process)
                return -1
    # Hard limit reached — kill and return non-zero so the caller surfaces an error.
    _kill_process_tree(process)
    return -1


def _register_orchestrated_chat_group(workspace_id: int, runtime: str = "multi") -> None:
    now = time.monotonic()
    with ORCHESTRATED_CHAT_LOCK:
        ORCHESTRATED_CHAT_PROCESSES[workspace_id] = {}
        ORCHESTRATED_CHAT_META[workspace_id] = {
            "started_at": now,
            "last_output_at": now,
            "input_waiting": False,
            "stop_requested": False,
            "runtime": runtime,
            "pid": 0,
            "turn_active": True,
        }


def _touch_orchestrated_chat_group(workspace_id: int | None) -> None:
    if workspace_id is None:
        return
    with ORCHESTRATED_CHAT_LOCK:
        meta = ORCHESTRATED_CHAT_META.get(workspace_id)
        if meta is not None:
            meta["last_output_at"] = time.monotonic()


def _register_orchestrated_process(workspace_id: int | None, process: subprocess.Popen, runtime: str) -> None:
    if workspace_id is None:
        return
    now = time.monotonic()
    with ORCHESTRATED_CHAT_LOCK:
        group = ORCHESTRATED_CHAT_PROCESSES.setdefault(workspace_id, {})
        group[process.pid] = process
        meta = ORCHESTRATED_CHAT_META.setdefault(workspace_id, {
            "started_at": now,
            "last_output_at": now,
            "input_waiting": False,
            "stop_requested": False,
            "runtime": runtime,
            "pid": process.pid,
            "turn_active": True,
        })
        meta["runtime"] = runtime or meta.get("runtime") or "multi"
        meta["pid"] = int(meta.get("pid") or process.pid)
        meta["last_output_at"] = now


def _unregister_orchestrated_process(workspace_id: int | None, pid: int | None) -> None:
    if workspace_id is None or pid is None:
        return
    with ORCHESTRATED_CHAT_LOCK:
        group = ORCHESTRATED_CHAT_PROCESSES.get(workspace_id)
        if group is not None:
            group.pop(pid, None)
        meta = ORCHESTRATED_CHAT_META.get(workspace_id)
        if meta is not None:
            meta["last_output_at"] = time.monotonic()
            if group:
                meta["pid"] = next(iter(group.keys()))
            else:
                meta["pid"] = 0


def _clear_orchestrated_chat_group(workspace_id: int | None) -> None:
    if workspace_id is None:
        return
    with ORCHESTRATED_CHAT_LOCK:
        ORCHESTRATED_CHAT_PROCESSES.pop(workspace_id, None)
        ORCHESTRATED_CHAT_META.pop(workspace_id, None)


def _kill_orchestrated_chat_group(workspace_id: int | None) -> bool:
    if workspace_id is None:
        return False
    killed = False
    with ORCHESTRATED_CHAT_LOCK:
        snapshot = list((ORCHESTRATED_CHAT_PROCESSES.get(workspace_id) or {}).values())
    for process in snapshot:
        if process.poll() is not None:
            continue
        killed = True
        _kill_process_tree(process)
    return killed


def _active_orchestrated_chat_status_payload(workspace_id: int) -> dict | None:
    with ORCHESTRATED_CHAT_LOCK:
        meta = dict(ORCHESTRATED_CHAT_META.get(workspace_id) or {})
        group = dict(ORCHESTRATED_CHAT_PROCESSES.get(workspace_id) or {})
    if not meta:
        return None

    alive_processes = [process for process in group.values() if process.poll() is None]
    now = time.monotonic()
    started_at = float(meta.get("started_at") or now)
    last_output_at = float(meta.get("last_output_at") or started_at)
    idle_seconds = max(0.0, now - last_output_at)
    input_waiting = bool(meta.get("input_waiting"))
    stalled = idle_seconds >= CHAT_STALL_WARNING_SECONDS and not input_waiting
    return {
        "active": bool(meta.get("turn_active")),
        "pid": int(meta.get("pid") or (alive_processes[0].pid if alive_processes else 0)),
        "runtime": meta.get("runtime") or "multi",
        "idle_seconds": round(idle_seconds, 1),
        "running_seconds": round(max(0.0, now - started_at), 1),
        "input_waiting": input_waiting,
        "stop_requested": bool(meta.get("stop_requested")),
        "stalled": stalled,
        "process_count": len(alive_processes),
    }


def _register_active_chat_process(workspace_id: int, process: subprocess.Popen, runtime: str) -> None:
    _register_active_chat_process_base(workspace_id, process, runtime)


def _clear_active_chat_process(workspace_id: int) -> None:
    _clear_active_chat_process_base(workspace_id)
    _clear_orchestrated_chat_group(workspace_id)


def _touch_active_chat_process(workspace_id: int | None) -> None:
    _touch_active_chat_process_base(workspace_id)
    _touch_orchestrated_chat_group(workspace_id)


def _set_chat_input_waiting(workspace_id: int | None, waiting: bool) -> None:
    _set_chat_input_waiting_base(workspace_id, waiting)
    if workspace_id is None:
        return
    with ORCHESTRATED_CHAT_LOCK:
        meta = ORCHESTRATED_CHAT_META.get(workspace_id)
        if meta is not None:
            meta["input_waiting"] = bool(waiting)
            if not waiting:
                meta["last_output_at"] = time.monotonic()


def _request_chat_stop(workspace_id: int) -> None:
    _request_chat_stop_base(workspace_id)
    with ORCHESTRATED_CHAT_LOCK:
        meta = ORCHESTRATED_CHAT_META.get(workspace_id)
        if meta is not None:
            meta["stop_requested"] = True


def _chat_stop_requested(workspace_id: int | None) -> bool:
    if _chat_stop_requested_base(workspace_id):
        return True
    if workspace_id is None:
        return False
    with ORCHESTRATED_CHAT_LOCK:
        meta = ORCHESTRATED_CHAT_META.get(workspace_id)
        return bool(meta and meta.get("stop_requested"))


def _active_chat_status_payload(workspace_id: int) -> dict:
    orchestrated = _active_orchestrated_chat_status_payload(workspace_id)
    if orchestrated is not None:
        return orchestrated
    return _active_chat_status_payload_base(workspace_id, CHAT_STALL_WARNING_SECONDS)


def _sweep_inactive_chat_processes() -> list[int]:
    cleared = set(_sweep_inactive_chat_processes_base())
    with ORCHESTRATED_CHAT_LOCK:
        stale = [
            workspace_id
            for workspace_id, meta in ORCHESTRATED_CHAT_META.items()
            if not meta.get("turn_active")
        ]
    for workspace_id in stale:
        _clear_orchestrated_chat_group(workspace_id)
        cleared.add(workspace_id)
    return list(cleared)


def _raw_cli_output_line(raw_line: str) -> str | None:
    line = raw_line.rstrip("\r\n")
    if not line.strip():
        return None
    return line


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text or "")


def _extract_terminal_lines(text: str, carry: str = "") -> tuple[list[str], str]:
    lines: list[str] = []
    current = carry
    for char in _strip_ansi(text):
        if char in "\r\n":
            if current.strip():
                lines.append(current.strip())
            current = ""
            continue
        current += char
    return lines, current


def _emit_status_event(
    activity_log: list[str] | None,
    history_log: list[str] | None,
    message: str | None = None,
    transcript: str | None = None,
    terminal: str | None = None,
):
    if message:
        _append_activity_line(activity_log if activity_log is not None else [], message)
    transcript_line = transcript or None
    if transcript_line:
        _append_history_line(history_log, transcript_line)
    terminal_line = terminal or None
    return _stream_event_bytes(
        "status",
        message=message or "",
        transcript=transcript_line or "",
        terminal=terminal_line or "",
    )


def _emit_orchestrated_stream_event(
    stream_handler: Callable[[dict], None] | None,
    event_type: str,
    **payload,
) -> None:
    if stream_handler is None:
        return
    try:
        stream_handler({"type": event_type, **payload})
    except Exception:
        return


def _emit_orchestrated_terminal_chunk(
    stream_handler: Callable[[dict], None] | None,
    text: str | None,
    carry: str = "",
) -> str:
    if not text:
        return carry
    _emit_orchestrated_stream_event(stream_handler, "terminal_chunk", text=text)
    lines, next_carry = _extract_terminal_lines(text, carry)
    for line in lines:
        _emit_orchestrated_stream_event(stream_handler, "history_line", text=line)
    return next_carry


def _compact_cli_payload(value, max_chars: int = 320) -> str:
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _codex_failure_detail(output: str, progress_lines: list[str]) -> str:
    if output:
        return output

    meaningful_lines = [line for line in progress_lines if line and not line.startswith("Starting Codex")]
    if meaningful_lines:
        return meaningful_lines[-1]

    return "Codex CLI failed."


def _codex_transcript_line(raw_line: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("WARNING:"):
        return None

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return re.sub(r"^\d{4}-\d\d-\d\dT[^\s]+\s+", "", line)

    event_type = payload.get("type") or ""
    if event_type == "thread.started":
        thread_id = payload.get("thread_id")
        return f"[thread.started] {thread_id}" if thread_id else "[thread.started]"
    if event_type == "turn.started":
        return "[turn.started]"
    if event_type == "error":
        return payload.get("message") or "[error]"
    if event_type in {"item.started", "item.completed"}:
        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        item_type = item.get("type") or item.get("kind") or payload.get("item_type") or payload.get("kind") or "item"
        prefix = "start" if event_type.endswith("started") else "done"
        command = item.get("command")
        if isinstance(command, list) and command:
            return f"[{prefix}] $ {' '.join(str(part) for part in command)}"
        if isinstance(command, str) and command:
            return f"[{prefix}] $ {command}"
        path = item.get("path")
        if path:
            return f"[{prefix}] {item_type} {path}"
        query = item.get("query")
        if query:
            return f"[{prefix}] search {query}"
        title = item.get("title") or item.get("name")
        if title:
            return f"[{prefix}] {title}"
        return f"[{event_type}] {item_type}"
    if isinstance(payload.get("message"), str) and payload.get("message").strip():
        return payload["message"].strip()
    return _compact_cli_payload(payload)


def _codex_item_message(payload: dict, completed: bool) -> str | None:
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    item_type = item.get("type") or item.get("kind") or payload.get("item_type") or payload.get("kind")

    label = None
    if "command" in item:
        command = item.get("command")
        if isinstance(command, list):
            label = f"Running shell command: {' '.join(str(part) for part in command)}"
        elif isinstance(command, str):
            label = f"Running shell command: {command}"
    elif item.get("path"):
        action = "Updating file" if completed else "Working with file"
        label = f"{action}: {item['path']}"
    elif item.get("title"):
        label = item["title"]
    elif item.get("name"):
        label = item["name"]
    elif item.get("query"):
        label = f"Searching: {item['query']}"
    elif item_type:
        known = {
            "command": "Running shell command",
            "shell_command": "Running shell command",
            "apply_patch": "Applying patch",
            "read_file": "Reading file",
            "write_file": "Updating file",
            "search": "Searching codebase",
            "plan": "Updating plan",
        }
        label = known.get(item_type)

    if not label:
        return None
    if completed:
        return label.replace("Running", "Completed").replace("Working with", "Completed work on")
    return label


def _codex_progress_message(raw_line: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("WARNING:"):
        return None

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        compact = re.sub(r"^\d{4}-\d\d-\d\dT[^\s]+\s+", "", line)
        compact = compact.replace("ERROR codex_api::endpoint::responses_websocket:", "Connection issue:")
        return compact

    event_type = payload.get("type") or ""
    if event_type == "thread.started":
        return "Session started."
    if event_type == "turn.started":
        return "Turn started."
    if event_type == "error":
        return payload.get("message") or "Codex reported an error."
    if event_type == "item.started":
        return _codex_item_message(payload, completed=False)
    if event_type == "item.completed":
        return _codex_item_message(payload, completed=True)
    if event_type.endswith(".started"):
        return f"{event_type.removesuffix('.started').replace('.', ' ').title()}."
    if event_type.endswith(".completed"):
        return f"{event_type.removesuffix('.completed').replace('.', ' ').title()} complete."
    if payload.get("message"):
        return payload["message"]

    return event_type.replace(".", " ").title() if event_type else None


def _stream_codex_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    reasoning_effort: str | None = None,
    agent_mode: str | None = None,
    session_id: str | None = None,
    activity_log: list[str] | None = None,
    history_log: list[str] | None = None,
    workspace_id: int | None = None,
    terminal_log: list[str] | None = None,
):
    codex_path = shutil.which("codex")
    if not codex_path:
        raise HTTPException(status_code=400, detail="Codex CLI is not installed.")
    capabilities = _codex_exec_capabilities(codex_path)
    bypass_sandbox = False

    while True:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as output_file:
            output_path = output_file.name

        try:
            if sys.platform == "win32" or not hasattr(os, "openpty"):
                command = _build_codex_command(
                    codex_path,
                    workspace_path,
                    output_path,
                    prompt_text,
                    model_name,
                    reasoning_effort,
                    agent_mode=agent_mode,
                    session_id=session_id,
                    json_output=True,
                    bypass_sandbox=bypass_sandbox,
                )
                process = subprocess.Popen(
                    command,
                    cwd=workspace_path,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                )
                if workspace_id is not None:
                    _register_active_chat_process(workspace_id, process, "codex")

                start_message = f"Starting Codex with {_resolved_runtime_model_id('codex', model_name, reasoning_effort)}..."
                yield _emit_status_event(activity_log, history_log, message=start_message)

                active_session_id = session_id
                progress_lines = [start_message]
                assert process.stdout is not None
                for line in process.stdout:
                    raw_line = _raw_cli_output_line(line)
                    if raw_line:
                        _touch_active_chat_process(workspace_id)
                        _append_terminal_chunk(terminal_log, line)
                        yield _stream_event_bytes("terminal_chunk", text=line)
                    active_session_id = _codex_thread_id(line) or active_session_id
                    message = _codex_progress_message(line)
                    if message:
                        progress_lines.append(message)
                        _touch_active_chat_process(workspace_id)
                        yield _emit_status_event(
                            activity_log,
                            history_log,
                            message=message,
                            transcript=raw_line,
                        )
                        if workspace_id is not None and _is_input_prompt(message):
                            _set_chat_input_waiting(workspace_id, True)
                            yield _stream_event_bytes("input_required", prompt=message)
                            user_input = _wait_for_chat_input(workspace_id, timeout=300.0)
                            _set_chat_input_waiting(workspace_id, False)
                            if user_input is not None and process.stdin:
                                try:
                                    process.stdin.write(user_input + "\n")
                                    process.stdin.flush()
                                except OSError:
                                    pass

                returncode = _wait_for_process(process, workspace_id)
                output = Path(output_path).read_text(encoding="utf-8").strip()
                if _chat_stop_requested(workspace_id):
                    raise ChatStoppedError("Chat stopped.")
                if returncode != 0:
                    detail = _codex_failure_detail(output, progress_lines)
                    if (
                        not bypass_sandbox
                        and capabilities.get("supports_dangerous_bypass")
                        and _is_codex_sandbox_bootstrap_failure(detail)
                    ):
                        bypass_sandbox = True
                        yield _emit_status_event(
                            activity_log,
                            history_log,
                            message=_codex_retry_without_sandbox_message(),
                        )
                        continue
                    raise HTTPException(status_code=400, detail=detail)

                reply = output.strip()
                if not reply:
                    raise HTTPException(status_code=500, detail="Codex CLI returned no output.")

                return {
                    "reply": reply,
                    "model": _codex_model_label(model_name, reasoning_effort),
                    "runtime": "codex",
                    "session_id": active_session_id if capabilities["supports_resume"] else "",
                }

            command = _build_codex_command(
                codex_path,
                workspace_path,
                output_path,
                prompt_text,
                model_name,
                reasoning_effort,
                agent_mode=agent_mode,
                session_id=session_id,
                terminal_output=True,
                bypass_sandbox=bypass_sandbox,
            )
            master_fd, slave_fd = os.openpty()
            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                env={
                    **os.environ,
                    "TERM": os.environ.get("TERM") or "xterm-256color",
                },
            )
            os.close(slave_fd)
            if workspace_id is not None:
                _register_active_chat_process(workspace_id, process, "codex")

            start_message = f"Starting Codex with {_resolved_runtime_model_id('codex', model_name, reasoning_effort)}..."
            yield _stream_event_bytes("status", message=start_message)
            _append_activity_line(activity_log if activity_log is not None else [], start_message)

            active_session_id = session_id if capabilities["supports_resume"] else ""
            progress_lines = [start_message]
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            line_carry = ""
            last_prompt = ""
            try:
                while True:
                    chunk = None
                    if workspace_id is not None:
                        with PENDING_CHAT_INPUT_LOCK:
                            pending_input = PENDING_CHAT_INPUT.get(workspace_id)
                        if pending_input is not None:
                            try:
                                user_input = pending_input.get_nowait()
                            except queue.Empty:
                                user_input = None
                            if user_input:
                                try:
                                    _set_chat_input_waiting(workspace_id, False)
                                    os.write(master_fd, (user_input + "\n").encode("utf-8"))
                                except OSError:
                                    pass
                                with PENDING_CHAT_INPUT_LOCK:
                                    PENDING_CHAT_INPUT.pop(workspace_id, None)

                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                    if ready:
                        try:
                            chunk = os.read(master_fd, 4096)
                        except OSError:
                            chunk = b""
                        if chunk:
                            text = decoder.decode(chunk)
                            if text:
                                _touch_active_chat_process(workspace_id)
                                _append_terminal_chunk(terminal_log, text)
                                yield _stream_event_bytes("terminal_chunk", text=text)
                                lines, line_carry = _extract_terminal_lines(text, line_carry)
                                for line in lines:
                                    progress_lines.append(line)
                                    _append_activity_line(activity_log if activity_log is not None else [], line)
                                    _append_history_line(history_log, line)
                                    yield _stream_event_bytes("status", message=line)
                                    if workspace_id is not None and line != last_prompt and _is_input_prompt(line):
                                        last_prompt = line
                                        with PENDING_CHAT_INPUT_LOCK:
                                            PENDING_CHAT_INPUT.setdefault(workspace_id, queue.Queue())
                                        _set_chat_input_waiting(workspace_id, True)
                                        yield _stream_event_bytes("input_required", prompt=line)
                        elif process.poll() is not None:
                            break

                    if process.poll() is not None and not ready:
                        break
            finally:
                try:
                    remainder = decoder.decode(b"", final=True)
                except Exception:
                    remainder = ""
                if remainder:
                    _append_terminal_chunk(terminal_log, remainder)
                    yield _stream_event_bytes("terminal_chunk", text=remainder)
                    lines, line_carry = _extract_terminal_lines(remainder, line_carry)
                    for line in lines:
                        progress_lines.append(line)
                        _append_activity_line(activity_log if activity_log is not None else [], line)
                        _append_history_line(history_log, line)
                        yield _stream_event_bytes("status", message=line)
                if line_carry.strip():
                    final_line = line_carry.strip()
                    progress_lines.append(final_line)
                    _append_activity_line(activity_log if activity_log is not None else [], final_line)
                    _append_history_line(history_log, final_line)
                    yield _stream_event_bytes("status", message=final_line)
                os.close(master_fd)
                if workspace_id is not None:
                    with PENDING_CHAT_INPUT_LOCK:
                        PENDING_CHAT_INPUT.pop(workspace_id, None)

                returncode = _wait_for_process(process, workspace_id)
            output = Path(output_path).read_text(encoding="utf-8").strip()
            if _chat_stop_requested(workspace_id):
                raise ChatStoppedError("Chat stopped.")
            if returncode != 0:
                detail = _codex_failure_detail(output, progress_lines)
                if (
                    not bypass_sandbox
                    and capabilities.get("supports_dangerous_bypass")
                    and _is_codex_sandbox_bootstrap_failure(detail)
                ):
                    bypass_sandbox = True
                    retry_message = _codex_retry_without_sandbox_message()
                    _append_activity_line(activity_log if activity_log is not None else [], retry_message)
                    _append_history_line(history_log, retry_message)
                    yield _stream_event_bytes("status", message=retry_message)
                    continue
                raise HTTPException(status_code=400, detail=detail)

            reply = output.strip()
            if not reply:
                raise HTTPException(status_code=500, detail="Codex CLI returned no output.")

            return {
                "reply": reply,
                "model": _codex_model_label(model_name, reasoning_effort),
                "runtime": "codex",
                "session_id": active_session_id if capabilities["supports_resume"] else "",
            }
        finally:
            Path(output_path).unlink(missing_ok=True)
            if workspace_id is not None:
                _clear_active_chat_process(workspace_id)


def _stream_claude_cli(
    workspace_path: str,
    prompt_text: str,
    model_name: str | None,
    session_id: str | None = None,
    agent_mode: str | None = None,
    activity_log: list[str] | None = None,
    history_log: list[str] | None = None,
    workspace_id: int | None = None,
    reasoning_effort: str | None = None,
    terminal_log: list[str] | None = None,
):
    claude_path = shutil.which("claude")
    if not claude_path:
        raise HTTPException(status_code=400, detail="Claude CLI is not installed.")

    # Use --output-format json (not stream-json) so Claude shows its native visual UI
    # (spinners, tool call indicators, colors) through the PTY. The final JSON blob
    # at process exit is parsed for reply/session_id.
    command = _build_claude_command(
        claude_path,
        prompt_text,
        model_name,
        session_id=session_id,
        stream_json=False,
        reasoning_effort=reasoning_effort,
        agent_mode=agent_mode,
    )

    use_pty = sys.platform != "win32" and hasattr(os, "openpty")

    if use_pty:
        master_fd, slave_fd = os.openpty()
        process = subprocess.Popen(
            command,
            cwd=workspace_path,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        os.close(slave_fd)
    else:
        process = subprocess.Popen(
            command,
            cwd=workspace_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
        )

    if workspace_id is not None:
        _register_active_chat_process(workspace_id, process, "claude")

    active_session_id = session_id
    reply = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    line_carry = ""
    last_prompt = ""
    # Accumulate ANSI-stripped text so we can find the final JSON blob at the end
    text_accumulator: list[str] = []
    # Skip the initial plain-text prompt echo that Claude CLI prints before its
    # live UI starts.  The live UI always begins with ANSI escape sequences;
    # the prompt echo is plain text.  We buffer and discard until we see ESC+[.
    _skip: dict = {"buf": b"", "done": False}
    _ANSI_MARKER = b"\x1b["
    # Prompts can be very large (system instructions + workspace context).
    # Use a 2 MB cap so the prompt never bleeds into the live terminal view.
    _SKIP_LIMIT = 2 * 1024 * 1024

    def _drain_pty_chunk(raw_bytes: bytes):
        """Skip prompt echo, then stream raw terminal bytes as terminal_chunk."""
        nonlocal line_carry, last_prompt
        if use_pty and not _skip["done"]:
            _skip["buf"] += raw_bytes
            buf = _skip["buf"]
            if _ANSI_MARKER in buf or len(buf) >= _SKIP_LIMIT:
                _skip["done"] = True
                idx = buf.find(_ANSI_MARKER)
                raw_bytes = buf[idx:] if idx >= 0 else buf
                _skip["buf"] = b""
            else:
                return  # still buffering the initial prompt echo
        text = decoder.decode(raw_bytes)
        if not text:
            return
        _append_terminal_chunk(terminal_log, text)
        yield _stream_event_bytes("terminal_chunk", text=text)
        stripped_text = _strip_ansi(text)
        text_accumulator.append(stripped_text)
        lines, line_carry = _extract_terminal_lines(stripped_text, line_carry)
        for line in lines:
            normalized_prompt = _pending_input_prompt(line, last_prompt)
            if workspace_id is None or not normalized_prompt:
                continue
            last_prompt = normalized_prompt
            yield _stream_event_bytes("input_required", prompt=normalized_prompt)
            user_input = _wait_for_prompt_input(workspace_id)
            if use_pty:
                _write_chat_input_to_fd(master_fd, user_input)
            else:
                _write_chat_input_to_process(process, user_input)

    try:
        if use_pty:
            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        chunk = b""
                    if chunk:
                        _touch_active_chat_process(workspace_id)
                        yield from _drain_pty_chunk(chunk)
                    elif process.poll() is not None:
                        break
                elif process.poll() is not None:
                    # Drain any remaining bytes before exiting
                    try:
                        while True:
                            r2, _, _ = select.select([master_fd], [], [], 0.05)
                            if not r2:
                                break
                            tail = os.read(master_fd, 4096)
                            if not tail:
                                break
                            yield from _drain_pty_chunk(tail)
                    except OSError:
                        pass
                    break
        else:
            assert process.stdout is not None
            for raw_bytes in process.stdout:
                _touch_active_chat_process(workspace_id)
                yield from _drain_pty_chunk(raw_bytes)

        returncode = _wait_for_process(process, workspace_id)
        if _chat_stop_requested(workspace_id):
            raise ChatStoppedError("Chat stopped.")

        # Parse the final JSON blob for reply and session_id
        final_payload = _extract_claude_terminal_result_payload("".join(text_accumulator))
        if final_payload is not None:
            active_session_id = _claude_session_id(final_payload) or active_session_id
            if final_payload.get("is_error"):
                raise HTTPException(
                    status_code=400,
                    detail=final_payload.get("result") or "Claude CLI failed.",
                )
            reply = _claude_message_text(final_payload) or reply

        if returncode != 0:
            detail = reply or "Claude CLI failed."
            raise HTTPException(status_code=400, detail=detail)
        if not reply:
            raise HTTPException(status_code=500, detail="Claude CLI returned no output.")

        return {
            "reply": reply,
            "model": _resolved_runtime_model_id("claude", model_name, reasoning_effort),
            "runtime": "claude",
            "session_id": active_session_id,
        }
    finally:
        if terminal_log is not None and terminal_log:
            sanitized_terminal_output = _sanitize_claude_terminal_output("".join(terminal_log))
            terminal_log[:] = [sanitized_terminal_output] if sanitized_terminal_output else []
        if use_pty:
            try:
                os.close(master_fd)
            except OSError:
                pass
        if workspace_id is not None:
            _clear_active_chat_process(workspace_id)


def _make_unique_workspace_name(db, desired_name: str, exclude_id: int | None = None) -> str:
    base_name = _normalize_workspace_name(desired_name)
    candidate = base_name
    suffix = 2

    while True:
        query = db.query(Workspace).filter_by(name=candidate)
        if exclude_id is not None:
            query = query.filter(Workspace.id != exclude_id)
        if query.first() is None:
            return candidate
        candidate = f"{base_name} {suffix}"
        suffix += 1


def _get_or_create_workspace(db, path: str) -> Workspace:
    normalized_path = _normalize_workspace_path(path)
    workspace = db.query(Workspace).filter_by(path=normalized_path).first()
    if workspace:
        _ensure_workspace_tab(db, workspace)
        return workspace

    desired_name = Path(normalized_path).name or normalized_path
    workspace = Workspace(
        name=_make_unique_workspace_name(db, desired_name),
        path=normalized_path,
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    _ensure_workspace_tab(db, workspace)
    return workspace


def _collect_stream_text(stream) -> str:
    full_response = ""
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        full_response += content
    return full_response


def _get_workspace_or_404(db, workspace_id: int) -> Workspace:
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _next_workspace_tab_title(db, workspace: Workspace) -> str:
    return DEFAULT_TAB_TITLE


def _create_workspace_tab(
    db,
    workspace: Workspace,
    *,
    title: str | None = None,
    sort_order: int | None = None,
    archived_at: datetime | None = None,
) -> WorkspaceTab:
    if sort_order is None:
        last_sort = (
            db.query(WorkspaceTab.sort_order)
            .filter(WorkspaceTab.workspace_id == workspace.id, WorkspaceTab.archived_at.is_(None))
            .order_by(WorkspaceTab.sort_order.desc(), WorkspaceTab.id.desc())
            .first()
        )
        sort_order = (int(last_sort[0] or 0) + 1) if last_sort else 0

    now = _utcnow()
    tab = WorkspaceTab(
        workspace_id=workspace.id,
        title=(title or "").strip() or _next_workspace_tab_title(db, workspace),
        sort_order=sort_order,
        archived_at=archived_at,
        last_used_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(tab)
    db.commit()
    db.refresh(tab)
    db.refresh(workspace)
    return tab


def _ensure_workspace_tab(db, workspace: Workspace) -> WorkspaceTab:
    tab = (
        db.query(WorkspaceTab)
        .filter(WorkspaceTab.workspace_id == workspace.id)
        .order_by(WorkspaceTab.archived_at.is_not(None), WorkspaceTab.sort_order.asc(), WorkspaceTab.id.asc())
        .first()
    )
    if tab is not None:
        return tab
    return _create_workspace_tab(db, workspace, title=DEFAULT_TAB_TITLE, sort_order=0)


def _get_workspace_tab_or_404(
    db,
    workspace: Workspace,
    tab_id: int | None = None,
    *,
    allow_archived: bool = False,
    create_missing: bool = True,
) -> WorkspaceTab:
    if tab_id is not None:
        query = db.query(WorkspaceTab).filter(
            WorkspaceTab.workspace_id == workspace.id,
            WorkspaceTab.id == tab_id,
        )
        if not allow_archived:
            query = query.filter(WorkspaceTab.archived_at.is_(None))
        tab = query.first()
        if tab is None:
            raise HTTPException(status_code=404, detail="Tab not found.")
        return tab

    query = db.query(WorkspaceTab).filter(
        WorkspaceTab.workspace_id == workspace.id,
        WorkspaceTab.archived_at.is_(None),
    ).order_by(WorkspaceTab.sort_order.asc(), WorkspaceTab.id.asc())
    tab = query.first()
    if tab is not None:
        return tab
    if not create_missing:
        raise HTTPException(status_code=404, detail="No tabs available for this workspace.")
    return _ensure_workspace_tab(db, workspace)


def _run_git(workspace_path: str, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=workspace_path,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Git is not installed in this environment.") from exc

    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "Git command failed.").strip()
        raise HTTPException(status_code=400, detail=detail)

    return result


def _file_stat_signature(path: Path) -> dict | None:
    try:
        stat_result = path.stat()
    except OSError:
        return None
    return {
        "size": stat_result.st_size,
        "mtime_ns": getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000)),
    }


def _git_change_entries(git_state: dict) -> dict[str, dict]:
    entries = {}
    for entry in [*(git_state.get("changed") or []), *(git_state.get("staged") or []), *(git_state.get("untracked") or [])]:
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        combined = entries.setdefault(path, {"path": path, "index_status": ".", "worktree_status": "."})
        if entry.get("index_status"):
            combined["index_status"] = entry["index_status"]
        if entry.get("worktree_status"):
            combined["worktree_status"] = entry["worktree_status"]
    return entries


def _capture_git_change_state(workspace_path: str) -> dict | None:
    git_state = _parse_git_status(workspace_path)
    if not git_state.get("is_repo"):
        return None

    workspace_root = Path(workspace_path)
    entries = {}
    for path, entry in _git_change_entries(git_state).items():
        entries[path] = {
            "index_status": entry.get("index_status") or ".",
            "worktree_status": entry.get("worktree_status") or ".",
            "stat": _file_stat_signature(workspace_root / path),
        }
    return {"paths": entries}


def _workspace_file_paths(workspace_path: str) -> set[str]:
    workspace_root = Path(workspace_path)
    paths = set()
    for root, dirs, files in os.walk(workspace_root, topdown=True):
        dirs[:] = sorted(directory for directory in dirs if directory not in SNAPSHOT_EXCLUDED_DIRS)
        root_path = Path(root)
        for filename in sorted(files):
            file_path = root_path / filename
            if not file_path.is_file():
                continue
            paths.add(str(file_path.relative_to(workspace_root)))
    return paths


def _capture_turn_file_metadata(workspace_path: str, existing_paths: list[str]) -> dict[str, dict]:
    workspace_root = Path(workspace_path)
    metadata: dict[str, dict] = {}
    for relative_path in existing_paths:
        signature = _file_stat_signature(workspace_root / relative_path)
        if not signature:
            continue
        metadata[relative_path] = {"size": int(signature.get("size") or 0)}
    return metadata


def _read_file_preview(path: Path, max_bytes: int) -> tuple[dict | None, int]:
    try:
        stat_result = path.stat()
    except OSError:
        return None, 0

    read_limit = max(0, min(int(max_bytes), int(stat_result.st_size)))
    try:
        with path.open("rb") as handle:
            preview = handle.read(read_limit)
    except OSError:
        return None, 0

    truncated = int(stat_result.st_size) > read_limit
    entry: dict[str, object] = {
        "kind": "binary" if b"\x00" in preview else "text",
        "size": int(stat_result.st_size),
        "truncated": truncated,
    }
    if entry["kind"] == "text":
        entry["text"] = preview.decode("utf-8", errors="replace")
    return entry, len(preview)


def _read_text_preview(path: Path, max_bytes: int) -> tuple[str | None, bool, int]:
    preview, consumed_bytes = _read_file_preview(path, max_bytes)
    if not preview or preview.get("kind") != "text":
        return None, False, 0
    return str(preview.get("text") or ""), bool(preview.get("truncated")), consumed_bytes


def _capture_turn_text_snapshot(workspace_path: str, existing_paths: list[str]) -> dict[str, dict]:
    snapshot: dict[str, dict] = {}
    remaining_bytes = MAX_TURN_SNAPSHOT_TOTAL_BYTES
    workspace_root = Path(workspace_path)

    for relative_path in existing_paths:
        if len(snapshot) >= MAX_TURN_SNAPSHOT_FILES or remaining_bytes <= 0:
            break
        if _is_generated_artifact_path(relative_path):
            continue
        preview_limit = min(MAX_TURN_SNAPSHOT_FILE_BYTES, remaining_bytes)
        preview, consumed_bytes = _read_file_preview(workspace_root / relative_path, preview_limit)
        if not preview:
            continue
        snapshot[relative_path] = dict(preview)
        remaining_bytes -= consumed_bytes

    return snapshot


def _capture_turn_context(workspace: Workspace) -> dict:
    workspace_path = workspace.path
    generated_staging_dir = _workspace_generated_staging_dir(workspace, create=True)
    existing_paths = sorted(_workspace_file_paths(workspace_path))
    git_state = _capture_git_change_state(workspace_path)
    git_head = None
    if _git_repo_root(workspace_path):
        result = _run_git(workspace_path, ["rev-parse", "HEAD"], check=False)
        if result.returncode == 0:
            git_head = result.stdout.strip() or None
    return {
        "started_at_ns": time.time_ns(),
        "existing_paths": existing_paths,
        "file_metadata": _capture_turn_file_metadata(workspace_path, existing_paths),
        "text_snapshot": _capture_turn_text_snapshot(workspace_path, existing_paths) if git_state is None else {},
        "generated_dir": str(_workspace_generated_dir(workspace, create=True)),
        "generated_staging_dir": str(generated_staging_dir),
        "git": git_state,
        "git_head": git_head,
    }


def _prune_empty_workspace_dirs(path: Path, workspace_root: Path):
    current = path
    while current != workspace_root and workspace_root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _relocate_new_workspace_files(workspace: Workspace, turn_context: dict | None):
    turn_context = turn_context or {}
    started_at_ns = int(turn_context.get("started_at_ns") or 0)
    if started_at_ns <= 0:
        return

    staging_root = Path(turn_context.get("generated_staging_dir") or _workspace_generated_staging_dir(workspace, create=True))
    generated_root = Path(turn_context.get("generated_dir") or _workspace_generated_dir(workspace, create=True))
    moved_paths = []

    if not staging_root.exists():
        turn_context["moved_generated_paths"] = moved_paths
        return

    staged_files: list[tuple[str, Path]] = []
    for root, dirs, files in os.walk(staging_root, topdown=True):
        dirs[:] = sorted(dirs)
        root_path = Path(root)
        for filename in sorted(files):
            source_path = root_path / filename
            signature = _file_stat_signature(source_path)
            if not signature or int(signature["mtime_ns"]) < started_at_ns:
                continue
            relative_path = str(source_path.relative_to(staging_root))
            staged_files.append((relative_path, source_path))

    for relative_path, source_path in staged_files:
        destination_path = generated_root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists():
            if destination_path.is_dir():
                shutil.rmtree(destination_path)
            else:
                destination_path.unlink()

        shutil.move(str(source_path), str(destination_path))
        moved_paths.append(relative_path)
        _prune_empty_workspace_dirs(source_path.parent, staging_root)

    turn_context["moved_generated_paths"] = moved_paths


def _generated_files_turn_changes(turn_context: dict | None) -> list[dict]:
    turn_context = turn_context or {}
    generated_dir = Path(str(turn_context.get("generated_dir") or ""))
    started_at_ns = int(turn_context.get("started_at_ns") or 0)
    if started_at_ns <= 0 or not generated_dir.exists():
        return []

    items = []
    for root, dirs, files in os.walk(generated_dir, topdown=True):
        dirs[:] = sorted(dirs)
        root_path = Path(root)
        for filename in sorted(files):
            file_path = root_path / filename
            signature = _file_stat_signature(file_path)
            if not signature or int(signature["mtime_ns"]) < started_at_ns:
                continue
            relative_path = str(file_path.relative_to(generated_dir))
            items.append((relative_path, int(signature["mtime_ns"])))

    items.sort(key=lambda item: (item[1], item[0]), reverse=True)
    changes = []
    for relative_path, _mtime_ns in items[:MAX_TURN_DIFF_FILES]:
        absolute_path = generated_dir / relative_path
        changes.append({
            "path": f"generated/{relative_path}",
            "status": "generated",
            "diff": "",
            "note": f"Stored in BetterCode generated files: {absolute_path}",
            "absolute_path": str(absolute_path),
        })

    omitted_count = max(0, len(items) - len(changes))
    if omitted_count > 0:
        changes.append({
            "path": f"{omitted_count} more generated file(s)",
            "status": "generated",
            "diff": "",
            "note": "Additional generated files were omitted from this response preview.",
        })

    return changes


def _git_change_status(entry: dict | None) -> str:
    if not entry:
        return "modified"
    index_status = str(entry.get("index_status") or ".")
    worktree_status = str(entry.get("worktree_status") or ".")
    combined = f"{index_status}{worktree_status}"
    if "?" in combined or "A" in combined:
        return "added"
    if "D" in combined:
        return "deleted"
    if "R" in combined:
        return "renamed"
    return "modified"


def _current_git_diff(workspace_path: str, path: str, before_head: str | None = None) -> str:
    if _git_repo_root(workspace_path) is None:
        return ""

    diff_chunks = []
    seen = set()

    if before_head:
        result = _run_git(workspace_path, ["diff", "--no-ext-diff", "--no-color", before_head, "HEAD", "--", path], check=False)
        content = (result.stdout or "").strip()
        if result.returncode == 0 and content and content not in seen:
            diff_chunks.append(content)
            seen.add(content)

    for args in (
        ["diff", "--no-ext-diff", "--no-color", "--", path],
        ["diff", "--cached", "--no-ext-diff", "--no-color", "--", path],
    ):
        result = _run_git(workspace_path, args, check=False)
        content = (result.stdout or "").strip()
        if result.returncode == 0 and content and content not in seen:
            diff_chunks.append(content)
            seen.add(content)

    return "\n\n".join(diff_chunks)


def _synthesized_new_file_diff(workspace_path: str, path: str) -> str:
    absolute_path = Path(workspace_path) / path
    preview, _consumed = _read_file_preview(absolute_path, MAX_TURN_DIFF_FALLBACK_BYTES)
    if not preview:
        return ""
    if preview.get("kind") == "binary":
        return _synthesized_binary_diff(
            path,
            None,
            int(preview.get("size") or 0),
            fromfile="/dev/null",
            tofile=f"b/{path}",
        )
    return _synthesized_text_diff(
        path,
        "",
        str(preview.get("text") or ""),
        fromfile="/dev/null",
        tofile=f"b/{path}",
        after_truncated=bool(preview.get("truncated")),
    )


def _synthesized_text_diff(
    path: str,
    before_text: str,
    after_text: str,
    *,
    fromfile: str,
    tofile: str,
    before_truncated: bool = False,
    after_truncated: bool = False,
) -> str:
    diff_lines = list(difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    ))
    if not diff_lines:
        return ""
    if before_truncated or after_truncated:
        diff_lines.append("... diff preview truncated ...")
    if len(diff_lines) > MAX_TURN_DIFF_LINES:
        diff_lines = diff_lines[:MAX_TURN_DIFF_LINES]
        diff_lines.append("... diff preview truncated ...")
    return "\n".join(diff_lines)


def _synthesized_binary_diff(
    path: str,
    before_size: int | None,
    after_size: int | None,
    *,
    fromfile: str,
    tofile: str,
) -> str:
    diff_lines = [
        f"--- {fromfile}",
        f"+++ {tofile}",
        "@@ binary @@",
    ]
    if before_size is not None:
        diff_lines.append(f"-Binary file ({before_size} bytes)")
    if after_size is not None:
        diff_lines.append(f"+Binary file ({after_size} bytes)")
    return "\n".join(diff_lines)


def _synthesized_file_summary_diff(
    path: str,
    before_size: int | None,
    after_size: int | None,
    *,
    fromfile: str,
    tofile: str,
    file_kind: str = "file",
) -> str:
    diff_lines = [
        f"--- {fromfile}",
        f"+++ {tofile}",
        "@@ summary @@",
    ]
    if before_size is not None:
        diff_lines.append(f"-Previous {file_kind} size: {before_size} bytes")
    else:
        diff_lines.append(f"-Previous {file_kind} snapshot unavailable")
    if after_size is not None:
        diff_lines.append(f"+Current {file_kind} size: {after_size} bytes")
    else:
        diff_lines.append(f"+Current {file_kind} missing")
    return "\n".join(diff_lines)


def _is_generated_artifact_path(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts if part]
    if not parts:
        return False
    if any(part in GENERATED_ARTIFACT_DIRS for part in parts[:-1]):
        return True
    filename = parts[-1]
    if filename in GENERATED_ARTIFACT_FILES:
        return True
    return any(filename.endswith(suffix) for suffix in GENERATED_ARTIFACT_SUFFIXES)


def _prioritize_turn_change_paths(changed_paths: list[str]) -> tuple[list[str], int, int]:
    meaningful_paths = [path for path in changed_paths if not _is_generated_artifact_path(path)]
    generated_paths = [path for path in changed_paths if _is_generated_artifact_path(path)]
    prioritized = meaningful_paths or generated_paths
    selected_paths = prioritized[:MAX_TURN_DIFF_FILES]

    if meaningful_paths:
        omitted_meaningful = max(0, len(meaningful_paths) - len(selected_paths))
        omitted_generated = len(generated_paths)
    else:
        omitted_meaningful = 0
        omitted_generated = max(0, len(generated_paths) - len(selected_paths))

    return selected_paths, omitted_meaningful, omitted_generated


def _workspace_recent_files(workspace_path: str, started_at_ns: int) -> list[str]:
    workspace_root = Path(workspace_path)
    candidates = []
    for root, dirs, files in os.walk(workspace_root, topdown=True):
        dirs[:] = sorted(directory for directory in dirs if directory not in SNAPSHOT_EXCLUDED_DIRS)
        root_path = Path(root)
        for filename in sorted(files):
            file_path = root_path / filename
            signature = _file_stat_signature(file_path)
            if not signature or int(signature["mtime_ns"]) < started_at_ns:
                continue
            candidates.append((str(file_path.relative_to(workspace_root)), int(signature["mtime_ns"])))

    candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
    return [path for path, _ in candidates]


def _review_source_label(sources: set[str]) -> str:
    normalized = set(sources or set())
    if normalized == {"staged"}:
        return "staged"
    if normalized == {"changed"}:
        return "modified"
    if normalized == {"untracked"}:
        return "untracked"
    if "staged" in normalized and "changed" in normalized:
        return "staged + modified"
    if "staged" in normalized and "untracked" in normalized:
        return "staged + new"
    if "changed" in normalized and "untracked" in normalized:
        return "modified + new"
    return "changed"


def _review_changed_files(git_state: dict, limit: int = DEFAULT_REVIEW_FILE_LIMIT) -> list[dict]:
    sources_by_path: dict[str, set[str]] = {}
    for source_name, entries in (
        ("staged", git_state.get("staged") or []),
        ("changed", git_state.get("changed") or []),
        ("untracked", git_state.get("untracked") or []),
    ):
        for entry in entries:
            path = str(entry.get("path") or "").strip()
            if not path or _is_generated_artifact_path(path):
                continue
            sources_by_path.setdefault(path, set()).add(source_name)

    items = []
    for path, entry in sorted(_git_change_entries(git_state).items()):
        if _is_generated_artifact_path(path):
            continue
        items.append({
            "path": path,
            "status": _git_change_status(entry),
            "git_status": f"{entry.get('index_status') or '.'}{entry.get('worktree_status') or '.'}",
            "source_label": _review_source_label(sources_by_path.get(path, set())),
        })
    return items[:limit]


def _workspace_recent_file_entries(
    workspace_path: str,
    limit: int = DEFAULT_REVIEW_FILE_LIMIT,
    exclude_paths: set[str] | None = None,
) -> list[dict]:
    started_at = time.monotonic()
    cache_key = (
        _workspace_cache_path(workspace_path),
        int(limit),
        tuple(sorted(exclude_paths or set())),
    )
    cached = _cache_get(
        RECENT_FILE_ENTRIES_CACHE,
        RECENT_FILE_ENTRIES_CACHE_LOCK,
        cache_key,
        RECENT_FILE_ENTRIES_CACHE_TTL_SECONDS,
    )
    if cached is not None:
        log_event(
            "review_recent_files_scanned",
            workspace_path=workspace_path,
            cache_hit=True,
            limit=limit,
            duration_ms=duration_ms(started_at),
        )
        return cached

    workspace_root = Path(workspace_path)
    excluded = exclude_paths or set()
    candidates = []
    for root, dirs, files in os.walk(workspace_root, topdown=True):
        dirs[:] = sorted(directory for directory in dirs if directory not in SNAPSHOT_EXCLUDED_DIRS)
        root_path = Path(root)
        for filename in sorted(files):
            file_path = root_path / filename
            signature = _file_stat_signature(file_path)
            if not signature:
                continue
            relative_path = str(file_path.relative_to(workspace_root))
            if relative_path in excluded or _is_generated_artifact_path(relative_path):
                continue
            candidates.append((relative_path, int(signature["mtime_ns"])))

    candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
    entries = [
        {
            "path": path,
            "modified_at": datetime.fromtimestamp(mtime_ns / 1_000_000_000).isoformat(),
        }
        for path, mtime_ns in candidates[:limit]
    ]
    _cache_set(RECENT_FILE_ENTRIES_CACHE, RECENT_FILE_ENTRIES_CACHE_LOCK, cache_key, entries)
    log_event(
        "review_recent_files_scanned",
        workspace_path=workspace_path,
        cache_hit=False,
        candidate_count=len(candidates),
        result_count=len(entries),
        limit=limit,
        duration_ms=duration_ms(started_at),
    )
    return entries


def _workspace_turn_changes(workspace_path: str, turn_context: dict | None) -> list[dict]:
    turn_context = turn_context or {}
    git_before = ((turn_context.get("git") or {}).get("paths") or {})
    before_head = turn_context.get("git_head")
    existing_paths = set(turn_context.get("existing_paths") or [])
    file_metadata = turn_context.get("file_metadata") or {}
    text_snapshot = turn_context.get("text_snapshot") or {}
    git_after_state = _capture_git_change_state(workspace_path)
    git_after = (git_after_state or {}).get("paths") or {}

    # Detect if HEAD changed (CLI committed changes)
    after_head = None
    committed_paths: list[str] = []
    if git_after_state is not None and before_head:
        result = _run_git(workspace_path, ["rev-parse", "HEAD"], check=False)
        if result.returncode == 0:
            after_head = result.stdout.strip() or None
        if after_head and after_head != before_head:
            result = _run_git(workspace_path, ["diff", "--no-ext-diff", "--name-only", before_head, after_head], check=False)
            if result.returncode == 0:
                committed_paths = [p.strip() for p in (result.stdout or "").splitlines() if p.strip()]

    if git_after_state is not None:
        dirty_changed = [
            path
            for path in sorted(set(git_before) | set(git_after))
            if git_before.get(path) != git_after.get(path)
        ]
        changed_paths = sorted(set(dirty_changed) | set(committed_paths))
        current_paths = set(git_after)
    else:
        current_paths = _workspace_file_paths(workspace_path)
        deleted_paths = sorted(existing_paths - current_paths)
        changed_paths = sorted(set(_workspace_recent_files(workspace_path, int(turn_context.get("started_at_ns") or 0))) | set(deleted_paths))

    effective_before_head = before_head if (after_head and after_head != before_head) else None

    selected_paths, omitted_meaningful, omitted_generated = _prioritize_turn_change_paths(changed_paths)
    changes = []
    for path in selected_paths:
        absolute_path = Path(workspace_path) / path
        after_entry = git_after.get(path)
        before_entry = git_before.get(path)
        snapshot_entry = text_snapshot.get(path) or {}
        before_size = int((file_metadata.get(path) or {}).get("size") or 0) or None
        if git_after_state is not None:
            status = _git_change_status(after_entry or before_entry)
        else:
            if path not in current_paths:
                status = "deleted"
            elif path not in existing_paths:
                status = "added"
            else:
                status = "modified"
        diff_text = _current_git_diff(workspace_path, path, effective_before_head) if git_after_state is not None else ""
        if not diff_text and path not in existing_paths and absolute_path.is_file():
            diff_text = _synthesized_new_file_diff(workspace_path, path)
        if not diff_text and git_after_state is not None and path in existing_paths and absolute_path.is_file():
            current_preview, _consumed = _read_file_preview(absolute_path, MAX_TURN_DIFF_FALLBACK_BYTES)
            if current_preview and (
                snapshot_entry.get("kind") == "binary"
                or current_preview.get("kind") == "binary"
            ):
                diff_text = _synthesized_binary_diff(
                    path,
                    before_size,
                    int(current_preview.get("size") or 0),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            elif current_preview:
                diff_text = _synthesized_file_summary_diff(
                    path,
                    before_size,
                    int(current_preview.get("size") or 0),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                    file_kind="text file",
                )
        if not diff_text and git_after_state is None and path in existing_paths:
            before_text = str(snapshot_entry.get("text") or "")
            before_truncated = bool(snapshot_entry.get("truncated"))
            if path not in current_paths:
                if snapshot_entry.get("kind") == "text":
                    diff_text = _synthesized_text_diff(
                        path,
                        before_text,
                        "",
                        fromfile=f"a/{path}",
                        tofile="/dev/null",
                        before_truncated=before_truncated,
                    )
                else:
                    diff_text = _synthesized_binary_diff(
                        path,
                        before_size,
                        None,
                        fromfile=f"a/{path}",
                        tofile="/dev/null",
                    )
            elif absolute_path.is_file():
                current_preview, _consumed = _read_file_preview(absolute_path, MAX_TURN_DIFF_FALLBACK_BYTES)
                if snapshot_entry.get("kind") == "text" and current_preview and current_preview.get("kind") == "text":
                    diff_text = _synthesized_text_diff(
                        path,
                        before_text,
                        str(current_preview.get("text") or ""),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                        before_truncated=before_truncated,
                        after_truncated=bool(current_preview.get("truncated")),
                    )
                elif current_preview and (
                    snapshot_entry.get("kind") == "binary"
                    or current_preview.get("kind") == "binary"
                ):
                    diff_text = _synthesized_binary_diff(
                        path,
                        before_size,
                        int(current_preview.get("size") or 0),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                    )
                elif current_preview:
                    diff_text = _synthesized_file_summary_diff(
                        path,
                        before_size,
                        int(current_preview.get("size") or 0),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                        file_kind="text file",
                    )
        change = {
            "path": path,
            "status": status,
            "diff": diff_text,
        }
        if not diff_text:
            change["note"] = "Diff preview unavailable for this file."
        changes.append(change)

    if omitted_meaningful > 0:
        changes.append({
            "path": f"{omitted_meaningful} more file(s)",
            "status": "truncated",
            "diff": "",
            "note": "Additional changed files were omitted from this response preview.",
        })
    if omitted_generated > 0:
        changes.append({
            "path": f"{omitted_generated} generated artifact(s)",
            "status": "generated",
            "diff": "",
            "note": "Generated build output was omitted from this response preview.",
        })

    return changes + _generated_files_turn_changes(turn_context)


def _git_repo_root(workspace_path: str) -> str | None:
    result = _run_git(workspace_path, ["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _parse_git_status(workspace_path: str) -> dict:
    started_at = time.monotonic()
    cache_key = _workspace_cache_path(workspace_path)
    cached = _cache_get(
        GIT_STATUS_CACHE,
        GIT_STATUS_CACHE_LOCK,
        cache_key,
        GIT_STATUS_CACHE_TTL_SECONDS,
    )
    if cached is not None:
        log_event(
            "git_status_scanned",
            workspace_path=workspace_path,
            cache_hit=True,
            is_repo=bool(cached.get("is_repo")),
            changed_count=len(cached.get("changed") or []),
            duration_ms=duration_ms(started_at),
        )
        return cached

    repo_root = _git_repo_root(workspace_path)
    if repo_root is None:
        payload = {
            "is_repo": False,
            "branch": None,
            "ahead": 0,
            "behind": 0,
            "changed": [],
            "staged": [],
            "untracked": [],
        }
        _cache_set(GIT_STATUS_CACHE, GIT_STATUS_CACHE_LOCK, cache_key, payload)
        log_event(
            "git_status_scanned",
            workspace_path=workspace_path,
            cache_hit=False,
            is_repo=False,
            changed_count=0,
            duration_ms=duration_ms(started_at),
        )
        return payload

    result = _run_git(workspace_path, ["status", "--porcelain=2", "--branch"])
    branch = None
    ahead = 0
    behind = 0
    changed = []
    staged = []
    untracked = []

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# branch.head "):
            branch_name = line.removeprefix("# branch.head ").strip()
            branch = None if branch_name == "(detached)" else branch_name
            continue

        if line.startswith("# branch.ab "):
            parts = line.split()
            for part in parts:
                if part.startswith("+"):
                    ahead = int(part[1:])
                elif part.startswith("-"):
                    behind = int(part[1:])
            continue

        if line.startswith("1 "):
            parts = line.split(" ", 8)
            if len(parts) < 9:
                continue
            xy = parts[1]
            path = _decode_git_path(parts[8])
            entry = {
                "path": path,
                "index_status": xy[0],
                "worktree_status": xy[1],
            }
            if xy[0] != ".":
                staged.append(entry)
            if xy[1] != ".":
                changed.append(entry)
            continue

        if line.startswith("2 "):
            parts = line.split(" ", 9)
            if len(parts) < 10:
                continue
            xy = parts[1]
            path = _decode_git_path(parts[9].split("\t", 1)[0])
            entry = {
                "path": path,
                "index_status": xy[0],
                "worktree_status": xy[1],
            }
            if xy[0] != ".":
                staged.append(entry)
            if xy[1] != ".":
                changed.append(entry)
            continue

        if line.startswith("? "):
            path = _decode_git_path(line[2:])
            entry = {"path": path}
            changed.append({"path": path, "index_status": "?", "worktree_status": "?"})
            untracked.append(entry)

    payload = {
        "is_repo": True,
        "root": repo_root,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "changed": changed,
        "staged": staged,
        "untracked": untracked,
    }
    _cache_set(GIT_STATUS_CACHE, GIT_STATUS_CACHE_LOCK, cache_key, payload)
    log_event(
        "git_status_scanned",
        workspace_path=workspace_path,
        cache_hit=False,
        is_repo=True,
        branch=branch,
        changed_count=len(changed),
        staged_count=len(staged),
        untracked_count=len(untracked),
        duration_ms=duration_ms(started_at),
    )
    return payload


def _build_change_summary(change_log: list[dict]) -> str:
    changed_paths = [
        str(change.get("path") or "").strip()
        for change in change_log or []
        if change.get("status") != "truncated" and str(change.get("path") or "").strip()
    ]
    if not changed_paths:
        return ""
    unique_paths = []
    for path in changed_paths:
        if path not in unique_paths:
            unique_paths.append(path)
    if len(unique_paths) == 1:
        return f"Updated {unique_paths[0]}."
    if len(unique_paths) == 2:
        return f"Updated {unique_paths[0]} and {unique_paths[1]}."
    return f"Updated {unique_paths[0]}, {unique_paths[1]}, and {len(unique_paths) - 2} more files."


def _classify_turn_failure(exc: Exception) -> dict:
    message = str(exc).strip() or "Request failed."
    lowered = message.lower()
    category = "generic"
    retry_hint = "Retry the turn."
    if "timeout" in lowered or "timed out" in lowered:
        category = "timeout"
        retry_hint = "Retry the turn or pick a faster model."
    elif "not installed" in lowered or "not configured" in lowered or "requires" in lowered:
        category = "configuration"
        retry_hint = "Check the runtime or selector configuration, then retry."
    elif "login" in lowered or "auth" in lowered or "api key" in lowered:
        category = "authentication"
        retry_hint = "Refresh the runtime login or API key, then retry."
    elif "stopped" in lowered or "cancelled" in lowered:
        category = "cancelled"
        retry_hint = "Retry the turn when ready."
    elif _is_usage_limit_error(lowered):
        category = "usage_limit"
        retry_hint = "Check your subscription or try a different model."
    return {
        "category": category,
        "message": message,
        "retry_hint": retry_hint,
    }


_USAGE_LIMIT_RE = re.compile(
    r"usage.?limit|rate.?limit|quota|too.many.requests|billing|subscription|"
    r"resource.?exhausted|insufficient.?quota|out.of.credit|credits?\s+|"
    r"claude\.ai/billing|max.?requests|tokens?.?per.*(minute|hour|day)|"
    r"requests?.?per.*(minute|hour|day)|exceeded.*limit|limit.*exceeded|"
    r"upgrade.*plan|plan.*upgrade|429",
    re.IGNORECASE,
)


def _is_usage_limit_error(message: str) -> bool:
    """Return True if the error message indicates a quota/rate-limit/billing failure."""
    return bool(_USAGE_LIMIT_RE.search(message or ""))


def _pick_cli_fallback(
    excluded_models: set[str],
    selector_request_text: str = "",
) -> dict | None:
    """
    Pick the next best available model, excluding already-tried ones.
    Uses heuristic selection — fast, no local model call needed during error recovery.
    Returns a selection dict or None if no candidates remain.
    """
    try:
        registry = _model_registry()
        candidates = [m for m in registry if m.get("id") not in excluded_models]
        if not candidates:
            return None
        selection = select_best_model_heuristic(selector_request_text, candidates)
        selection["selected_model_label"] = next(
            (m["label"] for m in candidates if m["id"] == selection["selected_model"]),
            _model_label(selection["selected_model"]),
        )
        return selection
    except Exception:
        return None


def _refresh_incremental_turn_memory(
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    request_text: str,
    reply_text: str,
) -> None:
    transcript = "\n".join(
        line for line in (
            f"user: {request_text.strip()}" if (request_text or "").strip() else "",
            f"assistant: {reply_text.strip()}" if (reply_text or "").strip() else "",
        )
        if line
    ).strip()
    if not transcript:
        return
    if len(transcript) > MEMORY_INCREMENTAL_TRANSCRIPT_CHARS:
        transcript = "… [earlier turn trimmed]\n" + transcript[-MEMORY_INCREMENTAL_TRANSCRIPT_CHARS:]
    try:
        _review_chat_memory(db, workspace, tab, mode="auto", transcript=transcript)
    except Exception:
        return


def _manage_workspace_context_with_fallback(db, workspace: Workspace, tab: WorkspaceTab) -> bool:
    try:
        return bool(manage_workspace_context(db, workspace, tab=tab))
    except TypeError:
        return bool(manage_workspace_context(db, workspace))


def _store_turn_postprocess_async(
    message_id: int,
    workspace_id: int,
    tab_id: int,
    request_text: str,
    reply_text: str,
    change_log: list[dict],
):
    try:
        recommendations = []
        if get_enable_follow_up_suggestions():
            recommendations_started_at = time.monotonic()
            recommendations = suggest_follow_up_recommendations(request_text, reply_text, change_log)
            log_event(
                "follow_up_recommendations_completed",
                message_id=message_id,
                count=len(recommendations),
                duration_ms=duration_ms(recommendations_started_at),
            )

        with SessionLocal() as db:
            message = db.query(Message).filter_by(id=message_id).first()
            workspace = db.query(Workspace).filter_by(id=workspace_id).first()
            tab = db.query(WorkspaceTab).filter_by(id=tab_id, workspace_id=workspace_id).first()
            if message is None or workspace is None or tab is None:
                return
            message.recommendations = json.dumps(recommendations)
            _manage_workspace_context_with_fallback(db, workspace, tab)
            _refresh_incremental_turn_memory(db, workspace, tab, request_text, reply_text)
            db.commit()
    except Exception:
        return


def _start_turn_postprocess(
    message_id: int,
    workspace_id: int,
    tab_id: int,
    request_text: str,
    reply_text: str,
    change_log: list[dict],
) -> None:
    threading.Thread(
        target=_store_turn_postprocess_async,
        args=(message_id, workspace_id, tab_id, request_text, reply_text, change_log),
        daemon=True,
    ).start()


def _generate_assistant_reply(
    prompt_text: str,
    request_text: str,
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    selected_model: str,
    agent_mode: str | None = None,
    selected_source: str = "manual",
    task_analysis: dict | None = None,
    selection_reasoning: str | None = None,
    selected_model_label: str | None = None,
    activity_log: list[str] | None = None,
    history_log: list[str] | None = None,
    turn_context: dict | None = None,
) -> dict:
    human_language = get_human_language()
    if selected_model.startswith("local/"):
        local_model_id = selected_model.split("/", 1)[1]
        try:
            local_prompt = _build_local_turn_prompt(db, workspace, tab, request_text)
            cli_result = run_local_model_response(local_prompt, model_id=local_model_id, human_language=human_language)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        cli_result = _run_workspace_chat_cli(workspace, tab, prompt_text, selected_model, agent_mode=agent_mode)
    reply = cli_result["reply"]
    _invalidate_workspace_caches(workspace.path)
    _invalidate_generated_file_count_cache(workspace.id)
    _relocate_new_workspace_files(workspace, turn_context)
    change_log = _workspace_turn_changes(workspace.path, turn_context)
    routing_meta = _build_routing_meta(
        selected_model,
        selected_source,
        task_analysis,
        cli_result,
        selection_reasoning=selection_reasoning,
        selected_model_label=selected_model_label,
        change_summary=_build_change_summary(change_log),
    )

    assistant_message = _persist_workspace_message(
        db,
        workspace,
        tab,
        "assistant",
        reply,
        activity_log=json.dumps(activity_log or []),
        history_log=json.dumps(history_log or []),
        change_log=json.dumps(change_log),
        recommendations=json.dumps([]),
        routing_meta=json.dumps(routing_meta),
    )
    _record_workspace_runtime_state(db, workspace, tab, cli_result)
    _record_router_telemetry(
        db,
        workspace,
        cli_result["model"],
        cli_result["runtime"],
        selected_source,
        task_analysis or analyze_routing_task(request_text, ""),
        success=True,
        changed_files=len(change_log),
    )
    _start_turn_postprocess(assistant_message.id, workspace.id, tab.id, request_text, reply, change_log)

    return {
        "message": _serialize_message(assistant_message),
        "model": cli_result["model"],
        "runtime": cli_result["runtime"],
    }


def _build_preprocessed_turn_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    tab: WorkspaceTab | None = None,
) -> dict:
    return _build_preprocessed_turn_context_base(db, workspace, request_text, attachments, _parse_git_status, tab=tab)


def _build_selector_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    tab: WorkspaceTab | None = None,
) -> str:
    return _build_selector_context_base(db, workspace, request_text, attachments, _parse_git_status, tab=tab)


def _model_label(model_id: str) -> str:
    normalized_model_id = str(model_id or "").strip()
    if normalized_model_id == "smart":
        return "Auto Model Select"
    for entry in _model_options_cached_only():
        if entry["id"] == normalized_model_id:
            return entry["label"]
    for entry in _model_registry():
        if entry["id"] == normalized_model_id:
            return entry["label"]
    for entry in _model_options():
        if entry["id"] == normalized_model_id:
            return entry["label"]
    return normalized_model_id


def _build_routing_meta(
    selected_model: str,
    selected_source: str,
    task_analysis: dict | None,
    cli_result: dict,
    selection_reasoning: str | None = None,
    selected_model_label: str | None = None,
    change_summary: str | None = None,
    task_breakdown: dict | None = None,
) -> dict:
    selector_map = {
        "manual": "Direct",
        "local": "Local Router",
        "fallback": "Heuristic Router",
        "auto": "Auto Model Select",
        "local_direct": "Local Fast Path",
    }
    source = selected_source or "manual"
    mode = "auto" if source != "manual" else "manual"
    model_id = selected_model if task_breakdown and task_breakdown.get("task_count") else (cli_result.get("model") or selected_model)
    model_label = selected_model_label or _model_label(selected_model) or _model_label(model_id)
    task_type = (task_analysis or {}).get("task_type") or "general"

    if mode == "manual":
        reason = selection_reasoning or "Model selected directly."
    else:
        reason = selection_reasoning or "Auto Model Select routed this turn."

    return {
        "mode": mode,
        "selector": source,
        "selector_label": selector_map.get(source, source.replace("_", " ").title()),
        "model_id": model_id,
        "model_label": model_label,
        "runtime": cli_result.get("runtime") or "",
        "task_type": task_type,
        "reason": reason,
        "change_summary": change_summary or "",
        "task_breakdown": task_breakdown or {},
    }


def _router_telemetry_summary(db, workspace: Workspace | None, limit: int = 240) -> dict:
    query = db.query(RouterTelemetry).order_by(RouterTelemetry.created_at.desc()).limit(limit)
    entries = list(reversed(query.all()))
    if workspace is not None:
        workspace_entries = [entry for entry in entries if entry.workspace_id == workspace.id]
    else:
        workspace_entries = []

    def build_summary(records: list[RouterTelemetry]) -> dict:
        by_model = {}
        for entry in records:
            model_stats = by_model.setdefault(entry.model_id, {
                "attempts": 0,
                "successes": 0,
                "changed_files_total": 0,
                "task_types": {},
            })
            model_stats["attempts"] += 1
            model_stats["successes"] += 1 if entry.success else 0
            model_stats["changed_files_total"] += max(0, int(entry.changed_files or 0))

            task_stats = model_stats["task_types"].setdefault(entry.task_type or "general", {
                "attempts": 0,
                "successes": 0,
            })
            task_stats["attempts"] += 1
            task_stats["successes"] += 1 if entry.success else 0

        return {"by_model": by_model, "sample_size": len(records)}

    return {
        "workspace": build_summary(workspace_entries),
        "global": build_summary(entries),
    }


def _record_router_telemetry(
    db,
    workspace: Workspace,
    model_id: str,
    runtime: str,
    source: str,
    task_analysis: dict,
    success: bool,
    changed_files: int = 0,
):
    db.add(RouterTelemetry(
        workspace_id=workspace.id,
        model_id=model_id,
        runtime=runtime,
        source=source,
        task_type=task_analysis.get("task_type") or "general",
        complexity=int(task_analysis.get("complexity") or 0),
        estimated_tokens=int(task_analysis.get("estimated_tokens") or 0),
        success=1 if success else 0,
        changed_files=max(0, int(changed_files)),
    ))
    db.commit()


def _build_recent_messages_block(db, workspace: Workspace, limit: int = 6) -> str:
    messages = (
        db.query(Message)
        .filter_by(workspace_id=workspace.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    if not messages:
        return ""

    messages = list(reversed(messages))
    lines = [f"{message.role.title()}: {message.content}" for message in messages]
    return "Recent conversation:\n" + "\n\n".join(lines)


def _workspace_session_id(tab: WorkspaceTab | None, runtime: str) -> str:
    if tab is None:
        return ""
    if runtime == "codex":
        return tab.codex_session_id or ""
    if runtime == "cursor":
        return getattr(tab, "cursor_session_id", "") or ""
    if runtime == "claude":
        return tab.claude_session_id or ""
    return ""


def _set_workspace_session_id(tab: WorkspaceTab, runtime: str, session_id: str):
    if runtime == "codex":
        tab.codex_session_id = session_id
    elif runtime == "cursor":
        tab.cursor_session_id = session_id
    elif runtime == "claude":
        tab.claude_session_id = session_id


def _workspace_has_session(tab: WorkspaceTab | None) -> bool:
    if tab is None:
        return False
    return bool(
        (tab.codex_session_id or "").strip()
        or (getattr(tab, "cursor_session_id", "") or "").strip()
        or (tab.claude_session_id or "").strip()
    )


def _clear_workspace_sessions(tab: WorkspaceTab):
    tab.codex_session_id = ""
    tab.cursor_session_id = ""
    tab.claude_session_id = ""


def _warm_session_cutoff() -> datetime:
    return _utcnow() - timedelta(minutes=WARM_SESSION_IDLE_MINUTES)


def _rebalance_workspace_session_pool(db, busy_tab_id: int | None = None):
    session_filter = or_(
        WorkspaceTab.codex_session_id != "",
        WorkspaceTab.cursor_session_id != "",
        WorkspaceTab.claude_session_id != "",
    )
    candidates = (
        db.query(WorkspaceTab)
        .filter(session_filter, WorkspaceTab.archived_at.is_(None))
        .order_by(WorkspaceTab.last_used_at.desc(), WorkspaceTab.id.desc())
        .all()
    )
    warm_cutoff = _warm_session_cutoff()

    warm_ids = set()
    for tab in candidates:
        if busy_tab_id is not None and tab.id == busy_tab_id:
            tab.session_state = "busy"
            warm_ids.add(tab.id)
            break

    for tab in candidates:
        if tab.id in warm_ids:
            continue
        tab_last_used_at = _coerce_utc(tab.last_used_at)
        if not tab_last_used_at or tab_last_used_at < warm_cutoff:
            continue
        if len(warm_ids) >= MAX_WARM_WORKSPACES:
            break
        warm_ids.add(tab.id)

    active_ids = [tab.id for tab in candidates]
    if active_ids:
        db.query(WorkspaceTab).filter(WorkspaceTab.id.in_(active_ids)).update(
            {WorkspaceTab.session_state: "cold"},
            synchronize_session=False,
        )
    if warm_ids:
        db.query(WorkspaceTab).filter(WorkspaceTab.id.in_(list(warm_ids))).update(
            {WorkspaceTab.session_state: "warm"},
            synchronize_session=False,
        )
    if busy_tab_id is not None:
        db.query(WorkspaceTab).filter(WorkspaceTab.id == busy_tab_id).update(
            {WorkspaceTab.session_state: "busy"},
            synchronize_session=False,
        )


def _mark_workspace_session_busy(db, workspace: Workspace, tab: WorkspaceTab):
    now = _utcnow()
    workspace.last_used_at = now
    tab.last_used_at = now
    tab.updated_at = now
    _rebalance_workspace_session_pool(db, busy_tab_id=tab.id)
    db.commit()
    db.refresh(tab)
    db.refresh(workspace)


def _touch_workspace_session(db, workspace: Workspace, tab: WorkspaceTab):
    now = _utcnow()
    workspace.last_used_at = now
    tab.last_used_at = now
    tab.updated_at = now
    if not _workspace_has_session(tab):
        tab.session_state = "cold"
        db.commit()
        db.refresh(tab)
        db.refresh(workspace)
        return

    workspace.last_used_at = now
    _rebalance_workspace_session_pool(db)
    db.commit()
    db.refresh(tab)
    db.refresh(workspace)


def _record_workspace_runtime_state(db, workspace: Workspace, tab: WorkspaceTab, cli_result: dict):
    runtime = cli_result.get("runtime") or ""
    now = _utcnow()
    tab.last_runtime = runtime
    tab.last_model = cli_result.get("model") or ""
    tab.last_used_at = now
    tab.updated_at = now
    workspace.last_used_at = now
    if runtime and cli_result.get("session_id"):
        _set_workspace_session_id(tab, runtime, cli_result["session_id"])
    _rebalance_workspace_session_pool(db)
    db.commit()
    db.refresh(tab)
    db.refresh(workspace)


def _reconcile_workspace_session_pool():
    with SessionLocal() as db:
        _rebalance_workspace_session_pool(db)
        db.commit()


def activate_workspace_session_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        _touch_workspace_session(db, workspace, tab)
        return {"workspace": _serialize_workspace(workspace), "tab": _serialize_tab(tab)}


def reset_workspace_session_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        _clear_workspace_sessions(tab)
        clear_memory_entries(db, workspace, tab, "short")
        tab.session_state = "cold"
        tab.last_runtime = ""
        tab.last_model = ""
        tab.last_used_at = _utcnow()
        tab.updated_at = tab.last_used_at
        workspace.last_used_at = tab.last_used_at
        _rebalance_workspace_session_pool(db)
        db.commit()
        db.refresh(tab)
        db.refresh(workspace)
        return {"workspace": _serialize_workspace(workspace), "tab": _serialize_tab(tab)}


def _run_workspace_chat_cli(
    workspace: Workspace,
    tab: WorkspaceTab,
    prompt_text: str,
    selected_model: str,
    agent_mode: str | None = None,
) -> dict:
    started_at = time.monotonic()
    runtime, model_name, reasoning_effort = _resolve_runtime_model(selected_model)
    log_event(
        "chat_cli_started",
        workspace_id=workspace.id,
        runtime=runtime,
        selected_model=selected_model,
    )
    if runtime == "codex":
        result = _run_codex_cli(
            workspace.path,
            prompt_text,
            model_name,
            reasoning_effort,
            agent_mode=agent_mode,
            session_id=(_workspace_session_id(tab, "codex") or None),
        )
    elif runtime == "cursor":
        result = _run_cursor_cli(
            workspace.path,
            prompt_text,
            model_name,
            session_id=(_workspace_session_id(tab, "cursor") or None),
            agent_mode=agent_mode,
        )
    elif runtime == "claude":
        result = _run_claude_cli(
            workspace.path,
            prompt_text,
            model_name,
            session_id=(_workspace_session_id(tab, "claude") or None),
            reasoning_effort=reasoning_effort,
            agent_mode=agent_mode,
        )
    else:
        result = _run_gemini_cli(workspace.path, prompt_text, model_name, agent_mode=agent_mode)
    log_event(
        "chat_cli_completed",
        workspace_id=workspace.id,
        runtime=runtime,
        selected_model=selected_model,
        resolved_model=result.get("model") or "",
        duration_ms=duration_ms(started_at),
    )
    return result


def _resolve_better_select_model(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    agent_mode: str | None = None,
    tab: WorkspaceTab | None = None,
    selector_context: str | None = None,
    task_analysis: dict | None = None,
    routing_history: dict | None = None,
    available_models: list[dict] | None = None,
    selector_runtime_status: dict | None = None,
) -> dict:
    selector_context = selector_context if selector_context is not None else _build_selector_context(db, workspace, request_text, attachments, tab=tab)
    available_models = _filter_models_for_agent_mode(available_models or _model_registry(), agent_mode)
    selection = select_best_model(
        request_text,
        available_models,
        selector_context,
        routing_history=routing_history or _router_telemetry_summary(db, workspace),
        selector_runtime_status=selector_runtime_status,
    )
    selection["selected_model_label"] = next(
        (option["label"] for option in available_models if option["id"] == selection["selected_model"]),
        selection["selected_model"],
    )
    selection["task_analysis"] = task_analysis or analyze_routing_task(request_text, selector_context)
    return selection


def _selector_preprocess_context(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    agent_mode: str | None = None,
    tab: WorkspaceTab | None = None,
) -> tuple[str, dict, dict, list[dict], dict | None]:
    selector_context = _build_selector_context(db, workspace, request_text, attachments, tab=tab)
    task_analysis = analyze_routing_task(request_text, selector_context)
    routing_history = _router_telemetry_summary(db, workspace)
    available_models = _filter_models_for_agent_mode(_model_registry(), agent_mode)
    selector_runtime_status = None
    if get_local_preprocess_mode() != "off":
        try:
            selector_runtime_status = require_selector_runtime(
                start_if_needed=True,
                warm_model=False,
                startup_timeout=5.0,
            )
        except RuntimeError:
            selector_runtime_status = None
    return selector_context, task_analysis, routing_history, available_models, selector_runtime_status


def _selector_preprocess_turn(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    agent_mode: str | None = None,
    tab: WorkspaceTab | None = None,
) -> tuple[str, dict, dict, list[dict], dict]:
    started_at = time.monotonic()
    selector_context, task_analysis, routing_history, available_models, selector_runtime_status = _selector_preprocess_context(
        db,
        workspace,
        request_text,
        attachments,
        agent_mode=agent_mode,
        tab=tab,
    )
    local_selection = maybe_select_local_execution(
        request_text,
        selector_context,
        task_analysis=task_analysis,
        selector_runtime_status=selector_runtime_status,
    )
    if local_selection is not None:
        log_event(
            "selector_local_execution_selected",
            workspace_id=workspace.id,
            selected_model=local_selection.get("selected_model") or "",
            confidence=int(local_selection.get("confidence") or 0),
            duration_ms=duration_ms(started_at),
        )
        return selector_context, task_analysis, routing_history, available_models, local_selection
    selection = _resolve_better_select_model(
        db,
        workspace,
        request_text,
        attachments,
        agent_mode=agent_mode,
        tab=tab,
        selector_context=selector_context,
        task_analysis=task_analysis,
        routing_history=routing_history,
        available_models=available_models,
        selector_runtime_status=selector_runtime_status,
    )
    log_event(
        "selector_preprocess_profile",
        workspace_id=workspace.id,
        request_length=len(request_text or ""),
        attachment_count=len(attachments or []),
        selected_model=selection.get("selected_model") or "",
        selector_source=selection.get("source") or "",
        selector_confidence=int(selection.get("confidence") or 0),
        duration_ms=duration_ms(started_at),
    )
    return selector_context, task_analysis, routing_history, available_models, selection


def _trim_task_text(text: str, max_chars: int = TASK_RESULT_SNIPPET_CHARS) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _task_breakdown_primary_model(tasks: list[dict]) -> tuple[str, str]:
    if not tasks:
        return "", "Task plan"

    scores: dict[str, int] = {}
    labels: dict[str, str] = {}
    for task in tasks:
        model_id = str(task.get("model_id") or "").strip()
        if not model_id:
            continue
        weight = 3 if str(task.get("stage") or "").strip() == "edit" else 1
        scores[model_id] = scores.get(model_id, 0) + weight
        labels[model_id] = str(task.get("model_label") or _model_label(model_id) or model_id).strip()

    if not scores:
        return "", "Task plan"
    primary_model_id = max(scores.items(), key=lambda item: (item[1], item[0]))[0]
    return primary_model_id, labels.get(primary_model_id) or _model_label(primary_model_id) or primary_model_id


def _serialize_task_breakdown(tasks: list[dict]) -> dict:
    normalized_tasks = []
    model_ids = []
    for task in tasks:
        model_id = str(task.get("model_id") or "").strip()
        if model_id:
            model_ids.append(model_id)
        normalized_tasks.append({
            "id": str(task.get("id") or "").strip(),
            "title": str(task.get("title") or task.get("id") or "").strip(),
            "status": str(task.get("status") or "planned").strip(),
            "detail": str(task.get("detail") or "").strip(),
            "depends_on": [str(value) for value in (task.get("depends_on") or []) if str(value or "").strip()],
            "execution": str(task.get("execution") or "sync").strip(),
            "stage": str(task.get("stage") or "").strip(),
            "model_id": model_id,
            "model_label": str(task.get("model_label") or _model_label(model_id) or model_id).strip(),
            "selection_reason": str(task.get("selection_reason") or "").strip(),
            "track_key": str(task.get("track_key") or "").strip(),
            "track_label": str(task.get("track_label") or "").strip(),
            "track_kind": str(task.get("track_kind") or "").strip(),
            "parallel_group": str(task.get("parallel_group") or "").strip(),
        })

    unique_models = list(dict.fromkeys(model_ids))
    primary_model_id, primary_model_label = _task_breakdown_primary_model(normalized_tasks)
    return {
        "task_count": len(normalized_tasks),
        "model_count": len(unique_models),
        "parallel_task_count": len([task for task in normalized_tasks if task.get("execution") == "async"]),
        "primary_model_id": primary_model_id,
        "primary_model_label": primary_model_label,
        "label": "Multi-model plan" if len(unique_models) > 1 else (primary_model_label or "Task plan"),
        "tasks": normalized_tasks,
    }


def _task_breakdown_summary(task_breakdown: dict | None) -> str:
    if not task_breakdown:
        return ""
    task_count = int(task_breakdown.get("task_count") or 0)
    model_count = int(task_breakdown.get("model_count") or 0)
    parallel_count = int(task_breakdown.get("parallel_task_count") or 0)
    if not task_count:
        return ""
    parts = [f"{task_count} task{'s' if task_count != 1 else ''}"]
    if model_count:
        parts.append(f"{model_count} model{'s' if model_count != 1 else ''}")
    if parallel_count:
        parts.append(f"{parallel_count} parallel")
    return ", ".join(parts)


def _build_task_execution_prompt(
    base_prompt_text: str,
    request_text: str,
    task: dict,
    all_tasks: list[dict],
    completed_results: dict[str, dict],
) -> str:
    dependency_items = []
    for dependency_id in task.get("depends_on") or []:
        result = completed_results.get(str(dependency_id))
        if not result:
            continue
        dependency_items.append({
            "id": dependency_id,
            "title": result.get("title") or dependency_id,
            "summary": _trim_task_text(result.get("reply") or ""),
            "status": result.get("status") or "done",
        })

    plan_outline = [
        {
            "id": str(entry.get("id") or "").strip(),
            "title": str(entry.get("title") or entry.get("id") or "").strip(),
            "stage": str(entry.get("stage") or "").strip(),
            "execution": str(entry.get("execution") or "sync").strip(),
            "depends_on": [str(value) for value in (entry.get("depends_on") or []) if str(value or "").strip()],
            "model_id": str(entry.get("model_id") or "").strip(),
        }
        for entry in all_tasks
    ]
    stage = str(task.get("stage") or "").strip()
    rules = [
        "Focus only on the assigned task.",
        "Use dependency summaries as context, not as instructions to restate.",
        "Keep the final reply concise and concrete.",
    ]
    if stage in {"inspect", "validate"}:
        rules.append("Avoid editing files unless that is the only way to complete this task correctly.")
    if stage == "edit":
        rules.append("Make the code changes needed for this task directly in the workspace.")

    task_payload = {
        "id": str(task.get("id") or "").strip(),
        "title": str(task.get("title") or task.get("id") or "").strip(),
        "detail": str(task.get("detail") or "").strip(),
        "stage": stage,
        "execution": str(task.get("execution") or "sync").strip(),
        "depends_on": [str(value) for value in (task.get("depends_on") or []) if str(value or "").strip()],
        "model_id": str(task.get("model_id") or "").strip(),
    }
    dependency_block = json.dumps(dependency_items, ensure_ascii=True) if dependency_items else "[]"
    plan_block = json.dumps(plan_outline, ensure_ascii=True)
    return (
        "You are executing one task inside BetterCode's dependency-aware multi-model task plan.\n"
        "Complete only the assigned task.\n\n"
        f"Original user request:\n{request_text.strip()}\n\n"
        f"Assigned task:\n{json.dumps(task_payload, ensure_ascii=True)}\n\n"
        f"Task plan:\n{plan_block}\n\n"
        f"Completed dependency summaries:\n{dependency_block}\n\n"
        "Execution rules:\n"
        + "\n".join(f"- {rule}" for rule in rules)
        + "\n\nBase workspace prompt:\n"
        + base_prompt_text.strip()
    )


def verify_task_completion_locally(
    request_text: str,
    model_id: str,
    task_analysis: dict,
    combined_reply: str,
    selector_runtime_status: dict | None = None,
) -> dict:
    """Lightweight local check that planned tasks appear completed."""
    planned = task_analysis.get("tasks") or []
    total = len(planned)
    if not total:
        return {"summary": "Tasks completed.", "verified": True}
    summary_lines = [f"- {str(task.get('title') or task.get('id') or 'task').strip()}" for task in planned]
    summary = f"Completed {total} task{'s' if total != 1 else ''}:\n" + "\n".join(summary_lines)
    return {"summary": summary, "verified": True}


def _fallback_task_turn_reply(
    task_breakdown: dict,
    task_results: list[dict],
    change_summary: str,
) -> str:
    completed = [result for result in task_results if result.get("status") == "done"]
    if len(completed) == 1 and not change_summary:
        return str(completed[0].get("reply") or "").strip()

    summary = _task_breakdown_summary(task_breakdown)
    lead = f"Completed {summary}." if summary else "Completed the planned work."
    lines = [lead]
    if change_summary:
        lines.append(change_summary)
    for result in completed[:3]:
        title = str(result.get("title") or result.get("id") or "Task").strip()
        reply = _trim_task_text(result.get("reply") or "", max_chars=TASK_REPLY_SNIPPET_CHARS)
        if reply:
            lines.append(f"{title}: {reply}")
    return "\n\n".join(line for line in lines if line).strip()


def _manual_task_analysis(
    db,
    workspace: Workspace,
    request_text: str,
    attachments: list[dict],
    tab: WorkspaceTab | None = None,
) -> dict:
    return _manual_task_analysis_base(db, workspace, request_text, attachments, tab=tab)


def _ensure_default_workspace():
    with SessionLocal() as db:
        _get_or_create_workspace(db, os.getcwd())


# Static files are read once at import time and served from memory so that any
# edits made to the source files during an active session (e.g. when BetterCode
# is used to work on its own code) cannot corrupt the currently running app.
_STATIC_FILE_CACHE: dict[str, str] = {}
_STATIC_FILE_CACHE_LOCK = threading.Lock()


def _read_static_file(filename: str) -> str:
    with _STATIC_FILE_CACHE_LOCK:
        if filename not in _STATIC_FILE_CACHE:
            _STATIC_FILE_CACHE[filename] = (STATIC_DIR / filename).read_text(encoding="utf-8")
        return _STATIC_FILE_CACHE[filename]


def list_workspaces_payload() -> dict:
    with SessionLocal() as db:
        workspaces = db.query(Workspace).order_by(Workspace.created_at.desc()).all()
        touched = False
        for workspace in workspaces:
            _ensure_workspace_tab(db, workspace)
            if getattr(workspace, "generated_files_seen_count", None) is None:
                workspace.generated_files_seen_count = _workspace_generated_file_count(workspace)
                touched = True
        if touched:
            db.commit()
            for workspace in workspaces:
                db.refresh(workspace)
        return {"workspaces": [_serialize_workspace(workspace) for workspace in workspaces]}


def create_workspace_payload(path: str) -> dict:
    with SessionLocal() as db:
        workspace = _get_or_create_workspace(db, path)
        return {"workspace": _serialize_workspace(workspace)}


def create_workspace_tab_payload(workspace_id: int, title: str | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _create_workspace_tab(db, workspace, title=title)
        return {"workspace": _serialize_workspace(workspace), "tab": _serialize_tab(tab)}


def archive_workspace_tab_payload(workspace_id: int, tab_id: int) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        now = _utcnow()
        tab.archived_at = now
        tab.updated_at = now
        tab.session_state = "cold"
        workspace.last_used_at = now
        db.commit()

        remaining_tabs = (
            db.query(WorkspaceTab)
            .filter(WorkspaceTab.workspace_id == workspace.id, WorkspaceTab.archived_at.is_(None))
            .order_by(WorkspaceTab.sort_order.asc(), WorkspaceTab.id.asc())
            .all()
        )
        next_tab = remaining_tabs[0] if remaining_tabs else _create_workspace_tab(db, workspace)
        _rebalance_workspace_session_pool(db)
        db.commit()
        db.refresh(tab)
        db.refresh(workspace)
        return {
            "workspace": _serialize_workspace(workspace),
            "tab": _serialize_tab(tab),
            "next_tab_id": next_tab.id if next_tab is not None else None,
        }


def restore_workspace_tab_payload(workspace_id: int, tab_id: int) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id, allow_archived=True, create_missing=False)
        if tab.archived_at is None:
            return {"workspace": _serialize_workspace(workspace), "tab": _serialize_tab(tab)}

        last_sort = (
            db.query(WorkspaceTab.sort_order)
            .filter(WorkspaceTab.workspace_id == workspace.id, WorkspaceTab.archived_at.is_(None))
            .order_by(WorkspaceTab.sort_order.desc(), WorkspaceTab.id.desc())
            .first()
        )
        now = _utcnow()
        tab.archived_at = None
        tab.sort_order = (int(last_sort[0] or 0) + 1) if last_sort else 0
        tab.last_used_at = now
        tab.updated_at = now
        workspace.last_used_at = now
        _rebalance_workspace_session_pool(db)
        db.commit()
        db.refresh(tab)
        db.refresh(workspace)
        return {"workspace": _serialize_workspace(workspace), "tab": _serialize_tab(tab)}


def create_workspace_folder_payload(parent_path: str, name: str) -> dict:
    normalized_parent = _normalize_workspace_path(parent_path)
    normalized_name = _normalize_workspace_folder_name(name)
    target_path = Path(normalized_parent) / normalized_name

    if target_path.exists():
        raise HTTPException(status_code=400, detail="A directory with that project name already exists in the selected location.")

    try:
        target_path.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not create project directory: {exc}") from exc

    return create_workspace_payload(str(target_path))


def create_current_workspace_payload() -> dict:
    return create_workspace_payload(os.getcwd())


def choose_workspace_payload(directory_chooser: Callable[[], str | None] | None) -> dict:
    if directory_chooser is None:
        raise HTTPException(status_code=501, detail="Directory chooser is not available in this runtime.")

    chosen = directory_chooser()
    if not chosen:
        return {"cancelled": True}

    payload = create_workspace_payload(chosen)
    payload["cancelled"] = False
    return payload


def pick_workspace_path_payload(directory_chooser: Callable[[], str | None] | None) -> dict:
    if directory_chooser is None:
        raise HTTPException(status_code=501, detail="Directory chooser is not available in this runtime.")

    chosen = directory_chooser()
    if not chosen:
        return {"cancelled": True}

    normalized_path = _normalize_workspace_path(chosen)
    return {
        "cancelled": False,
        "path": normalized_path,
        "name": Path(normalized_path).name or normalized_path,
    }


def _normalize_message_page_size(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_MESSAGE_PAGE_SIZE
    return max(1, min(MAX_MESSAGE_PAGE_SIZE, int(limit)))


def get_messages_payload(
    workspace_id: int,
    tab_id: int | None = None,
    limit: int | None = None,
    before_id: int | None = None,
) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        if prune_expired_memory_entries(db, workspace, tab):
            db.commit()
        page_size = _normalize_message_page_size(limit)
        query = (
            db.query(Message)
            .filter(Message.workspace_id == workspace_id, Message.tab_id == tab.id)
        )
        if before_id is not None:
            query = query.filter(Message.id < before_id)

        fetched = (
            query.order_by(Message.id.desc())
            .limit(page_size + 1)
            .all()
        )
        has_more = len(fetched) > page_size
        page_messages = fetched[:page_size]
        messages = list(reversed(page_messages))
        next_before_id = messages[0].id if has_more and messages else None
        return {
            "workspace": _serialize_workspace(workspace),
            "tab": _serialize_tab(tab),
            "messages": [_serialize_message(message) for message in messages],
            "memory": {
                "entries": [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)],
            },
            "paging": {
                "limit": page_size,
                "before_id": before_id,
                "next_before_id": next_before_id,
                "has_more": has_more,
            },
        }


def memory_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        pruned = prune_expired_memory_entries(db, workspace, tab)
        if pruned:
            db.commit()
        entries = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
        return {
            "workspace": _serialize_workspace(workspace),
            "tab": _serialize_tab(tab),
            "memory": {
                "entries": entries,
            },
        }


def clear_memory_payload(workspace_id: int, tab_id: int | None = None, bucket: str = "all") -> dict:
    normalized_bucket = (bucket or "all").strip().lower() or "all"
    if normalized_bucket not in {"all", "short", "medium", "long"}:
        raise HTTPException(status_code=400, detail="Bucket must be one of: all, short, medium, long.")
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        deleted = clear_memory_entries(db, workspace, tab, None if normalized_bucket == "all" else normalized_bucket)
        db.commit()
        remaining = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
        return {
            "workspace": _serialize_workspace(workspace),
            "tab": _serialize_tab(tab),
            "deleted": deleted,
            "bucket": normalized_bucket,
            "memory": {
                "entries": remaining,
            },
        }


def rename_workspace_payload(workspace_id: int, name: str) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)

        workspace.name = _make_unique_workspace_name(db, name, exclude_id=workspace.id)
        db.commit()
        db.refresh(workspace)
        return {"workspace": _serialize_workspace(workspace)}


def delete_workspace_payload(workspace_id: int) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        generated_root = _workspace_generated_dir(workspace, create=False)

        db.delete(workspace)
        db.commit()
        _delete_workspace_generated_files_base(generated_root)
        return {"deleted": True, "workspace_id": workspace_id}


def generated_files_payload(workspace_id: int) -> dict:
    _invalidate_generated_file_count_cache(workspace_id)
    return _generated_files_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        serialize_workspace=_serialize_workspace,
        workspace_generated_dir=_workspace_generated_dir,
        workspace_generated_file_entries=_workspace_generated_file_entries,
    )


def mark_generated_files_seen_payload(workspace_id: int) -> dict:
    return _mark_generated_files_seen_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        workspace_generated_file_count=_workspace_generated_file_count,
        serialize_workspace=_serialize_workspace,
    )


def _open_with_system_default(path: Path):
    _open_with_system_default_base(path, launch_fn=_launch_detached_command)


def open_generated_file_payload(workspace_id: int, relative_path: str) -> dict:
    return _open_generated_file_payload_base(
        workspace_id,
        relative_path,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        resolve_generated_file_path=_resolve_generated_file_path,
        workspace_generated_dir=_workspace_generated_dir,
        open_with_system_default=_open_with_system_default,
    )


def open_telemetry_log_payload() -> dict:
    return _open_telemetry_log_payload_base(
        telemetry_log_path=_telemetry_log_path,
        open_with_system_default=_open_with_system_default,
    )


def save_api_key_payload(provider: str, api_key: str) -> dict:
    set_api_key(provider, api_key)
    _clear_model_discovery_cache()
    return _auth_status()


def save_subscription_login_payload(username: str, password: str) -> dict:
    if not login(username, password):
        raise HTTPException(status_code=401, detail="Login failed.")
    _clear_model_discovery_cache()
    return _auth_status()


def _memory_command_payload(
    db,
    workspace: Workspace,
    tab: WorkspaceTab,
    command: dict,
    user_message: Message,
) -> dict:
    action = command["action"]
    model_id = "system/memory"
    runtime = "system"
    if action == "review":
        messages = _memory_review_messages(db, workspace, tab)
        transcript = _messages_transcript(messages, MEMORY_REVIEW_TRANSCRIPT_CHARS)
        if not transcript:
            reply_text = "Not enough chat history to review for memory yet."
            memory_entries = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
        else:
            stored_entries, result = _review_chat_memory(db, workspace, tab, mode="review", transcript=transcript)
            model_id = result.get("model") or model_id
            runtime = result.get("runtime") or "local"
            reply_text = _memory_review_response_text(stored_entries)
            memory_entries = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
    elif action == "show":
        memory_entries = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
        reply_text = _memory_text_response(memory_entries)
    else:
        bucket = command.get("bucket") or "all"
        deleted = clear_memory_entries(db, workspace, tab, None if bucket == "all" else bucket)
        memory_entries = [serialize_memory_entry(entry) for entry in list_memory_entries(db, workspace, tab)]
        reply_text = _memory_clear_response_text(bucket, deleted)

    assistant_message = _persist_workspace_message(
        db,
        workspace,
        tab,
        "assistant",
        reply_text,
        recommendations=json.dumps([]),
        routing_meta=json.dumps(
            {
                "mode": "memory",
                "selector": "memory",
                "selector_label": "Memory Manager",
                "model_id": model_id,
                "model_label": "Local Memory Review" if runtime == "local" else "Memory Manager",
                "runtime": runtime,
                "task_type": "memory",
                "reason": f"Handled /memory {action}.",
                "change_summary": "",
            }
        ),
    )
    db.commit()
    db.refresh(tab)
    db.refresh(workspace)
    return {
        "tab": _serialize_tab(tab),
        "user_message": _serialize_message(user_message),
        "message": _serialize_message(assistant_message),
        "model": model_id,
        "runtime": runtime,
        "memory": {
            "entries": memory_entries,
        },
    }


def chat_payload(
    workspace_id: int,
    text: str,
    model: str = "smart",
    attachments: list[ChatAttachment] | None = None,
    agent_mode: str | None = None,
    tab_id: int | None = None,
) -> dict:
    turn_started_at = time.monotonic()
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        normalized_text = _normalize_chat_text(text)
        normalized_attachments = _normalize_chat_attachments(attachments or [])
        selected_model = _normalize_selected_model(model)
        requested_agent_mode = _resolve_requested_agent_mode(selected_model, agent_mode, available_models=_model_options())
        _record_last_chat_request(tab, normalized_text, normalized_attachments, selected_model, requested_agent_mode)
        user_message_content = _build_user_message_content(normalized_text, normalized_attachments)
        selector_request_text = _build_selector_request_text(normalized_text, normalized_attachments)
        _auto_title_tab_from_request(db, tab, selector_request_text)
        memory_command = _memory_command(normalized_text)
        if memory_command is not None:
            user_message = _persist_workspace_message(db, workspace, tab, "user", user_message_content)
            return _memory_command_payload(db, workspace, tab, memory_command, user_message)
        prompt_text = _build_prompt_text(
            normalized_text,
            normalized_attachments,
            _build_workspace_prompt_context(db, workspace, selector_request_text, normalized_attachments, tab),
            generated_files_dir=str(_workspace_generated_dir(workspace, create=True)),
            generated_files_staging_dir=str(_workspace_generated_staging_dir(workspace, create=True)),
            human_language=get_human_language(),
        )
        turn_context = _capture_turn_context(workspace)
        log_event(
            "chat_turn_started",
            workspace_id=workspace_id,
            stream=False,
            requested_model=selected_model,
            agent_mode=requested_agent_mode,
            attachment_count=len(normalized_attachments),
            text_length=len(selector_request_text),
        )

        user_message = _persist_workspace_message(db, workspace, tab, "user", user_message_content)

        selected_source = "manual"
        selected_model_label = _model_label(selected_model)
        selection_reasoning = "Model selected directly."
        task_analysis = _manual_task_analysis(
            db,
            workspace,
            selector_request_text,
            normalized_attachments,
            tab=tab,
        )
        if selected_model == "smart":
            preprocess_started_at = time.monotonic()
            selector_context, task_analysis, routing_history, available_models, selection = _selector_preprocess_turn(
                db,
                workspace,
                selector_request_text,
                normalized_attachments,
                agent_mode=requested_agent_mode,
                tab=tab,
            )
            selected_model = selection["selected_model"]
            task_analysis = selection.get("task_analysis") or task_analysis
            selected_source = selection.get("source") or "auto"
            selection_reasoning = selection.get("reasoning") or "Auto Model Select routed this turn."
            selected_model_label = selection.get("selected_model_label") or _model_label(selected_model)
            refined_context = (selection.get("refined_context") or "").strip()
            if refined_context:
                prompt_text = f"Router analysis:\n{refined_context}\n\n{prompt_text}"
            log_event(
                "chat_preprocess_completed",
                workspace_id=workspace_id,
                stream=False,
                requested_model=model,
                selected_model=selected_model,
                selector=selected_source,
                duration_ms=duration_ms(preprocess_started_at),
            )

        _mark_workspace_session_busy(db, workspace, tab)
        try:
            reply = _generate_assistant_reply(
                prompt_text,
                selector_request_text,
                db,
                workspace,
                tab,
                selected_model,
                requested_agent_mode,
                selected_source=selected_source,
                task_analysis=task_analysis,
                selection_reasoning=selection_reasoning,
                selected_model_label=selected_model_label,
                turn_context=turn_context,
            )
            log_event(
                "chat_turn_completed",
                workspace_id=workspace_id,
                stream=False,
                requested_model=model,
                selected_model=reply["model"],
                runtime=reply["runtime"],
                selector=selected_source,
                duration_ms=duration_ms(turn_started_at),
            )
            return {
                "tab": _serialize_tab(tab),
                "user_message": _serialize_message(user_message),
                **reply,
            }
        except Exception as exc:
            runtime, _, _ = _resolve_runtime_model(selected_model)
            failure = _classify_turn_failure(exc)
            _record_router_telemetry(
                db,
                workspace,
                selected_model,
                runtime,
                selected_source,
                task_analysis,
                success=False,
                changed_files=0,
            )
            log_event(
                "chat_turn_failed",
                workspace_id=workspace_id,
                stream=False,
                requested_model=model,
                selected_model=selected_model,
                runtime=runtime,
                selector=selected_source,
                duration_ms=duration_ms(turn_started_at),
                error=failure["message"],
                failure_category=failure["category"],
            )
            raise


def _build_review_prompt(files_with_content: list[dict], depth: str, human_language: str | None = None) -> str:
    depth_instructions = {
        "quick": "Focus only on the most critical bugs and security issues. Return no more than 5 findings.",
        "standard": "Review for bugs, security vulnerabilities, performance issues, and code quality concerns.",
        "deep": "Perform a comprehensive review covering bugs, security, performance, maintainability, architecture, and style.",
    }
    depth_instruction = depth_instructions.get(depth, depth_instructions["standard"])
    files_block = "\n\n".join(
        f'<file path="{f["path"]}">\n{f["content"]}\n</file>'
        for f in files_with_content
    )
    return (
        "You are a code reviewer. Analyze the files below and return ONLY a JSON object — no markdown fences, no explanation, just the raw JSON.\n\n"
        f"{language_runtime_instruction(human_language)}\n"
        f"Review scope: {depth_instruction}\n\n"
        'Return this exact structure:\n'
        '{\n'
        '  "summary": "2-3 sentence overall assessment",\n'
        '  "findings": [\n'
        '    {\n'
        '      "id": "f1",\n'
        '      "severity": "critical|high|medium|low|info",\n'
        '      "category": "bug|security|performance|style|maintainability",\n'
        '      "title": "Brief title",\n'
        '      "description": "What the issue is and why it matters",\n'
        '      "file": "relative/path/to/file",\n'
        '      "line_hint": "42 or null",\n'
        '      "fix_instruction": "Precise instruction for an AI coding assistant to fix this"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        f"Files to review:\n\n{files_block}"
    )


def _parse_review_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {}


def _serialize_code_review(review: CodeReview) -> dict:
    return {
        "id": review.id,
        "workspace_id": review.workspace_id,
        "depth": review.depth,
        "files": _deserialize_json_list(review.files),
        "primary_model": review.primary_model,
        "secondary_model": review.secondary_model,
        "primary_model_label": review.primary_model_label,
        "secondary_model_label": review.secondary_model_label,
        "summary_primary": review.summary_primary,
        "summary_secondary": review.summary_secondary,
        "findings": _deserialize_json_list(review.findings),
        "activity_log": _deserialize_json_list(review.activity_log),
        "created_at": review.created_at.isoformat() if review.created_at else "",
    }


def review_history_payload(workspace_id: int, limit: int = 50) -> dict:
    with SessionLocal() as db:
        _get_workspace_or_404(db, workspace_id)
        reviews = (
            db.query(CodeReview)
            .filter(CodeReview.workspace_id == workspace_id)
            .order_by(CodeReview.created_at.desc())
            .limit(limit)
            .all()
        )
        return {"reviews": [_serialize_code_review(r) for r in reviews]}


def review_run_payload(workspace_id: int, files: list[str], depth: str, primary_model: str, secondary_model: str):
    def _event_stream():
        with SessionLocal() as db:
            workspace = _get_workspace_or_404(db, workspace_id)
            workspace_path = workspace.path

        files_with_content = []
        for rel_path in (files or [])[:200]:
            try:
                abs_path = _resolve_workspace_relative_path(workspace_path, rel_path, require_file=True)
            except HTTPException as exc:
                yield _stream_event_bytes("error", message=exc.detail)
                return
            try:
                raw = abs_path.read_bytes()
                if b"\x00" in raw:
                    # Binary file — including its raw bytes in a CLI prompt arg causes
                    # "embedded null byte" errors on POSIX. Skip and note it.
                    files_with_content.append({"path": rel_path, "content": "[Binary file — skipped]"})
                    continue
                content = raw.decode("utf-8", errors="replace")
                if len(content) > 80000:
                    content = content[:80000] + "\n... (truncated)"
                files_with_content.append({"path": rel_path, "content": content})
            except Exception as exc:
                files_with_content.append({"path": rel_path, "content": f"[Error reading file: {exc}]"})

        if not files_with_content:
            yield _stream_event_bytes("error", message="No files selected for review.")
            return

        primary_prompt = _build_review_prompt(files_with_content, depth, human_language=get_human_language())

        # Resolve primary model
        raw_primary = (primary_model or "smart").strip()
        if raw_primary == "smart":
            runtimes = _cli_runtimes()
            if runtimes.get("claude", {}).get("available"):
                resolved_primary = "claude/default"
            elif runtimes.get("codex", {}).get("available"):
                resolved_primary = "codex/default"
            elif runtimes.get("cursor", {}).get("available"):
                resolved_primary = "cursor/default"
            elif runtimes.get("gemini", {}).get("available"):
                resolved_primary = "gemini/default"
            else:
                yield _stream_event_bytes("error", message="No supported coding CLI is installed.")
                return
        else:
            resolved_primary = raw_primary

        activity_log: list[str] = []
        history_log: list[str] = []
        summary_primary = ""
        summary_secondary = ""
        secondary_label = ""
        all_findings: list[dict] = []

        try:
            runtime, model_name, reasoning_effort = _resolve_runtime_model(resolved_primary)
            model_label = _model_label(resolved_primary)
            yield _stream_event_bytes("status", role="primary", message=f"Running primary review with {model_label}\u2026", model=resolved_primary, model_label=model_label)

            if runtime == "codex":
                cli_result = yield from _stream_codex_cli(
                    workspace_path, primary_prompt, model_name, reasoning_effort,
                    activity_log=activity_log, history_log=history_log,
                )
            elif runtime == "cursor":
                cli_result = yield from _stream_cursor_cli(
                    workspace_path, primary_prompt, model_name,
                    activity_log=activity_log, history_log=history_log,
                )
            elif runtime == "claude":
                cli_result = yield from _stream_claude_cli(
                    workspace_path, primary_prompt, model_name,
                    activity_log=activity_log, history_log=history_log,
                    reasoning_effort=reasoning_effort,
                )
            else:
                cli_result = yield from _stream_gemini_cli(
                    workspace_path, primary_prompt, model_name,
                    activity_log=activity_log, history_log=history_log,
                )

            primary_reply = cli_result.get("reply", "")
            yield _stream_event_bytes("result", role="primary", content=primary_reply, model=resolved_primary, model_label=model_label)
            primary_parsed = _parse_review_json(primary_reply)
            summary_primary = primary_parsed.get("summary", "")
            all_findings += [{"_source": "primary", **f} for f in primary_parsed.get("findings", [])]

        except HTTPException as exc:
            yield _stream_event_bytes("error", message=exc.detail)
            return
        except Exception as exc:
            yield _stream_event_bytes("error", message=str(exc))
            return

        raw_secondary = (secondary_model or "none").strip()
        if raw_secondary and raw_secondary != "none":
            secondary_activity: list[str] = []
            secondary_history: list[str] = []
            try:
                secondary_runtime, secondary_model_name, secondary_reasoning = _resolve_runtime_model(raw_secondary)
                secondary_label = _model_label(raw_secondary)
                yield _stream_event_bytes("status", role="secondary", message=f"Running secondary review with {secondary_label}\u2026", model=raw_secondary, model_label=secondary_label)

                secondary_prompt = (
                    "A primary code reviewer analyzed these files and produced the following findings:\n\n"
                    f"{primary_reply}\n\n"
                    "Now perform your own independent review of the same files. Focus on findings the primary reviewer may have missed. "
                    "Return ONLY a JSON object in the same format (summary + findings array).\n\n"
                    "Files:\n\n"
                    + "\n\n".join(f'<file path="{f["path"]}">\n{f["content"]}\n</file>' for f in files_with_content)
                )

                if secondary_runtime == "codex":
                    cli_result2 = yield from _stream_codex_cli(
                        workspace_path, secondary_prompt, secondary_model_name, secondary_reasoning,
                        activity_log=secondary_activity, history_log=secondary_history,
                    )
                elif secondary_runtime == "cursor":
                    cli_result2 = yield from _stream_cursor_cli(
                        workspace_path, secondary_prompt, secondary_model_name,
                        activity_log=secondary_activity, history_log=secondary_history,
                    )
                elif secondary_runtime == "claude":
                    cli_result2 = yield from _stream_claude_cli(
                        workspace_path, secondary_prompt, secondary_model_name,
                        activity_log=secondary_activity, history_log=secondary_history,
                        reasoning_effort=secondary_reasoning,
                    )
                else:
                    cli_result2 = yield from _stream_gemini_cli(
                        workspace_path, secondary_prompt, secondary_model_name,
                        activity_log=secondary_activity, history_log=secondary_history,
                    )

                secondary_reply = cli_result2.get("reply", "")
                yield _stream_event_bytes("result", role="secondary", content=secondary_reply, model=raw_secondary, model_label=secondary_label)
                secondary_parsed = _parse_review_json(secondary_reply)
                summary_secondary = secondary_parsed.get("summary", "")
                all_findings += [{"_source": "secondary", **f} for f in secondary_parsed.get("findings", [])]

            except HTTPException as exc:
                yield _stream_event_bytes("status", role="secondary", message=f"Secondary review skipped: {exc.detail}")
            except Exception as exc:
                yield _stream_event_bytes("status", role="secondary", message=f"Secondary review error: {exc}")

        review_id = None
        try:
            with SessionLocal() as db:
                review = CodeReview(
                    workspace_id=workspace_id,
                    depth=depth or "standard",
                    files=json.dumps(files or []),
                    primary_model=resolved_primary,
                    secondary_model=raw_secondary if raw_secondary and raw_secondary != "none" else "",
                    primary_model_label=model_label,
                    secondary_model_label=secondary_label,
                    summary_primary=summary_primary,
                    summary_secondary=summary_secondary,
                    findings=json.dumps(all_findings),
                    activity_log=json.dumps(activity_log),
                )
                db.add(review)
                db.commit()
                db.refresh(review)
                review_id = review.id
        except Exception:
            pass

        yield _stream_event_bytes("final", review_id=review_id)

    return StreamingResponse(_event_stream(), media_type="application/x-ndjson")


def chat_stream_payload(
    workspace_id: int,
    text: str,
    model: str = "smart",
    attachments: list[ChatAttachment] | None = None,
    agent_mode: str | None = None,
    tab_id: int | None = None,
):
    def _event_stream():
        turn_started_at = time.monotonic()
        with SessionLocal() as db:
            workspace = _get_workspace_or_404(db, workspace_id)
            tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
            chat_process_key = tab.id
            activity_log = []
            history_log = []
            terminal_log_parts: list[str] = []
            task_graph: list[dict] = []

            def _upsert_task(task_id: str, **fields) -> None:
                for task in task_graph:
                    if task.get("id") == task_id:
                        task.update(fields)
                        return
                task_graph.append({"id": task_id, **fields})

            def _emit_task_graph():
                return _stream_event_bytes("task_state", tasks=task_graph)

            def _update_task_if_present(task_id: str, **fields) -> None:
                for task in task_graph:
                    if task.get("id") == task_id:
                        task.update(fields)
                        return

            def _planner_task_selection_reason(task_id: str) -> str:
                if task_id == "preprocess":
                    return "The local router handles the pre-processing pass before BetterCode starts the actual runtime."
                if task_id == "route":
                    return "The local router assigns the best available model to each task before execution starts."
                if task_id == "plan":
                    return "The local router turns the routed request into an execution plan before BetterCode starts running tasks."
                if task_id == "breakdown":
                    return "The local router breaks the request into executable tasks and records their dependencies."
                return ""

            def _execution_task_selection_reason(
                selected_model_id: str,
                selected_model_source: str,
                reasoning: str,
                breakdown_enabled: bool,
            ) -> str:
                if selected_model_source == "manual":
                    base = "You selected this runtime directly, so BetterCode is executing the turn on it."
                else:
                    trimmed_reason = (reasoning or "").strip().rstrip(".")
                    base = (
                        f"Auto Model Select chose this runtime because {trimmed_reason}."
                        if trimmed_reason
                        else "Auto Model Select chose this runtime for the turn."
                    )
                if not breakdown_enabled:
                    return base
                if "@" in selected_model_id:
                    effort = selected_model_id.rsplit("@", 1)[-1].strip().lower()
                    effort_label = _reasoning_effort_label(effort).lower() if effort else "selected"
                    return (
                        f"{base} Planned task tracks are local-router suggestions by base model family, so they do not repeat the "
                        f"{effort_label} effort suffix shown on this runtime."
                    )
                return f"{base} Planned task tracks are local-router suggestions and may not match the actual runtime one-for-one."

            normalized_text = _normalize_chat_text(text)
            normalized_attachments = _normalize_chat_attachments(attachments or [])
            selected_model = _normalize_selected_model(model)
            requested_agent_mode = _resolve_requested_agent_mode(selected_model, agent_mode, available_models=_model_options())
            _record_last_chat_request(tab, normalized_text, normalized_attachments, selected_model, requested_agent_mode)
            user_message_content = _build_user_message_content(normalized_text, normalized_attachments)
            selector_request_text = _build_selector_request_text(normalized_text, normalized_attachments)
            _auto_title_tab_from_request(db, tab, selector_request_text)
            memory_command = _memory_command(normalized_text)
            if memory_command is not None:
                user_message = _persist_workspace_message(db, workspace, tab, "user", user_message_content)
                if memory_command["action"] == "review":
                    yield _stream_event_bytes("status", message="Reviewing this chat for memory with the local model.")
                elif memory_command["action"] == "show":
                    yield _stream_event_bytes("status", message="Loading saved memory for this chat.")
                else:
                    yield _stream_event_bytes("status", message="Clearing saved memory for this chat.")
                payload = _memory_command_payload(db, workspace, tab, memory_command, user_message)
                yield _stream_event_bytes(
                    "final",
                    model=payload["model"],
                    runtime=payload["runtime"],
                    tab=payload["tab"],
                    message=payload["message"],
                    user_message=payload["user_message"],
                )
                return
            prompt_text = _build_prompt_text(
                normalized_text,
                normalized_attachments,
                _build_workspace_prompt_context(db, workspace, selector_request_text, normalized_attachments, tab),
                generated_files_dir=str(_workspace_generated_dir(workspace, create=True)),
                generated_files_staging_dir=str(_workspace_generated_staging_dir(workspace, create=True)),
                human_language=get_human_language(),
            )
            turn_context = _capture_turn_context(workspace)
            log_event(
                "chat_turn_started",
                workspace_id=workspace_id,
                stream=True,
                requested_model=selected_model,
                agent_mode=requested_agent_mode,
                attachment_count=len(normalized_attachments),
                text_length=len(selector_request_text),
            )

            user_message = _persist_workspace_message(db, workspace, tab, "user", user_message_content)
            selected_source = "manual"
            selected_model_label = _model_label(selected_model)
            selection_reasoning = "Model selected directly."
            task_breakdown_enabled = get_enable_task_breakdown() and requested_agent_mode != "plan"
            task_analysis = _manual_task_analysis(
                db,
                workspace,
                selector_request_text,
                normalized_attachments,
                tab=tab,
            )
            routing_model_id = selected_model
            task_breakdown: dict = {}
            planned_subtasks: list[dict] = []
            multi_model_execution = False
            try:
                if selected_model == "smart":
                    preprocess_started_at = time.monotonic()
                    _upsert_task(
                        "preprocess",
                        title="Gathering requirements",
                        status="running",
                        selection_reason=_planner_task_selection_reason("preprocess"),
                        kind="system",
                        track_key="system:planner",
                        track_label="Planner",
                        track_kind="system",
                        progress=0.05,
                    )
                    _upsert_task(
                        "route",
                        title="Planning",
                        status="pending",
                        selection_reason=_planner_task_selection_reason("route"),
                        kind="system",
                        track_key="system:planner",
                        track_label="Planner",
                        track_kind="system",
                    )
                    _upsert_task(
                        "execute",
                        title="Execute tasks",
                        status="waiting",
                        model_label="",
                        selection_reason="Run the planned work in order, using async lanes where tasks are independent.",
                        kind="system",
                        track_key="system:execution",
                        track_label="Execution",
                        track_kind="system",
                        waiting_on=[],
                    )
                    _upsert_task(
                        "validate_completion",
                        title="Validate completion",
                        status="waiting",
                        model_label="",
                        selection_reason="The local router reviews the completed task results and confirms the request was fully addressed.",
                        kind="system",
                        track_key="system:completion",
                        track_label="Completion",
                        track_kind="system",
                        waiting_on=["execute"],
                    )
                    yield _emit_task_graph()

                    selector_context, task_analysis, routing_history, available_models, selector_runtime_status = _selector_preprocess_context(
                        db,
                        workspace,
                        selector_request_text,
                        normalized_attachments,
                        agent_mode=requested_agent_mode,
                        tab=tab,
                    )
                    message = "The local router is pre-processing the request."
                    _append_activity_line(activity_log, message)
                    yield _stream_event_bytes("status", message=message)

                    _upsert_task("preprocess", status="done", progress=1.0)
                    _upsert_task("route", status="running")
                    yield _emit_task_graph()

                    local_selection = maybe_select_local_execution(
                        selector_request_text,
                        selector_context,
                        task_analysis=task_analysis,
                        selector_runtime_status=selector_runtime_status,
                    )

                    if task_breakdown_enabled and local_selection is None:
                        _upsert_task(
                            "breakdown",
                            title="Task breakdown",
                            status="running",
                            selection_reason=_planner_task_selection_reason("breakdown"),
                            kind="system",
                            track_key="system:planner",
                            track_label="Planner",
                            track_kind="system",
                        )
                        yield _emit_task_graph()
                        plan = plan_subtasks(
                            selector_request_text,
                            available_models,
                            selector_context,
                            routing_history=routing_history,
                            selector_runtime_status=selector_runtime_status,
                        )
                        for planned in plan.get("tasks") or []:
                            raw_id = str(planned.get("id") or "").strip()
                            if not raw_id:
                                continue
                            task_id = f"subtask:{raw_id}"
                            planned_subtasks.append({
                                "id": task_id,
                                "title": planned.get("title") or raw_id,
                                "status": "planned",
                                "kind": "planned",
                                "model_id": planned.get("model_id") or "",
                                "model_label": planned.get("model_label") or _model_label(planned.get("model_id") or "") or planned.get("model_id") or "",
                                "stage": planned.get("stage") or "",
                                "execution": planned.get("execution") or "sync",
                                "depends_on": [
                                    f"subtask:{str(dep).strip()}"
                                    for dep in (planned.get("depends_on") or [])
                                    if str(dep or "").strip()
                                ],
                                "detail": planned.get("detail") or "",
                                "selection_reason": planned.get("selection_reason") or "",
                                "track_key": planned.get("track_key") or "",
                                "track_label": planned.get("track_label") or planned.get("model_label") or planned.get("model_id") or "",
                                "track_kind": planned.get("track_kind") or "model",
                                "parallel_group": planned.get("parallel_group") or "",
                            })

                    if planned_subtasks:
                        task_breakdown = _serialize_task_breakdown(planned_subtasks)
                        task_summary = _task_breakdown_summary(task_breakdown)
                        selected_source = (plan.get("source") or "local").strip() or "local"
                        selection_reasoning = (
                            f"Auto Model Select split the request into {task_summary} with dependency-aware scheduling."
                            if task_summary
                            else "Auto Model Select split the request into dependency-aware tasks."
                        )
                        selected_model = task_breakdown.get("primary_model_id") or selected_model
                        routing_model_id = "multi-model"
                        selected_model_label = task_breakdown.get("label") or "Multi-model plan"
                        multi_model_execution = True
                        log_event(
                            "chat_preprocess_completed",
                            workspace_id=workspace_id,
                            stream=True,
                            requested_model=model,
                            selected_model=selected_model,
                            selector=selected_source,
                            duration_ms=duration_ms(preprocess_started_at),
                        )
                        message = (
                            f"Auto Model Select planned {task_summary}."
                            if task_summary
                            else "Auto Model Select planned dependency-aware tasks."
                        )
                        _append_activity_line(activity_log, message)
                        yield _stream_event_bytes(
                            "status",
                            message=message,
                            selected_model=routing_model_id,
                            selected_model_label=selected_model_label,
                            selection_reasoning=selection_reasoning,
                        )
                        _upsert_task(
                            "route",
                            status="done",
                            progress=1.0,
                            detail=f"Assigned models for {task_summary}." if task_summary else "Assigned models for the task plan.",
                            selection_reason="The local router assigns the best available model to each task before execution starts.",
                        )
                        _upsert_task("breakdown", status="done", progress=1.0)
                        for planned in planned_subtasks:
                            _upsert_task(planned["id"], **{key: value for key, value in planned.items() if key != "id"})
                        _upsert_task(
                            "execute",
                            status="running",
                            model_label="",
                            selection_reason="Run the task graph in dependency order. Independent inspect and validation tasks can run in parallel.",
                            detail=f"Plan: {task_summary}." if task_summary else "Executing the planned task graph.",
                            model_id=routing_model_id,
                            track_key="system:execution",
                            track_label="Execution",
                            track_kind="system",
                            waiting_on=[],
                        )
                    else:
                        if local_selection is not None:
                            selection = local_selection
                        else:
                            selection = _resolve_better_select_model(
                                db,
                                workspace,
                                selector_request_text,
                                normalized_attachments,
                                agent_mode=requested_agent_mode,
                                tab=tab,
                                selector_context=selector_context,
                                task_analysis=task_analysis,
                                routing_history=routing_history,
                                available_models=available_models,
                                selector_runtime_status=selector_runtime_status,
                            )
                        selected_model = selection["selected_model"]
                        routing_model_id = selected_model
                        task_analysis = selection.get("task_analysis") or task_analysis
                        selected_source = selection.get("source") or "auto"
                        selection_reasoning = selection.get("reasoning") or "Auto Model Select routed this turn."
                        selected_model_label = selection.get("selected_model_label") or _model_label(selected_model)
                        refined_context = (selection.get("refined_context") or "").strip()
                        if refined_context:
                            prompt_text = f"Router analysis:\n{refined_context}\n\n{prompt_text}"
                        log_event(
                            "chat_preprocess_completed",
                            workspace_id=workspace_id,
                            stream=True,
                            requested_model=model,
                            selected_model=selected_model,
                            selector=selected_source,
                            duration_ms=duration_ms(preprocess_started_at),
                        )
                        message = f"Auto Model Select chose {selection['selected_model_label']}. {selection['reasoning']}"
                        _append_activity_line(activity_log, message)
                        yield _stream_event_bytes(
                            "status",
                            message=message,
                            selected_model=selected_model,
                            selected_model_label=selected_model_label,
                            selection_reasoning=selection_reasoning,
                        )
                        _upsert_task("route", status="done", progress=1.0)
                        _update_task_if_present("breakdown", status="done", progress=1.0, detail="No subtask plan was needed for this turn.")
                        _upsert_task(
                            "execute",
                            status="running",
                            model_label="",
                            selection_reason=_execution_task_selection_reason(
                                selected_model,
                                selected_source,
                                selection_reasoning,
                                False,
                            ),
                            detail=f"Runtime: {selected_model_label}.",
                            model_id=selected_model,
                            track_key="system:execution",
                            track_label="Execution",
                            track_kind="system",
                            waiting_on=[],
                        )
                else:
                    routing_model_id = selected_model
                    _upsert_task(
                        "execute",
                        title="Execute tasks",
                        status="running",
                        kind="system",
                        model_id=selected_model,
                        model_label="",
                        selection_reason=_execution_task_selection_reason(
                            selected_model,
                            selected_source,
                            selection_reasoning,
                            False,
                        ),
                        detail=f"Turn runtime: {selected_model_label}.",
                        track_key="system:execution",
                        track_label="Execution",
                        track_kind="system",
                        waiting_on=[],
                    )
                    _upsert_task(
                        "validate_completion",
                        title="Validate completion",
                        status="waiting",
                        model_label="",
                        selection_reason="The local router reviews the completed task results and confirms the request was fully addressed.",
                        kind="system",
                        track_key="system:completion",
                        track_label="Completion",
                        track_kind="system",
                        waiting_on=["execute"],
                    )
                    message = f"Using {selected_model_label}."
                    _append_activity_line(activity_log, message)
                    yield _stream_event_bytes(
                        "status",
                        message=message,
                        selected_model=selected_model,
                        selected_model_label=selected_model_label,
                        selection_reasoning=selection_reasoning,
                    )
                yield _emit_task_graph()

                # Prompt enrichment: for non-trivial tasks, search the codebase and
                # have the local model produce a structured context brief for the CLI.
                _enrichment = _enrich_cli_prompt(normalized_text, workspace.path, task_analysis)
                if _enrichment:
                    prompt_text = f"Pre-execution context analysis:\n{_enrichment}\n\n{prompt_text}"
                    yield _emit_status_event(activity_log, history_log,
                                             message="Context enriched with codebase analysis.")

                def _make_task_stream_handler(task: dict, stream_queue_obj: queue.Queue) -> Callable[[dict], None]:
                    task_title = task.get("title") or task.get("id") or "Task"
                    model_label = task.get("model_label") or _model_label(task.get("model_id") or "") or ""
                    header = f"\n[{task_title}{' · ' + model_label if model_label else ''}]\n"
                    header_emitted = False

                    def _handler(event: dict) -> None:
                        nonlocal header_emitted
                        if not isinstance(event, dict):
                            return
                        event_type = str(event.get("type") or "").strip()
                        text = str(event.get("text") or "")
                        if event_type == "input_required":
                            prompt = str(event.get("prompt") or "").strip()
                            if prompt:
                                stream_queue_obj.put({
                                    "type": "input_required",
                                    "prompt": f"[{task_title}] {prompt}",
                                })
                            return
                        if event_type not in {"terminal_chunk", "history_line"}:
                            return
                        if not header_emitted and (text or event_type == "history_line"):
                            stream_queue_obj.put({"type": "terminal_chunk", "text": header})
                            header_emitted = True
                        if event_type == "terminal_chunk":
                            if text:
                                stream_queue_obj.put({"type": "terminal_chunk", "text": text})
                            return
                        stripped = text.strip()
                        if stripped:
                            stream_queue_obj.put({"type": "history_line", "text": f"[{task_title}] {stripped}"})

                    return _handler

                def _drain_task_stream_queue(stream_queue_obj: queue.Queue):
                    while True:
                        try:
                            event = stream_queue_obj.get_nowait()
                        except queue.Empty:
                            break
                        event_type = str(event.get("type") or "").strip()
                        if event_type == "terminal_chunk":
                            text = str(event.get("text") or "")
                            if text:
                                _append_terminal_chunk(terminal_log_parts, text)
                                yield _stream_event_bytes("terminal_chunk", text=text)
                        elif event_type == "history_line":
                            text = str(event.get("text") or "").strip()
                            if text:
                                _append_history_line(history_log, text)
                        elif event_type == "input_required":
                            prompt = str(event.get("prompt") or "").strip()
                            if prompt:
                                yield _stream_event_bytes("input_required", prompt=prompt)

                _mark_workspace_session_busy(db, workspace, tab)
                if multi_model_execution:
                    task_results_by_id: dict[str, dict] = {}
                    task_results: list[dict] = []
                    pending_ids = [task["id"] for task in planned_subtasks]
                    tasks_by_id = {task["id"]: task for task in planned_subtasks}
                    _register_orchestrated_chat_group(chat_process_key, runtime="multi")
                    try:
                        while pending_ids:
                            if _chat_stop_requested(chat_process_key):
                                raise ChatStoppedError("Chat stopped.")
                            ready = [
                                tasks_by_id[task_id]
                                for task_id in pending_ids
                                if all(dep_id in task_results_by_id for dep_id in tasks_by_id[task_id].get("depends_on") or [])
                            ]
                            if not ready:
                                raise HTTPException(status_code=500, detail="Task plan dependencies could not be resolved.")

                            async_batch = [
                                task
                                for task in ready
                                if task.get("execution") == "async" and task.get("stage") != "edit"
                            ][:MAX_PARALLEL_SUBTASKS]
                            batch = async_batch or [ready[0]]
                            total_tasks = len(planned_subtasks)

                            for task in batch:
                                _update_task_if_present(
                                    task["id"],
                                    status="running",
                                    detail=task.get("detail") or f"Running {task.get('title') or task['id']}.",
                                )
                                model_label = task.get("model_label") or _model_label(task.get("model_id") or "")
                                yield _emit_status_event(
                                    activity_log,
                                    history_log,
                                    message=f"Starting {task.get('title') or task['id']} with {model_label}.",
                                )
                            _upsert_task(
                                "execute",
                                detail=f"Running {len(task_results_by_id) + 1} of {total_tasks} tasks.",
                            )
                            yield _emit_task_graph()

                            prompts = {
                                task["id"]: _build_task_execution_prompt(
                                    prompt_text,
                                    selector_request_text,
                                    task,
                                    planned_subtasks,
                                    task_results_by_id,
                                )
                                for task in batch
                            }

                            completed_batch: list[tuple[dict, dict]] = []
                            try:
                                if len(batch) == 1:
                                    task = batch[0]
                                    _task_model = task.get("model_id") or selected_model
                                    _task_prompt = prompts[task["id"]]
                                    _task_excluded: set[str] = set()
                                    _task_fallback_attempted = False
                                    while True:
                                        stream_queue = queue.Queue()
                                        stream_handler = _make_task_stream_handler(task, stream_queue)
                                        try:
                                            with ThreadPoolExecutor(max_workers=1) as executor:
                                                future = executor.submit(
                                                    _run_orchestrated_task_cli,
                                                    workspace.path,
                                                    _task_prompt,
                                                    _task_model,
                                                    requested_agent_mode,
                                                    workspace_id=chat_process_key,
                                                    stream_handler=stream_handler,
                                                )
                                                while True:
                                                    done, _ = wait((future,), timeout=0.1, return_when=FIRST_COMPLETED)
                                                    yield from _drain_task_stream_queue(stream_queue)
                                                    if done:
                                                        _task_result = future.result()
                                                        break
                                                    if _chat_stop_requested(chat_process_key):
                                                        raise ChatStoppedError("Chat stopped.")
                                            break  # success
                                        except HTTPException as _task_exc:
                                            if not _task_fallback_attempted and _is_usage_limit_error(str(_task_exc.detail)):
                                                _task_fallback_attempted = True
                                                _task_excluded.add(_task_model)
                                                _task_fb = _pick_cli_fallback(_task_excluded, selector_request_text)
                                                if _task_fb:
                                                    _task_old_label = _model_label(_task_model)
                                                    _task_model = _task_fb["selected_model"]
                                                    _task_new_label = _task_fb.get("selected_model_label") or _model_label(_task_model)
                                                    yield _emit_status_event(
                                                        activity_log, history_log,
                                                        message=f"{_task_old_label} is unavailable. Switching to {_task_new_label}…",
                                                    )
                                                    continue
                                            raise
                                    completed_batch.append((task, _task_result))
                                else:
                                    stream_queue = queue.Queue()
                                    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_SUBTASKS, len(batch))) as executor:
                                        future_map = {
                                            executor.submit(
                                                _run_orchestrated_task_cli,
                                                workspace.path,
                                                prompts[task["id"]],
                                                task.get("model_id") or selected_model,
                                                requested_agent_mode,
                                                workspace_id=chat_process_key,
                                                stream_handler=_make_task_stream_handler(task, stream_queue),
                                            ): task
                                            for task in batch
                                        }
                                        while future_map:
                                            done, _ = wait(tuple(future_map.keys()), timeout=0.1, return_when=FIRST_COMPLETED)
                                            yield from _drain_task_stream_queue(stream_queue)
                                            if not done:
                                                if _chat_stop_requested(chat_process_key):
                                                    raise ChatStoppedError("Chat stopped.")
                                                continue
                                            for future in done:
                                                task_for_future = future_map.pop(future)
                                                completed_batch.append((task_for_future, future.result()))
                                        yield from _drain_task_stream_queue(stream_queue)
                            except Exception:
                                _kill_orchestrated_chat_group(chat_process_key)
                                raise

                            for task, task_result_payload in completed_batch:
                                task_reply = str(task_result_payload.get("reply") or "").strip()
                                resolved_model_id = str(task_result_payload.get("model") or task.get("model_id") or "").strip()
                                resolved_model_label = _model_label(resolved_model_id) or task.get("model_label") or resolved_model_id
                                result = {
                                    **task,
                                    "status": "done",
                                    "reply": task_reply,
                                    "runtime": task_result_payload.get("runtime") or "",
                                    "resolved_model_id": resolved_model_id,
                                    "resolved_model_label": resolved_model_label,
                                }
                                task_results_by_id[task["id"]] = result
                                task_results.append(result)
                                pending_ids.remove(task["id"])
                                _update_task_if_present(
                                    task["id"],
                                    status="done",
                                    detail=_trim_task_text(task_reply, TASK_REPLY_SNIPPET_CHARS) or (task.get("detail") or ""),
                                    model_id=resolved_model_id or task.get("model_id") or "",
                                    model_label=resolved_model_label or task.get("model_label") or "",
                                )
                                yield _emit_status_event(
                                    activity_log,
                                    history_log,
                                    message=f"Completed {task.get('title') or task['id']}.",
                                )

                            _upsert_task(
                                "execute",
                                detail=f"Completed {len(task_results_by_id)} of {total_tasks} tasks.",
                            )
                            yield _emit_task_graph()
                    finally:
                        _clear_orchestrated_chat_group(chat_process_key)

                    # Local model validates the completed tasks.
                    if task_results:
                        local_model_label = local_preprocess_model_label(
                            (selector_runtime_status or {}).get("selected_model") or
                            (selector_runtime_status or {}).get("model") or ""
                        ) if selector_runtime_status else ""
                        _update_task_if_present(
                            "validate_completion",
                            status="running",
                            model_label=local_model_label or "Local Router",
                            progress=0.3,
                        )
                        yield _emit_task_graph()
                        combined_task_reply = "\n\n".join(
                            r.get("reply") or "" for r in task_results if r.get("reply")
                        )
                        local_verification = verify_task_completion_locally(
                            selector_request_text,
                            task_breakdown.get("primary_model_id") or selected_model,
                            task_analysis,
                            combined_task_reply,
                            selector_runtime_status=selector_runtime_status,
                        )
                        _update_task_if_present(
                            "validate_completion",
                            status="done",
                            model_label=local_model_label or "Local Router",
                            progress=1.0,
                            detail=(local_verification or {}).get("summary") or "Tasks completed.",
                        )
                        yield _emit_task_graph()

                    cli_result = {
                        "reply": "",
                        "model": task_breakdown.get("primary_model_id") or selected_model,
                        "runtime": "multi",
                    }
                else:
                    _excluded_models: set[str] = set()
                    _fallback_attempted = False
                    while True:
                        runtime, model_name, reasoning_effort = _resolve_runtime_model(selected_model)
                        runtime_prompt = prompt_text + _runtime_prompt_suffix(runtime)
                        try:
                            if runtime == "local":
                                message = f"Answering locally with {selected_model_label or local_preprocess_model_label(model_name or '')}..."
                                yield _emit_status_event(activity_log, history_log, message=message)
                                try:
                                    local_prompt = _build_local_turn_prompt(db, workspace, tab, selector_request_text)
                                    cli_result = run_local_model_response(
                                        local_prompt,
                                        model_id=model_name,
                                        human_language=get_human_language(),
                                    )
                                except RuntimeError as exc:
                                    raise HTTPException(status_code=503, detail=str(exc)) from exc
                            elif runtime == "codex":
                                cli_result = yield from _stream_codex_cli(
                                    workspace.path,
                                    runtime_prompt,
                                    model_name,
                                    reasoning_effort,
                                    agent_mode=requested_agent_mode,
                                    session_id=(_workspace_session_id(tab, "codex") or None),
                                    activity_log=activity_log,
                                    history_log=history_log,
                                    workspace_id=chat_process_key,
                                    terminal_log=terminal_log_parts,
                                )
                            elif runtime == "cursor":
                                start_message = f"Starting Cursor with {_resolved_runtime_model_id('cursor', model_name)}..."
                                yield _emit_status_event(activity_log, history_log, message=start_message)
                                cli_result = yield from _stream_cursor_cli(
                                    workspace.path,
                                    runtime_prompt,
                                    model_name,
                                    agent_mode=requested_agent_mode,
                                    session_id=(_workspace_session_id(tab, "cursor") or None),
                                    activity_log=activity_log,
                                    history_log=history_log,
                                    workspace_id=chat_process_key,
                                    terminal_log=terminal_log_parts,
                                )
                            elif runtime == "claude":
                                start_message = f"Starting Claude with {_resolved_runtime_model_id('claude', model_name, reasoning_effort)}..."
                                yield _emit_status_event(activity_log, history_log, message=start_message)
                                cli_result = yield from _stream_claude_cli(
                                    workspace.path,
                                    runtime_prompt,
                                    model_name,
                                    session_id=(_workspace_session_id(tab, "claude") or None),
                                    agent_mode=requested_agent_mode,
                                    activity_log=activity_log,
                                    history_log=history_log,
                                    workspace_id=chat_process_key,
                                    reasoning_effort=reasoning_effort,
                                    terminal_log=terminal_log_parts,
                                )
                            else:
                                message = f"Starting {runtime.title()} with {_resolved_runtime_model_id(runtime, model_name)}..."
                                yield _emit_status_event(activity_log, history_log, message=message)
                                cli_result = yield from _stream_gemini_cli(
                                    workspace.path,
                                    runtime_prompt,
                                    model_name,
                                    agent_mode=requested_agent_mode,
                                    activity_log=activity_log,
                                    history_log=history_log,
                                    workspace_id=chat_process_key,
                                    terminal_log=terminal_log_parts,
                                )
                            break  # success — exit retry loop
                        except HTTPException as _cli_exc:
                            if not _fallback_attempted and _is_usage_limit_error(str(_cli_exc.detail)):
                                _fallback_attempted = True
                                _excluded_models.add(selected_model)
                                _fb = _pick_cli_fallback(_excluded_models, selector_request_text)
                                if _fb:
                                    _old_label = selected_model_label or _model_label(selected_model)
                                    selected_model = _fb["selected_model"]
                                    selected_model_label = _fb.get("selected_model_label") or _model_label(selected_model)
                                    yield _emit_status_event(
                                        activity_log, history_log,
                                        message=f"{_old_label} is unavailable. Switching to {selected_model_label}…",
                                    )
                                    continue  # retry with fallback model
                            raise  # not a usage limit, or no fallback available

                    cli_result["reply"] = _normalize_cli_reply(cli_result.get("reply", ""), runtime)
                _upsert_task("execute", status="done", progress=1.0)
                if not multi_model_execution:
                    _update_task_if_present(
                        "validate_completion",
                        status="running",
                        progress=0.45,
                        detail="Checking results, collecting changes, and preparing the final response.",
                    )
                yield _emit_task_graph()
                _invalidate_workspace_caches(workspace.path)
                _invalidate_generated_file_count_cache(workspace.id)
                _relocate_new_workspace_files(workspace, turn_context)
                change_log = _workspace_turn_changes(workspace.path, turn_context)
                if multi_model_execution:
                    task_breakdown = _serialize_task_breakdown([
                        task
                        for task in task_graph
                        if str(task.get("kind") or "").strip() == "planned"
                    ])
                    cli_result["reply"] = _fallback_task_turn_reply(
                        task_breakdown,
                        task_results,
                        _build_change_summary(change_log),
                    )
                assistant_message = _persist_workspace_message(
                    db,
                    workspace,
                    tab,
                    "assistant",
                    cli_result["reply"],
                    activity_log=json.dumps(activity_log),
                    history_log=json.dumps(history_log),
                    terminal_log="".join(terminal_log_parts),
                    change_log=json.dumps(change_log),
                    recommendations=json.dumps([]),
                    routing_meta=json.dumps(_build_routing_meta(
                        routing_model_id,
                        selected_source,
                        task_analysis,
                        cli_result,
                        selection_reasoning=selection_reasoning,
                        selected_model_label=selected_model_label,
                        change_summary=_build_change_summary(change_log),
                        task_breakdown=task_breakdown,
                    )),
                )
                _record_workspace_runtime_state(db, workspace, tab, cli_result)
                _record_router_telemetry(
                    db,
                    workspace,
                    cli_result["model"],
                    cli_result["runtime"],
                    selected_source,
                    task_analysis,
                    success=True,
                    changed_files=len(change_log),
                )

                _update_task_if_present("validate_completion", status="done", progress=1.0)
                yield _emit_task_graph()

                yield _stream_event_bytes(
                    "final",
                    model=cli_result["model"],
                    runtime=cli_result["runtime"],
                    tab=_serialize_tab(tab),
                    message=_serialize_message(assistant_message),
                    user_message=_serialize_message(user_message),
                )
                log_event(
                    "chat_turn_completed",
                    workspace_id=workspace_id,
                    stream=True,
                    requested_model=model,
                    selected_model=cli_result["model"],
                    runtime=cli_result["runtime"],
                    selector=selected_source,
                    duration_ms=duration_ms(turn_started_at),
                )

                _start_turn_postprocess(
                    assistant_message.id,
                    workspace.id,
                    tab.id,
                    selector_request_text,
                    cli_result["reply"],
                    change_log,
                )
            except ChatStoppedError:
                _append_activity_line(activity_log, "Turn stopped.")
                _upsert_task("execute", status="stopped")
                _update_task_if_present("preprocess", status="stopped")
                _update_task_if_present("route", status="stopped")
                _update_task_if_present("breakdown", status="stopped")
                _update_task_if_present("validate_completion", status="stopped")
                for task in task_graph:
                    if task.get("kind") == "planned" and task.get("status") not in {"done", "error"}:
                        task["status"] = "stopped"
                yield _emit_task_graph()
                log_event(
                    "chat_turn_cancelled",
                    workspace_id=workspace_id,
                    stream=True,
                    requested_model=model,
                    selected_model=selected_model,
                    selector=selected_source,
                    duration_ms=duration_ms(turn_started_at),
                )
                yield _stream_event_bytes("cancelled", message="Turn stopped.")
            except HTTPException as exc:
                failure = _classify_turn_failure(exc)
                message = f"{failure['message']} {failure['retry_hint']}".strip()
                runtime = ""
                try:
                    runtime, _, _ = _resolve_runtime_model(selected_model)
                except Exception:
                    runtime = ""
                _record_router_telemetry(
                    db,
                    workspace,
                    selected_model,
                    runtime,
                    selected_source,
                    task_analysis,
                    success=False,
                    changed_files=0,
                )
                _append_activity_line(activity_log, message)
                _upsert_task("execute", status="error")
                _update_task_if_present("preprocess", status="error")
                _update_task_if_present("route", status="error")
                _update_task_if_present("breakdown", status="error")
                _update_task_if_present("validate_completion", status="error")
                for task in task_graph:
                    if task.get("kind") == "planned" and task.get("status") not in {"done", "stopped"}:
                        task["status"] = "error"
                yield _emit_task_graph()
                log_event(
                    "chat_turn_failed",
                    workspace_id=workspace_id,
                    stream=True,
                    requested_model=model,
                    selected_model=selected_model,
                    runtime=runtime,
                    selector=selected_source,
                    duration_ms=duration_ms(turn_started_at),
                    error=message,
                    failure_category=failure["category"],
                )
                yield _stream_event_bytes("error", message=message)
            except Exception as exc:
                failure = _classify_turn_failure(exc)
                message = f"{failure['message']} {failure['retry_hint']}".strip()
                runtime = ""
                try:
                    runtime, _, _ = _resolve_runtime_model(selected_model)
                except Exception:
                    runtime = ""
                _record_router_telemetry(
                    db,
                    workspace,
                    selected_model,
                    runtime,
                    selected_source,
                    task_analysis,
                    success=False,
                    changed_files=0,
                )
                _append_activity_line(activity_log, message)
                _upsert_task("execute", status="error")
                _update_task_if_present("preprocess", status="error")
                _update_task_if_present("route", status="error")
                _update_task_if_present("breakdown", status="error")
                _update_task_if_present("validate_completion", status="error")
                for task in task_graph:
                    if task.get("kind") == "planned" and task.get("status") not in {"done", "stopped"}:
                        task["status"] = "error"
                yield _emit_task_graph()
                log_event(
                    "chat_turn_failed",
                    workspace_id=workspace_id,
                    stream=True,
                    requested_model=model,
                    selected_model=selected_model,
                    runtime=runtime,
                    selector=selected_source,
                    duration_ms=duration_ms(turn_started_at),
                    error=message,
                    failure_category=failure["category"],
                )
                yield _stream_event_bytes("error", message=message)

    return StreamingResponse(_event_stream(), media_type="application/x-ndjson")


def retry_chat_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        text, model, agent_mode, attachments = _last_chat_request_or_400(tab)
    return chat_payload(workspace_id, text, model, attachments, agent_mode=agent_mode, tab_id=tab.id)


def retry_chat_stream_payload(workspace_id: int, tab_id: int | None = None):
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
        text, model, agent_mode, attachments = _last_chat_request_or_400(tab)
    return chat_stream_payload(workspace_id, text, model, attachments, agent_mode=agent_mode, tab_id=tab.id)


def chat_input_payload(workspace_id: int, text: str, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
    process_key = tab.id
    # If the streaming generator is waiting for input (blocked on queue), unblock it
    with PENDING_CHAT_INPUT_LOCK:
        q = PENDING_CHAT_INPUT.get(process_key)
    if q is not None:
        q.put(text)
        return {"sent": True}

    # Fallback: write directly to subprocess stdin
    with ACTIVE_CHAT_PROCESSES_LOCK:
        process = ACTIVE_CHAT_PROCESSES.get(process_key)
    if process is None or process.poll() is not None:
        _clear_active_chat_process(process_key)
        raise HTTPException(status_code=404, detail="No active CLI process for this tab.")
    if not process.stdin:
        raise HTTPException(status_code=400, detail="CLI process stdin is not available.")
    try:
        process.stdin.write(text + "\n")
        process.stdin.flush()
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Could not write to CLI process.") from exc
    return {"sent": True}


def chat_status_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
    return {"chat": _active_chat_status_payload(tab.id)}


def stop_chat_payload(workspace_id: int, tab_id: int | None = None) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        tab = _get_workspace_tab_or_404(db, workspace, tab_id=tab_id)
    process_key = tab.id
    with ACTIVE_CHAT_PROCESSES_LOCK:
        process = ACTIVE_CHAT_PROCESSES.get(process_key)
    orchestrated_status = _active_orchestrated_chat_status_payload(process_key)
    has_orchestrated = bool(orchestrated_status and orchestrated_status.get("active"))
    if (process is None or process.poll() is not None) and not has_orchestrated:
        _clear_active_chat_process(process_key)
        return {"stopped": False, "already_finished": True}

    _request_chat_stop(process_key)
    with PENDING_CHAT_INPUT_LOCK:
        pending_queue = PENDING_CHAT_INPUT.get(process_key)
    if pending_queue is not None:
        pending_queue.put("")
    stopped = has_orchestrated
    pid = 0
    if process is not None and process.poll() is None:
        pid = process.pid
        _kill_process_tree(process)
        stopped = True
    if _kill_orchestrated_chat_group(process_key):
        stopped = True
    log_event("chat_turn_stop_requested", workspace_id=workspace_id, tab_id=tab.id, pid=pid)
    return {"stopped": stopped, "already_finished": not stopped}


def restart_selector_runtime_payload() -> dict:
    stop_managed_ollama()
    try:
        status = require_selector_runtime(
            start_if_needed=True,
            warm_model=False,
            startup_timeout=10.0,
        )
    except RuntimeError as exc:
        log_event("selector_runtime_restart_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    log_event("selector_runtime_restarted", status=status)
    return {
        "selector": status,
        "message": "Auto Model Select runtime restarted.",
    }


def install_selector_model_payload(model_id: str) -> dict:
    normalized = str(model_id or "").strip()
    candidate = installable_local_preprocess_model(normalized, mode="small")
    if not candidate:
        raise HTTPException(status_code=400, detail="Unsupported local preprocess model.")
    try:
        pull_local_preprocess_model(normalized)
    except RuntimeError as exc:
        log_event("selector_model_install_failed", model_id=normalized, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = selector_status()
    log_event("selector_model_installed", model_id=normalized, selector=status)
    return {
        "ok": True,
        "model_id": normalized,
        "selector": status,
        "message": f"Installed {normalized}.",
    }


def _detect_prereqs(workspace_path: str) -> list[dict]:
    """Rule-based detection of setup commands needed before the project can run."""
    root = Path(workspace_path)
    prereqs: list[dict] = []

    # ── Node.js ───────────────────────────────────────────────────────────────
    if (root / "package.json").exists() and not (root / "node_modules").is_dir():
        if (root / "pnpm-lock.yaml").exists():
            cmd = "pnpm install"
        elif (root / "yarn.lock").exists():
            cmd = "yarn install"
        else:
            cmd = "npm install"
        prereqs.append({
            "command": cmd,
            "label": "Install Node.js dependencies",
            "reason": "node_modules not found",
        })

    # ── Python ───────────────────────────────────────────────────────────────
    has_venv = any((root / d).is_dir() for d in (".venv", "venv", "env"))
    if (root / "poetry.lock").exists() and not has_venv:
        prereqs.append({
            "command": "poetry install",
            "label": "Install Python dependencies",
            "reason": "poetry.lock found, no virtual environment detected",
        })
    elif (root / "requirements.txt").exists() and not has_venv:
        prereqs.append({
            "command": "pip install -r requirements.txt",
            "label": "Install Python dependencies",
            "reason": "requirements.txt found, no virtual environment detected",
        })

    # ── Ruby ─────────────────────────────────────────────────────────────────
    if (root / "Gemfile").exists() and not (root / "vendor" / "bundle").is_dir():
        prereqs.append({
            "command": "bundle install",
            "label": "Install Ruby gems",
            "reason": "vendor/bundle not found",
        })

    # ── PHP ──────────────────────────────────────────────────────────────────
    if (root / "composer.json").exists() and not (root / "vendor").is_dir():
        prereqs.append({
            "command": "composer install",
            "label": "Install PHP dependencies",
            "reason": "vendor directory not found",
        })

    # ── Go ───────────────────────────────────────────────────────────────────
    if (root / "go.mod").exists() and not (root / "vendor").is_dir():
        prereqs.append({
            "command": "go mod download",
            "label": "Download Go modules",
            "reason": "vendor directory not found",
        })

    return prereqs


def detect_run_config_payload(workspace_id: int) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        workspace_path = workspace.path
    result = detect_project_run_config(workspace_path)
    result["prereqs"] = _detect_prereqs(workspace_path)
    return result


def get_run_settings_payload(workspace_id: int) -> dict:
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        try:
            settings = json.loads(workspace.run_settings or "{}")
        except (ValueError, TypeError):
            settings = {}
    return {"settings": settings}


def update_run_settings_payload(workspace_id: int, env: dict[str, str]) -> dict:
    clean_env = {str(k).strip(): str(v) for k, v in env.items() if str(k).strip()}
    settings = {"env": clean_env}
    with SessionLocal() as db:
        workspace = _get_workspace_or_404(db, workspace_id)
        workspace.run_settings = json.dumps(settings)
        db.commit()
    return {"settings": settings}


def _kill_process_tree(process: subprocess.Popen) -> None:
    _kill_process_tree_base(process)


def _kill_all_active_processes() -> None:
    with ACTIVE_RUN_PROCESSES_LOCK:
        run_procs = list(ACTIVE_RUN_PROCESSES.values())
    with ACTIVE_CHAT_PROCESSES_LOCK:
        chat_procs = list(ACTIVE_CHAT_PROCESSES.values())
    for proc in run_procs + chat_procs:
        try:
            _kill_process_tree(proc)
        except Exception:
            pass


def _sweep_active_run_processes() -> list[int]:
    cleared = []
    with ACTIVE_RUN_PROCESSES_LOCK:
        snapshot = list(ACTIVE_RUN_PROCESSES.items())
    for workspace_id, process in snapshot:
        if process.poll() is None:
            continue
        with ACTIVE_RUN_PROCESSES_LOCK:
            ACTIVE_RUN_PROCESSES.pop(workspace_id, None)
        cleared.append(workspace_id)
    return cleared


def _sweep_runtime_jobs(now: datetime | None = None) -> list[str]:
    reference = _coerce_utc(now) or _utcnow()
    cleared = []
    with RUNTIME_JOBS_LOCK:
        for job_id, job in list(RUNTIME_JOBS.items()):
            if job.get("status") == "running":
                continue
            finished_raw = job.get("finished_at") or ""
            try:
                finished_at = _coerce_utc(datetime.fromisoformat(finished_raw))
            except Exception:
                finished_at = None
            if finished_at is None:
                RUNTIME_JOBS.pop(job_id, None)
                cleared.append(job_id)
                continue
            if (reference - finished_at).total_seconds() >= RUNTIME_JOB_RETENTION_SECONDS:
                RUNTIME_JOBS.pop(job_id, None)
                cleared.append(job_id)
    return cleared


def _sweep_process_state() -> dict:
    return {
        "runs": _sweep_active_run_processes(),
        "chats": _sweep_inactive_chat_processes(),
        "runtime_jobs": _sweep_runtime_jobs(),
    }


def _start_process_sweeper(stop_event: threading.Event) -> threading.Thread:
    def _run():
        while not stop_event.wait(PROCESS_SWEEP_INTERVAL_SECONDS):
            try:
                _sweep_process_state()
            except Exception:
                pass

    thread = threading.Thread(target=_run, daemon=True, name="bettercode-process-sweeper")
    thread.start()
    return thread


def start_run_payload(workspace_id: int, command: str, env: dict[str, str]):
    def _event_stream():
        try:
            try:
                with SessionLocal() as db:
                    workspace = _get_workspace_or_404(db, workspace_id)
                    workspace_path = workspace.path
            except HTTPException as exc:
                yield _stream_event_bytes("error", message=str(exc.detail))
                return
            except Exception as exc:
                yield _stream_event_bytes("error", message=f"Failed to load workspace: {exc}")
                return

            with ACTIVE_RUN_PROCESSES_LOCK:
                existing = ACTIVE_RUN_PROCESSES.get(workspace_id)
            if existing is not None and existing.poll() is None:
                yield _stream_event_bytes("error", message="A run process is already active.")
                return

            run_env = os.environ.copy()
            # Merge saved run settings first (lowest priority)
            try:
                with SessionLocal() as _db:
                    _ws = _get_workspace_or_404(_db, workspace_id)
                    _saved = json.loads(_ws.run_settings or "{}")
                for k, v in _saved.get("env", {}).items():
                    if k and v:
                        run_env[k] = v
            except Exception:
                pass
            # Provided env overrides saved settings
            run_env.update(env)

            try:
                args = shlex.split(command)
            except ValueError as exc:
                yield _stream_event_bytes("error", message=f"Invalid command: {exc}")
                return
        except Exception as exc:
            yield _stream_event_bytes("error", message=f"Unexpected error: {exc}")
            return

        popen_kwargs: dict = dict(
            cwd=workspace_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=run_env,
        )
        # Launch in a new session so the whole process tree shares a pgid we can kill.
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(args, **popen_kwargs)
        except FileNotFoundError:
            yield _stream_event_bytes("error", message=f"Command not found: {args[0]}")
            return
        except Exception as exc:
            yield _stream_event_bytes("error", message=str(exc))
            return

        with ACTIVE_RUN_PROCESSES_LOCK:
            ACTIVE_RUN_PROCESSES[workspace_id] = process

        yield _stream_event_bytes("started", pid=process.pid)

        try:
            if process.stdout is None:
                yield _stream_event_bytes("error", message="Process stdout unavailable.")
                return
            for line in process.stdout:
                yield _stream_event_bytes("output", text=line)
            exit_code = process.wait()
            yield _stream_event_bytes("done", exit_code=exit_code)
        except Exception as exc:
            yield _stream_event_bytes("error", message=f"Stream error: {exc}")
        finally:
            with ACTIVE_RUN_PROCESSES_LOCK:
                ACTIVE_RUN_PROCESSES.pop(workspace_id, None)

    return StreamingResponse(_event_stream(), media_type="application/x-ndjson")


def stop_run_payload(workspace_id: int) -> dict:
    with ACTIVE_RUN_PROCESSES_LOCK:
        process = ACTIVE_RUN_PROCESSES.get(workspace_id)
    if process is None or process.poll() is not None:
        raise HTTPException(status_code=404, detail="No active run process for this workspace.")
    _kill_process_tree(process)
    return {"stopped": True}


def run_status_payload(workspace_id: int) -> dict:
    with ACTIVE_RUN_PROCESSES_LOCK:
        process = ACTIVE_RUN_PROCESSES.get(workspace_id)
    active = process is not None and process.poll() is None
    return {
        "active": active,
        "pid": process.pid if active else None,
    }


def git_status_payload(workspace_id: int) -> dict:
    return _git_status_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        parse_git_status=_parse_git_status,
    )


def review_files_payload(workspace_id: int, limit: int = DEFAULT_REVIEW_FILE_LIMIT) -> dict:
    return _review_files_payload_base(
        workspace_id,
        limit=limit,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        parse_git_status=_parse_git_status,
        review_changed_files=_review_changed_files,
        workspace_recent_file_entries=_workspace_recent_file_entries,
        serialize_workspace=_serialize_workspace,
    )


def git_stage_all_payload(workspace_id: int) -> dict:
    return _git_stage_all_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_unstage_all_payload(workspace_id: int) -> dict:
    return _git_unstage_all_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_stage_files_payload(workspace_id: int, paths: list[str]) -> dict:
    return _git_stage_files_payload_base(
        workspace_id,
        paths,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
        normalize_git_paths=_normalize_git_paths,
    )


def git_unstage_files_payload(workspace_id: int, paths: list[str]) -> dict:
    return _git_unstage_files_payload_base(
        workspace_id,
        paths,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
        normalize_git_paths=_normalize_git_paths,
    )


def git_init_payload(workspace_id: int) -> dict:
    return _git_init_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_fetch_payload(workspace_id: int) -> dict:
    return _git_fetch_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_pull_payload(workspace_id: int) -> dict:
    return _git_pull_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_update_payload(workspace_id: int) -> dict:
    return _git_update_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


def git_commit_payload(workspace_id: int, message: str) -> dict:
    return _git_commit_payload_base(
        workspace_id,
        message,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
        normalize_commit_message=_normalize_commit_message,
    )


def git_push_payload(workspace_id: int) -> dict:
    return _git_push_payload_base(
        workspace_id,
        session_factory=SessionLocal,
        get_workspace_or_404=_get_workspace_or_404,
        run_git=_run_git,
        invalidate_workspace_caches=_invalidate_workspace_caches,
        parse_git_status=_parse_git_status,
    )


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    # Pre-load static assets into the in-memory cache so that any file edits
    # made during a session (e.g. when BetterCode works on itself) do not
    # affect what the running app serves.
    for _static_name in ("index.html",):
        try:
            _read_static_file(_static_name)
        except Exception:
            pass

    init_db()
    _ensure_default_workspace()
    _reconcile_workspace_session_pool()
    _start_selector_warmup()
    sweep_stop_event = threading.Event()
    sweep_thread = _start_process_sweeper(sweep_stop_event)
    _start_model_discovery_warmup(verified=False)
    # App updates are temporarily disabled for this release.
    # _start_update_check_warmup()
    try:
        yield
    finally:
        sweep_stop_event.set()
        sweep_thread.join(timeout=1)
        _kill_all_active_processes()
        stop_managed_ollama()


def create_app(
    dev_mode: bool = False,
    directory_chooser: Callable[[], str | None] | None = None,
) -> FastAPI:
    app = FastAPI(title="BetterCode Desktop Web App", lifespan=_app_lifespan)
    app.state.dev_mode = dev_mode
    app.state.directory_chooser = directory_chooser
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(_read_static_file("index.html"))

    @app.get("/api/app/info")
    def app_info():
        runtimes = _cli_runtimes(quick=True)
        languages = supported_human_languages_payload()
        languages["current"] = get_human_language()
        languages["needs_setup"] = not has_explicit_human_language_setting()
        return build_app_info_payload(
            cwd=os.getcwd(),
            dev_mode=app.state.dev_mode,
            languages=languages,
            models=_model_options_for_app_info(),
            platform=os.name,
            runtimes=runtimes,
            auth=_auth_status(),
            selector=selector_status(),
            settings=get_app_settings(),
            telemetry=telemetry_info_payload(),
            update=_disabled_app_update_payload(),
            version=__version__,
        )

    @app.get("/api/app/update")
    def app_update(force: bool = False):
        return app_update_payload(force_refresh=force)

    @app.post("/api/app/update/install")
    def install_app_update(force: bool = True):
        return app_update_install_payload(force_refresh=force)

    @app.get("/api/app/telemetry")
    def app_telemetry(limit: int = 200):
        clamped_limit = max(1, min(int(limit), 1000))
        return {
            "telemetry": telemetry_info_payload(),
            "events": _recent_telemetry_events(limit=clamped_limit),
        }

    @app.post("/api/app/telemetry/open")
    def open_telemetry_log():
        return open_telemetry_log_payload()

    @app.get("/api/app/settings")
    def get_app_settings_route():
        return app_settings_payload()

    @app.post("/api/app/settings")
    def update_app_settings_route(request: AppSettingsRequest):
        previous_settings = get_app_settings()
        previous_selector = selector_status()
        updates = {}
        request_fields = set(getattr(request, "model_fields_set", getattr(request, "__fields_set__", set())))
        if "performance_profile" in request_fields:
            updates["performance_profile"] = request.performance_profile
        if "max_cost_tier" in request_fields:
            cost_tier = request.max_cost_tier
            if isinstance(cost_tier, str):
                cost_tier = cost_tier.strip().lower() or None
            updates["max_cost_tier"] = cost_tier
        if "auto_model_preference" in request_fields:
            preference = request.auto_model_preference
            if isinstance(preference, str):
                preference = preference.strip().lower() or None
            updates["auto_model_preference"] = preference
        if "enable_task_breakdown" in request_fields:
            updates["enable_task_breakdown"] = request.enable_task_breakdown
        if "enable_follow_up_suggestions" in request_fields:
            updates["enable_follow_up_suggestions"] = request.enable_follow_up_suggestions
        if "local_preprocess_mode" in request_fields:
            mode = request.local_preprocess_mode
            if isinstance(mode, str):
                mode = mode.strip().lower() or None
            updates["local_preprocess_mode"] = mode
        if "local_preprocess_model" in request_fields:
            model_name = request.local_preprocess_model
            if isinstance(model_name, str):
                model_name = model_name.strip() or None
            updates["local_preprocess_model"] = model_name
        if "font_size" in request_fields:
            font_size = request.font_size
            if isinstance(font_size, str):
                font_size = font_size.strip().lower() or None
            updates["font_size"] = font_size
        if "human_language" in request_fields:
            language = request.human_language
            if isinstance(language, str):
                language = language.strip().lower() or None
            updates["human_language"] = language
        try:
            set_app_settings(**updates)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        runtime_fields = {"local_preprocess_mode", "local_preprocess_model"}
        if runtime_fields.intersection(request_fields):
            next_settings = get_app_settings()
            previous_model = (
                previous_selector.get("selected_model")
                or previous_settings.get("local_preprocess_model")
            )
            try:
                apply_local_preprocess_runtime_change(
                    previous_model,
                    next_settings.get("local_preprocess_mode"),
                    next_settings.get("local_preprocess_model"),
                )
            except Exception as exc:
                try:
                    set_app_settings(
                        performance_profile=previous_settings.get("performance_profile"),
                        max_cost_tier=previous_settings.get("max_cost_tier"),
                        auto_model_preference=previous_settings.get("auto_model_preference"),
                        enable_task_breakdown=previous_settings.get("enable_task_breakdown"),
                        enable_follow_up_suggestions=previous_settings.get("enable_follow_up_suggestions"),
                        local_preprocess_mode=previous_settings.get("local_preprocess_mode"),
                        local_preprocess_model=previous_settings.get("local_preprocess_model"),
                        font_size=previous_settings.get("font_size"),
                        human_language=previous_settings.get("human_language"),
                    )
                except ValueError:
                    pass
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        return app_settings_payload()

    @app.post("/api/models/refresh")
    def refresh_models():
        return refresh_model_options_payload()

    @app.post("/api/runtimes/{runtime}/install")
    def install_runtime(runtime: str):
        return _install_runtime_payload(runtime)

    @app.post("/api/runtimes/{runtime}/login")
    def runtime_login(runtime: str):
        return runtime_login_payload(runtime)

    @app.post("/api/runtimes/{runtime}/logout")
    def runtime_logout(runtime: str):
        return runtime_logout_payload(runtime)

    @app.post("/api/selector/restart")
    def restart_selector_runtime():
        return restart_selector_runtime_payload()

    @app.post("/api/selector/models/install")
    def install_selector_model(request: SelectorModelInstallRequest):
        return install_selector_model_payload(request.model_id)

    @app.get("/api/runtime-jobs/{job_id}")
    def runtime_job(job_id: str):
        return runtime_job_payload(job_id)

    @app.get("/api/workspaces")
    def list_workspaces():
        return list_workspaces_payload()

    @app.post("/api/workspaces")
    def create_workspace(request: CreateWorkspaceRequest):
        return create_workspace_payload(request.path)

    @app.post("/api/workspaces/create-folder")
    def create_workspace_folder(request: CreateWorkspaceFolderRequest):
        return create_workspace_folder_payload(request.parent_path, request.name)

    @app.post("/api/workspaces/current")
    def create_current_workspace():
        return create_current_workspace_payload()

    @app.post("/api/workspaces/choose")
    def choose_workspace():
        return choose_workspace_payload(app.state.directory_chooser)

    @app.post("/api/workspaces/pick")
    def pick_workspace_path():
        return pick_workspace_path_payload(app.state.directory_chooser)

    @app.post("/api/workspaces/{workspace_id}/tabs")
    def create_workspace_tab(workspace_id: int):
        return create_workspace_tab_payload(workspace_id)

    @app.delete("/api/workspaces/{workspace_id}/tabs/{tab_id}")
    def archive_workspace_tab(workspace_id: int, tab_id: int):
        return archive_workspace_tab_payload(workspace_id, tab_id)

    @app.post("/api/workspaces/{workspace_id}/tabs/{tab_id}/restore")
    def restore_workspace_tab(workspace_id: int, tab_id: int):
        return restore_workspace_tab_payload(workspace_id, tab_id)

    @app.get("/api/workspaces/{workspace_id}/messages")
    def get_messages(
        workspace_id: int,
        tab_id: int | None = None,
        limit: int = DEFAULT_MESSAGE_PAGE_SIZE,
        before_id: int | None = None,
    ):
        return get_messages_payload(workspace_id, tab_id=tab_id, limit=limit, before_id=before_id)

    @app.get("/api/workspaces/{workspace_id}/memory")
    def get_memory(workspace_id: int, tab_id: int | None = None):
        return memory_payload(workspace_id, tab_id=tab_id)

    @app.delete("/api/workspaces/{workspace_id}/memory")
    def clear_memory(workspace_id: int, tab_id: int | None = None, bucket: str = "all"):
        return clear_memory_payload(workspace_id, tab_id=tab_id, bucket=bucket)

    @app.patch("/api/workspaces/{workspace_id}")
    def rename_workspace(workspace_id: int, request: RenameWorkspaceRequest):
        return rename_workspace_payload(workspace_id, request.name)

    @app.post("/api/workspaces/{workspace_id}/session/activate")
    def activate_workspace_session(workspace_id: int, tab_id: int | None = None):
        return activate_workspace_session_payload(workspace_id, tab_id=tab_id)

    @app.post("/api/workspaces/{workspace_id}/session/reset")
    def reset_workspace_session(workspace_id: int, tab_id: int | None = None):
        return reset_workspace_session_payload(workspace_id, tab_id=tab_id)

    @app.delete("/api/workspaces/{workspace_id}")
    def delete_workspace(workspace_id: int):
        return delete_workspace_payload(workspace_id)

    @app.get("/api/workspaces/{workspace_id}/generated-files")
    def generated_files(workspace_id: int):
        return generated_files_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/generated-files/seen")
    def mark_generated_files_seen(workspace_id: int):
        return mark_generated_files_seen_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/generated-files/open")
    def open_generated_file(workspace_id: int, request: GeneratedFileOpenRequest):
        return open_generated_file_payload(workspace_id, request.path)

    @app.get("/api/workspaces/{workspace_id}/git")
    def git_status(workspace_id: int):
        return git_status_payload(workspace_id)

    @app.get("/api/workspaces/{workspace_id}/review")
    def review_files(workspace_id: int, limit: int = DEFAULT_REVIEW_FILE_LIMIT):
        return review_files_payload(workspace_id, limit=limit)

    @app.get("/api/workspaces/{workspace_id}/review/all-files")
    def review_all_files(workspace_id: int):
        with SessionLocal() as db:
            workspace = _get_workspace_or_404(db, workspace_id)
        entries = _workspace_recent_file_entries(workspace.path, limit=500)
        return {"files": [e["path"] for e in entries], "total": len(entries)}

    @app.post("/api/workspaces/{workspace_id}/review/run")
    def run_review(workspace_id: int, request: ReviewRunRequest):
        return review_run_payload(workspace_id, request.files, request.depth, request.primary_model, request.secondary_model)

    @app.get("/api/workspaces/{workspace_id}/reviews")
    def list_reviews(workspace_id: int, limit: int = 50):
        return review_history_payload(workspace_id, limit=limit)

    @app.post("/api/workspaces/{workspace_id}/git/init")
    def git_init(workspace_id: int):
        return git_init_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/stage-all")
    def git_stage_all(workspace_id: int):
        return git_stage_all_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/stage")
    def git_stage(workspace_id: int, request: GitFilesRequest):
        return git_stage_files_payload(workspace_id, request.paths)

    @app.post("/api/workspaces/{workspace_id}/git/unstage-all")
    def git_unstage_all(workspace_id: int):
        return git_unstage_all_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/unstage")
    def git_unstage(workspace_id: int, request: GitFilesRequest):
        return git_unstage_files_payload(workspace_id, request.paths)

    @app.post("/api/workspaces/{workspace_id}/git/fetch")
    def git_fetch(workspace_id: int):
        return git_fetch_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/pull")
    def git_pull(workspace_id: int):
        return git_pull_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/update")
    def git_update(workspace_id: int):
        return git_update_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/git/commit")
    def git_commit(workspace_id: int, request: GitCommitRequest):
        return git_commit_payload(workspace_id, request.message)

    @app.post("/api/workspaces/{workspace_id}/git/push")
    def git_push(workspace_id: int):
        return git_push_payload(workspace_id)

    @app.get("/api/auth/status")
    def auth_status():
        return _auth_status()

    @app.post("/api/auth/api-key")
    def save_api_key(request: SaveApiKeyRequest):
        return save_api_key_payload(request.provider, request.api_key)

    @app.post("/api/auth/login")
    def save_subscription_login(request: LoginRequest):
        return save_subscription_login_payload(request.username, request.password)

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        return chat_payload(
            request.workspace_id,
            request.text,
            request.model,
            request.attachments,
            agent_mode=request.agent_mode,
            tab_id=request.tab_id,
        )

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest):
        return chat_stream_payload(
            request.workspace_id,
            request.text,
            request.model,
            request.attachments,
            agent_mode=request.agent_mode,
            tab_id=request.tab_id,
        )

    @app.get("/api/workspaces/{workspace_id}/chat/status")
    def chat_status(workspace_id: int, tab_id: int | None = None):
        return chat_status_payload(workspace_id, tab_id=tab_id)

    @app.post("/api/workspaces/{workspace_id}/chat/input")
    def chat_input(workspace_id: int, request: ChatInputRequest, tab_id: int | None = None):
        return chat_input_payload(workspace_id, request.text, tab_id=tab_id)

    @app.post("/api/workspaces/{workspace_id}/chat/stop")
    def stop_chat(workspace_id: int, tab_id: int | None = None):
        return stop_chat_payload(workspace_id, tab_id=tab_id)

    @app.post("/api/workspaces/{workspace_id}/chat/retry")
    def retry_chat(workspace_id: int, request: ChatRetryRequest | None = None, tab_id: int | None = None):
        if request and request.stream:
            return retry_chat_stream_payload(workspace_id, tab_id=tab_id)
        return retry_chat_payload(workspace_id, tab_id=tab_id)

    @app.post("/api/workspaces/{workspace_id}/chat/retry/stream")
    def retry_chat_stream_route(workspace_id: int, tab_id: int | None = None):
        return retry_chat_stream_payload(workspace_id, tab_id=tab_id)

    @app.get("/api/workspaces/{workspace_id}/run/config")
    def detect_run_config(workspace_id: int):
        return detect_run_config_payload(workspace_id)

    @app.get("/api/workspaces/{workspace_id}/run/status")
    def run_status(workspace_id: int):
        return run_status_payload(workspace_id)

    @app.post("/api/workspaces/{workspace_id}/run/start")
    def start_run(workspace_id: int, request: RunStartRequest):
        return start_run_payload(workspace_id, request.command, request.env)

    @app.post("/api/workspaces/{workspace_id}/run/stop")
    def stop_run(workspace_id: int):
        return stop_run_payload(workspace_id)

    @app.get("/api/workspaces/{workspace_id}/run/settings")
    def get_run_settings(workspace_id: int):
        return get_run_settings_payload(workspace_id)

    @app.patch("/api/workspaces/{workspace_id}/run/settings")
    def update_run_settings(workspace_id: int, request: UpdateRunSettingsRequest):
        return update_run_settings_payload(workspace_id, request.env)

    return app
