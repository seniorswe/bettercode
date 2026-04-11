import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib import request

from bettercode.i18n import language_runtime_instruction
from bettercode.settings import (
    COST_TIER_ORDER,
    get_auto_model_preference,
    get_local_preprocess_mode,
    get_local_preprocess_model,
    get_max_cost_tier,
)


SELECTOR_MODEL = os.environ.get("BETTERCODE_SELECTOR_MODEL", "qwen2.5-coder:1.5b")
SELECTOR_KEEP_ALIVE = os.environ.get("BETTERCODE_SELECTOR_KEEP_ALIVE", "15m")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MAX_SELECTOR_CONTEXT_CHARS = 2000
MAX_SELECTOR_REQUEST_CHARS = 800
MAX_SELECTOR_HISTORY_MODELS = 4
TOP_CANDIDATE_COUNT = 5
PREPROCESS_RAM_BUDGET_GB = {
    "off": 0.0,
    "tiny": 2.0,
    "small": 5.0,
}
MIN_PREPROCESS_MODEL_GB = 0.95
CURATED_LOCAL_PREPROCESS_MODELS = (
    {
        "id": "qwen2.5-coder:1.5b",
        "label": "Low Mem (1.0 GB)",
        "size_gb": 1.0,
        "description": "Best for the lightest local routing and simple answer-only work.",
    },
    {
        "id": "qwen3:1.7b",
        "label": "Medium Mem (1.4 GB)",
        "size_gb": 1.4,
        "description": "Better instruction following for everyday local preprocessing.",
    },
    {
        "id": "qwen2.5-coder:3b",
        "label": "High Mem (1.9 GB)",
        "size_gb": 1.9,
        "description": "Balanced local code planning for harder implementation requests.",
    },
    {
        "id": "qwen3:4b",
        "label": "Extra High Mem (2.5 GB)",
        "size_gb": 2.5,
        "description": "Best overall local planner under the standard memory cap.",
    },
    {
        "id": "qwen2.5-coder:7b",
        "label": "Ludacris Mem (4.7 GB)",
        "size_gb": 4.7,
        "description": "Strongest local code-focused option for the biggest memory budget.",
    },
)
CHEAP_INTENT_MAX_ESTIMATED_TOKENS = 1800
HEURISTIC_CONFIDENCE_HIGH = 8
HEURISTIC_CONFIDENCE_LOW = 3
TEST_RECOMMENDATION = "Add tests covering the behavior changes."
MAX_FOLLOW_UP_RECOMMENDATIONS = 1
MAX_FOLLOW_UP_RECOMMENDATION_LENGTH = 180
LOCAL_EXECUTION_MAX_ESTIMATED_TOKENS = 1400
LOCAL_EXECUTION_ALLOWED_TASK_TYPES = {"general", "conversational", "small_edit", "implementation"}
LOCAL_EXECUTION_REPO_HINTS = (
    "repo", "repository", "workspace", "project", "codebase", "app", "module", "package",
    "file", "files", "folder", "directory", "test", "tests", "git", "commit", "diff",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt",
)
LOCAL_EXECUTION_SELF_CONTAINED_HINTS = (
    "write", "generate", "show", "explain", "summarize", "draft", "example", "snippet",
    "regex", "sql", "query", "command", "function", "class", "algorithm", "convert",
    "what is", "how do i", "why does", "refine", "improve this sentence",
)
OBVIOUS_LOCAL_PROMPT_PREFIXES = (
    "what is",
    "what's",
    "what are",
    "what year",
    "when did",
    "when was",
    "who is",
    "who was",
    "where is",
    "where was",
    "why is",
    "why does",
    "how do i",
    "how does",
    "explain",
    "define",
    "summarize",
    "rewrite",
    "improve this",
    "translate",
    "write me",
    "tell me",
    "give me",
    "calculate",
    "solve",
    "convert",
)
OBVIOUS_LOCAL_DYNAMIC_HINTS = (
    "today",
    "right now",
    "currently",
    "latest",
    "breaking",
    "news",
    "weather",
    "temperature",
    "stock",
    "price",
    "score",
    "schedule",
    "president",
    "ceo",
)
NON_CODE_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less", ".html", ".md", ".txt", ".svg", ".png", ".jpg", ".jpeg",
    ".gif", ".ico", ".json", ".yaml", ".yml", ".toml", ".lock",
}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt", ".rb", ".php", ".cs"}
SUBTASK_STAGE_ORDER = ("inspect", "edit", "validate")
SUBTASK_MODEL_ASSIGNMENT_ORDER = ("edit", "inspect", "validate")
TASK_TYPE_KEYWORDS = {
    "conversational": ("joke", "riddle", "haiku", "fun fact"),
    "architecture": ("architecture", "design", "system design", "plan", "migration", "migrate", "deep", "complex", "tradeoff"),
    "debugging": ("debug", "bug", "broken", "error", "failed", "failing", "regression", "trace", "investigate", "fix"),
    "review": ("review", "audit", "risk", "regression check", "code review"),
    "implementation": ("implement", "build", "create", "add", "update", "wire", "integrate", "refactor"),
    "small_edit": (
        "rename", "wording", "copy", "spacing", "padding", "margin", "align", "label", "placeholder", "typo",
        "color", "font", "border radius", "border", "radius", "import path",
    ),
}


_MANAGED_OLLAMA_PROCESS: subprocess.Popen | None = None
_OLLAMA_STARTUP_LOCK = threading.Lock()
_CURATED_LOCAL_PREPROCESS_MAP = {entry["id"]: entry for entry in CURATED_LOCAL_PREPROCESS_MODELS}


def _ollama_command() -> str | None:
    return shutil.which("ollama")


def _api_request(method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{OLLAMA_HOST}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _ollama_running() -> bool:
    try:
        _api_request("GET", "/api/tags", timeout=1.5)
        return True
    except Exception:
        return False


def _installed_selector_model() -> str | None:
    try:
        payload = _api_request("GET", "/api/tags", timeout=2.0)
    except Exception:
        return None

    names = [model.get("name", "") for model in payload.get("models", [])]
    if SELECTOR_MODEL in names:
        return SELECTOR_MODEL

    prefix = f"{SELECTOR_MODEL}:"
    for name in names:
        if name.startswith(prefix) or name.startswith(SELECTOR_MODEL):
            return name

    return None


def _installed_ollama_models() -> list[dict]:
    try:
        payload = _api_request("GET", "/api/tags", timeout=2.0)
    except Exception:
        return []
    models = payload.get("models", [])
    return models if isinstance(models, list) else []


def _model_size_gb(model_payload: dict) -> float:
    size = model_payload.get("size")
    try:
        return float(size) / (1024 ** 3)
    except Exception:
        return 0.0


def _preprocess_candidate_label(name: str, size_gb: float) -> str:
    rounded = f"{size_gb:.1f} GB" if size_gb > 0 else "unknown size"
    if size_gb <= 1.1:
        tier = "Low Mem"
    elif size_gb <= 1.6:
        tier = "Medium Mem"
    elif size_gb <= 2.2:
        tier = "High Mem"
    elif size_gb <= 3.8:
        tier = "Extra High Mem"
    else:
        tier = "Ludacris Mem"
    return f"{tier} ({rounded})"


def local_preprocess_model_label(model_id: str, mode: str | None = None) -> str:
    for candidate in local_preprocess_candidates(mode):
        if candidate["id"] == model_id:
            return candidate.get("label") or model_id
    curated = _CURATED_LOCAL_PREPROCESS_MAP.get(model_id)
    if curated:
        return curated["label"]
    return model_id


def _supported_local_preprocess_model_name(name: str) -> bool:
    lowered = name.lower()
    return name in _CURATED_LOCAL_PREPROCESS_MAP or "coder" in lowered


def curated_local_preprocess_candidates(mode: str | None = None) -> list[dict]:
    normalized_mode = mode or get_local_preprocess_mode()
    max_gb = PREPROCESS_RAM_BUDGET_GB.get(normalized_mode, 0.0)
    if max_gb <= 0:
        return []
    return [
        {
            "id": entry["id"],
            "label": entry["label"],
            "size_gb": entry["size_gb"],
            "description": entry["description"],
            "installed": False,
            "source": "catalog",
        }
        for entry in CURATED_LOCAL_PREPROCESS_MODELS
        if MIN_PREPROCESS_MODEL_GB <= entry["size_gb"] <= max_gb
    ]


def local_preprocess_candidates(mode: str | None = None) -> list[dict]:
    normalized_mode = mode or get_local_preprocess_mode()
    max_gb = PREPROCESS_RAM_BUDGET_GB.get(normalized_mode, 0.0)
    if max_gb <= 0:
        return []
    installed_models = _installed_ollama_models()
    installed_by_name = {}
    for model in installed_models:
        name = str(model.get("name") or "").strip()
        if not name:
            continue
        installed_by_name[name] = model
    candidates = []
    seen_ids = set()
    for curated in curated_local_preprocess_candidates(normalized_mode):
        installed_payload = installed_by_name.get(curated["id"])
        size_gb = _model_size_gb(installed_payload) if installed_payload else curated["size_gb"]
        candidate = {
            "id": curated["id"],
            "label": curated["label"],
            "size_gb": round(size_gb, 2),
            "description": curated["description"],
            "installed": bool(installed_payload),
            "source": "catalog",
        }
        candidates.append(candidate)
        seen_ids.add(candidate["id"])
    for model in installed_models:
        name = str(model.get("name") or "").strip()
        if not name or name in seen_ids:
            continue
        size_gb = _model_size_gb(model)
        if size_gb < MIN_PREPROCESS_MODEL_GB or size_gb > max_gb:
            continue
        if not _supported_local_preprocess_model_name(name):
            continue
        candidates.append({
            "id": name,
            "label": _preprocess_candidate_label(name, size_gb),
            "size_gb": round(size_gb, 2),
            "description": "Installed local model.",
            "installed": True,
            "source": "installed",
        })
    candidates.sort(key=lambda entry: (not entry["installed"], entry["size_gb"], entry["id"]))
    return candidates


def resolve_local_preprocess_model(mode: str | None = None) -> str | None:
    candidates = local_preprocess_candidates(mode)
    if not candidates:
        return None
    preferred = get_local_preprocess_model()
    if preferred:
        for candidate in candidates:
            if candidate["id"] == preferred and candidate.get("installed"):
                return candidate["id"]
    installed_candidates = [candidate for candidate in candidates if candidate.get("installed")]
    for candidate in installed_candidates:
        lowered = candidate["id"].lower()
        if candidate["id"] in _CURATED_LOCAL_PREPROCESS_MAP or "coder" in lowered:
            return candidate["id"]
    return installed_candidates[0]["id"] if installed_candidates else None


def installable_local_preprocess_model(model_id: str, mode: str | None = None) -> dict | None:
    normalized = str(model_id or "").strip()
    if not normalized:
        return None
    candidates = {entry["id"]: entry for entry in local_preprocess_candidates(mode or "small")}
    candidate = candidates.get(normalized)
    if candidate and candidate.get("source") == "catalog":
        return candidate
    curated = _CURATED_LOCAL_PREPROCESS_MAP.get(normalized)
    if not curated:
        return None
    return {
        "id": curated["id"],
        "label": curated["label"],
        "size_gb": curated["size_gb"],
        "description": curated["description"],
        "installed": False,
        "source": "catalog",
    }


def pull_local_preprocess_model(model_id: str) -> dict:
    candidate = installable_local_preprocess_model(model_id, mode="small")
    if not candidate:
        raise RuntimeError("Unknown local preprocess model.")
    if candidate.get("installed"):
        return candidate
    command = _ollama_command()
    if not command:
        raise RuntimeError("Ollama command not found. Cannot install local preprocess models.")
    result = subprocess.run([command, "pull", candidate["id"]], check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to install local preprocess model '{candidate['id']}'. Run 'ollama pull {candidate['id']}' manually."
        )
    return candidate


def selector_status() -> dict:
    mode = get_local_preprocess_mode()
    command = _ollama_command()
    running = _ollama_running() if command else False
    default_model_name = _installed_selector_model() if running else None
    candidates = local_preprocess_candidates("small") if command else []
    selected_model = resolve_local_preprocess_model(mode if mode != "off" else "small") if running else None
    return {
        "installed": bool(command),
        "running": running,
        "mode": mode,
        "model": default_model_name or SELECTOR_MODEL,
        "selected_model": selected_model or default_model_name or SELECTOR_MODEL,
        "model_ready": bool(selected_model or default_model_name) and mode != "off",
        "available_local_models": candidates,
    }


def _ollama_preexec_fn():
    """Return a preexec_fn that ties Ollama's lifetime to BetterCode's PID on Linux.

    Uses prctl(PR_SET_PDEATHSIG, SIGTERM) so the kernel sends SIGTERM to Ollama
    when BetterCode dies for any reason — including crashes and SIGKILL.
    Returns None on platforms that don't support prctl.
    """
    if sys.platform != "linux":
        return None

    import ctypes
    import signal as _signal

    PR_SET_PDEATHSIG = 1
    sigterm = _signal.SIGTERM

    def _set() -> None:
        try:
            ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, sigterm)
        except Exception:
            pass

    return _set


def ensure_selector_runtime(
    start_if_needed: bool = True,
    warm_model: bool = True,
    startup_timeout: float = 3.0,
) -> dict:
    status = selector_status()
    if not status["installed"]:
        return status

    if not status["running"] and start_if_needed:
        with _OLLAMA_STARTUP_LOCK:
            # Re-check after acquiring lock — another thread may have started it.
            if not _ollama_running():
                command = _ollama_command()
                if command:
                    global _MANAGED_OLLAMA_PROCESS
                    try:
                        _MANAGED_OLLAMA_PROCESS = subprocess.Popen(
                            [command, "serve"],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                            preexec_fn=_ollama_preexec_fn(),
                        )
                    except OSError:
                        pass

        deadline = time.time() + max(0.5, startup_timeout)
        while time.time() < deadline:
            if _ollama_running():
                break
            time.sleep(0.15)

        status = selector_status()

    if warm_model and status["running"] and status["model_ready"]:
        try:
            _api_request(
                "POST",
                "/api/generate",
                {
                    "model": status.get("selected_model") or status["model"],
                    "prompt": "ping",
                    "stream": False,
                    "keep_alive": SELECTOR_KEEP_ALIVE,
                    "options": {"num_predict": 1},
                },
                timeout=20.0,
            )
        except Exception:
            pass

    return selector_status()


def _set_local_model_keep_alive(
    model_id: str | None,
    keep_alive: int | str,
    *,
    startup_timeout: float = 10.0,
) -> dict | None:
    normalized_model = str(model_id or "").strip()
    if not normalized_model:
        return None
    status = ensure_selector_runtime(
        start_if_needed=True,
        warm_model=False,
        startup_timeout=startup_timeout,
    )
    if not status.get("installed"):
        raise RuntimeError("Ollama is not installed.")
    if not status.get("running"):
        raise RuntimeError(f"Ollama is not running at {OLLAMA_HOST}.")
    return _api_request(
        "POST",
        "/api/generate",
        {
            "model": normalized_model,
            "prompt": "",
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"num_predict": 0},
        },
        timeout=20.0,
    )


def unload_local_preprocess_model(model_id: str | None, *, startup_timeout: float = 10.0) -> None:
    try:
        _set_local_model_keep_alive(model_id, 0, startup_timeout=startup_timeout)
    except Exception:
        pass


def warm_local_preprocess_model(model_id: str | None, *, startup_timeout: float = 10.0) -> dict:
    normalized_model = str(model_id or "").strip()
    if not normalized_model:
        raise RuntimeError("No local preprocess model is selected.")
    _set_local_model_keep_alive(
        normalized_model,
        SELECTOR_KEEP_ALIVE,
        startup_timeout=startup_timeout,
    )
    return selector_status()


def apply_local_preprocess_runtime_change(
    previous_model_id: str | None,
    next_mode: str | None,
    next_model_id: str | None,
    *,
    startup_timeout: float = 10.0,
) -> dict:
    normalized_next_mode = str(next_mode or "").strip().lower() or "off"
    normalized_previous_model = str(previous_model_id or "").strip() or None
    normalized_next_model = str(next_model_id or "").strip() or None

    if normalized_next_mode == "off":
        unload_local_preprocess_model(normalized_previous_model, startup_timeout=startup_timeout)
        stop_managed_ollama()
        return selector_status()

    status = require_selector_runtime(
        start_if_needed=True,
        warm_model=False,
        startup_timeout=startup_timeout,
    )
    resolved_next_model = (
        normalized_next_model
        or status.get("selected_model")
        or resolve_local_preprocess_model(normalized_next_mode)
    )
    if not resolved_next_model:
        raise RuntimeError("No local preprocess model is available for the selected mode.")
    if normalized_previous_model and normalized_previous_model != resolved_next_model:
        unload_local_preprocess_model(normalized_previous_model, startup_timeout=startup_timeout)
    return warm_local_preprocess_model(resolved_next_model, startup_timeout=startup_timeout)


def require_selector_runtime(
    start_if_needed: bool = True,
    warm_model: bool = True,
    startup_timeout: float = 10.0,
) -> dict:
    status = ensure_selector_runtime(
        start_if_needed=start_if_needed,
        warm_model=warm_model,
        startup_timeout=startup_timeout,
    )
    if not status["installed"]:
        raise RuntimeError(
            "Auto Model Select requires Ollama, but the 'ollama' command is not installed."
        )
    if not status["running"]:
        raise RuntimeError(
            f"Auto Model Select requires the Ollama service at {OLLAMA_HOST}, but it is not running."
        )
    if status.get("mode") == "off":
        raise RuntimeError("Local preprocess is disabled.")
    if not status["model_ready"]:
        raise RuntimeError(
            "Auto Model Select requires a local preprocess model within the configured RAM budget."
        )
    return status


def install_ollama() -> None:
    """Install Ollama using the platform's recommended method. Raises RuntimeError on failure."""
    if sys.platform == "win32":
        raise RuntimeError(
            "Ollama is not installed. Download and run the installer from https://ollama.com/download, "
            "then restart BetterCode."
        )

    if sys.platform == "darwin":
        brew = shutil.which("brew")
        if brew:
            result = subprocess.run([brew, "install", "ollama"], check=False)
            if result.returncode == 0:
                return
        raise RuntimeError(
            "Ollama is not installed. Install it with 'brew install ollama' or download from "
            "https://ollama.com/download, then restart BetterCode."
        )

    # Linux — official install script
    result = subprocess.run(
        ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to install Ollama automatically. Visit https://ollama.com/download to install "
            "manually, then restart BetterCode."
        )


def pull_selector_model() -> None:
    """Pull the selector model via `ollama pull`. Output streams directly to the terminal."""
    command = _ollama_command()
    if not command:
        raise RuntimeError("Ollama command not found. Cannot pull selector model.")
    result = subprocess.run([command, "pull", SELECTOR_MODEL], check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to pull selector model '{SELECTOR_MODEL}'. "
            f"Run 'ollama pull {SELECTOR_MODEL}' manually, then restart BetterCode."
        )


def bootstrap_selector_runtime(log_fn=None) -> None:
    """Ensure Ollama is installed, running, and the selector model is ready.

    Installs Ollama if missing, starts the service, and pulls the model when needed.
    ``log_fn`` is an optional callable(str) for progress messages.
    Raises RuntimeError if any step cannot be completed.
    """
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    status = selector_status()

    if not status["installed"]:
        _log("Ollama is not installed. Installing now (this may take a moment)...")
        install_ollama()
        status = selector_status()
        if not status["installed"]:
            raise RuntimeError(
                "Ollama installation appeared to succeed but the 'ollama' command is still not found. "
                "Open a new terminal and restart BetterCode."
            )
        _log("Ollama installed successfully.")

    if not status["running"]:
        _log("Starting Ollama service...")

    status = ensure_selector_runtime(start_if_needed=True, warm_model=False, startup_timeout=15.0)

    if not status["running"]:
        raise RuntimeError(
            f"Ollama is installed but the service did not start at {OLLAMA_HOST}. "
            "Try running 'ollama serve' in a terminal, then restart BetterCode."
        )

    if not _installed_selector_model():
        _log(f"Pulling selector model '{SELECTOR_MODEL}' (this may take a few minutes on first run)...")
        pull_selector_model()
        if not _installed_selector_model():
            raise RuntimeError(
                f"Failed to make selector model '{SELECTOR_MODEL}' ready after pulling. "
                f"Run 'ollama pull {SELECTOR_MODEL}' manually, then restart BetterCode."
            )
        _log(f"Model '{SELECTOR_MODEL}' is ready.")


def stop_managed_ollama() -> None:
    """Stop the Ollama process that BetterCode started, if any. Skips if Ollama was already running."""
    global _MANAGED_OLLAMA_PROCESS
    process = _MANAGED_OLLAMA_PROCESS
    if process is None:
        return
    _MANAGED_OLLAMA_PROCESS = None
    if process.poll() is not None:
        return
    try:
        if sys.platform != "win32":
            import signal as _signal
            try:
                import os as _os
                pgid = _os.getpgid(process.pid)
                _os.killpg(pgid, _signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _os.killpg(pgid, _signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass


def _model_profile(model_id: str) -> dict:
    label = model_id.split("/", 1)[1] if "/" in model_id else model_id
    lower = model_id.lower()

    if any(token in lower for token in ("@low", "mini", "flash", "haiku")):
        cost_tier = "low"
        speed_tier = "high"
        capability_tier = "medium"
    elif any(token in lower for token in ("@high", "@xhigh", "opus", "pro")):
        cost_tier = "high"
        speed_tier = "medium"
        capability_tier = "very_high"
    else:
        cost_tier = "medium"
        speed_tier = "medium"
        capability_tier = "high"

    return {
        "id": model_id,
        "label": label,
        "provider": model_id.split("/", 1)[0] if "/" in model_id else "",
        "runtime": model_id.split("/", 1)[0] if "/" in model_id else "",
        "family": label.split("/", 1)[0],
        "reasoning_effort": model_id.rsplit("@", 1)[1] if "@" in model_id else None,
        "default_reasoning_effort": None,
        "supported_reasoning_efforts": [],
        "context_window": None,
        "output_token_limit": None,
        "tool_support": [],
        "multimodal": False,
        "cost_tier": cost_tier,
        "speed_tier": speed_tier,
        "capability_tier": capability_tier,
        "stability": "stable",
        "suggested_uses": [],
        "source": "heuristic",
    }


def _normalize_model_entries(available_models: list[str] | list[dict]) -> list[dict]:
    entries = []
    for model in available_models:
        if isinstance(model, str):
            entries.append(_model_profile(model))
            continue

        model_id = model.get("id")
        if not model_id or model_id == "smart":
            continue

        entry = {
            "id": model_id,
            "label": model.get("label") or model_id,
            "provider": model.get("provider") or model_id.split("/", 1)[0],
            "runtime": model.get("runtime") or model_id.split("/", 1)[0],
            "family": model.get("family") or model_id.split("/", 1)[-1],
            "reasoning_effort": model.get("reasoning_effort"),
            "default_reasoning_effort": model.get("default_reasoning_effort"),
            "supported_reasoning_efforts": model.get("supported_reasoning_efforts") or [],
            "context_window": model.get("context_window"),
            "output_token_limit": model.get("output_token_limit"),
            "tool_support": model.get("tool_support") or [],
            "multimodal": bool(model.get("multimodal")),
            "cost_tier": model.get("cost_tier") or "medium",
            "speed_tier": model.get("speed_tier") or "medium",
            "capability_tier": model.get("capability_tier") or "high",
            "stability": model.get("stability") or "stable",
            "suggested_uses": model.get("suggested_uses") or [],
            "source": model.get("source") or "heuristic",
        }
        entries.append(entry)
    return entries


def _infer_subtask_stage(title: str, detail: str = "") -> str:
    text = f"{title}\n{detail}".lower()
    if any(token in text for token in ("test", "validate", "verify", "review", "check", "audit", "regression", "qa", "confirm")):
        return "validate"
    if any(token in text for token in ("implement", "edit", "update", "write", "patch", "fix", "refactor", "create", "build", "wire")):
        return "edit"
    return "inspect"


def _planning_candidates(model_entries: list[dict]) -> list[dict]:
    candidates = []
    seen_ids = set()
    for entry in model_entries:
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id or entry_id in seen_ids or "@" in entry_id:
            continue
        seen_ids.add(entry_id)
        candidates.append(
            {
                "id": entry_id,
                "label": entry.get("label") or entry_id,
                "provider": entry.get("provider") or entry.get("runtime") or "",
                "runtime": entry.get("runtime") or entry.get("provider") or "",
                "cost_tier": entry.get("cost_tier") or "medium",
                "capability_tier": entry.get("capability_tier") or "high",
                "speed_tier": entry.get("speed_tier") or "medium",
                "context_window": entry.get("context_window"),
                "stability": entry.get("stability") or "stable",
                "suggested_uses": entry.get("suggested_uses") or [],
            }
        )
    return candidates


def _fallback_subtask_outline(task: dict, direct_only: bool = False) -> list[dict]:
    # The local model handles requirements gathering (pre) and validation (post).
    # Only implementation tasks are dispatched to CLI models.
    return [
        {
            "id": "implement",
            "title": "Implement changes",
            "detail": "Apply targeted edits across the necessary files.",
            "depends_on": [],
            "execution": "sync",
            "stage": "edit",
        },
    ]


def _normalize_raw_subtasks(raw_tasks: list[dict], fallback_task: dict) -> list[dict]:
    normalized = []
    used_ids: set[str] = set()
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            continue
        task_id = str(raw.get("id") or "").strip()
        if not task_id or task_id in used_ids:
            continue
        used_ids.add(task_id)
        title = str(raw.get("title") or "").strip() or task_id
        detail = str(raw.get("detail") or "").strip()
        stage = str(raw.get("stage") or "").strip().lower()
        if stage not in SUBTASK_STAGE_ORDER:
            stage = _infer_subtask_stage(title, detail)
        execution = str(raw.get("execution") or "").strip().lower()
        normalized.append(
            {
                "id": task_id,
                "title": title,
                "detail": detail,
                "depends_on": [str(value).strip() for value in (raw.get("depends_on") or []) if str(value).strip()],
                "execution": "async" if execution == "async" else "sync",
                "stage": stage,
                "requested_model_id": str(raw.get("model_id") or "").strip(),
            }
        )
    return normalized or _fallback_subtask_outline(fallback_task)


def _normalize_subtask_dependencies(tasks: list[dict]) -> list[dict]:
    known_ids = [task["id"] for task in tasks if task.get("id")]
    known_id_set = set(known_ids)
    position = {task_id: index for index, task_id in enumerate(known_ids)}
    for index, task in enumerate(tasks):
        valid_deps = []
        for dep_id in task.get("depends_on") or []:
            if dep_id == task["id"] or dep_id not in known_id_set:
                continue
            if position.get(dep_id, index) >= index:
                continue
            if dep_id not in valid_deps:
                valid_deps.append(dep_id)

        if not valid_deps:
            prior_tasks = tasks[:index]
            prior_inspect = [entry["id"] for entry in prior_tasks if entry.get("stage") == "inspect"]
            prior_edit = [entry["id"] for entry in prior_tasks if entry.get("stage") == "edit"]
            if task.get("stage") == "edit" and prior_inspect:
                valid_deps = prior_inspect
            elif task.get("stage") == "validate":
                valid_deps = prior_edit or prior_inspect

        task["depends_on"] = valid_deps
        if task.get("stage") in {"inspect", "validate"} and not valid_deps and task.get("execution") != "async":
            task["execution"] = "async"
    return tasks


def _analyze_subtask(task: dict, request_task: dict) -> dict:
    subtask = _analyze_task(
        task.get("title") or task.get("id") or "",
        task.get("detail") or "",
    )
    request_type = request_task.get("task_type") or "general"
    request_complexity = max(0, int(request_task.get("complexity") or 0))
    stage = task.get("stage") or "inspect"

    if stage == "edit":
        subtask["task_type"] = "small_edit" if request_type == "small_edit" else "implementation"
        subtask["complexity"] = max(1, request_complexity)
        subtask["multi_file"] = bool(request_task.get("multi_file"))
        subtask["needs_deep_reasoning"] = bool(request_task.get("needs_deep_reasoning"))
    elif stage == "validate":
        if request_type in {"review", "architecture"}:
            subtask["task_type"] = "review"
        elif request_type == "debugging":
            subtask["task_type"] = "debugging"
        else:
            subtask["task_type"] = "general"
        subtask["complexity"] = max(1, request_complexity - 1 if request_complexity > 1 else 1)
    else:
        subtask["task_type"] = request_type if request_type in {"review", "architecture", "debugging"} else "general"
        subtask["complexity"] = max(0, request_complexity - 1)

    subtask["estimated_tokens"] = max(
        int(subtask.get("estimated_tokens") or 0),
        min(2200, max(180, int(request_task.get("estimated_tokens") or 0) // 2)),
    )
    return subtask


def _subtask_model_stage_bonus(model: dict, stage: str) -> int:
    cost = _score_tier(model.get("cost_tier"), ("low", "medium", "high"))
    speed = _score_tier(model.get("speed_tier"), ("low", "medium", "high"))
    capability = _score_tier(model.get("capability_tier"), ("medium", "high", "very_high"))
    effort = _effort_score(model)
    uses = " ".join(model.get("suggested_uses") or []).lower()
    score = 0

    if stage == "inspect":
        score += speed * 7 + (2 - cost) * 6 - capability * 2 - effort * 2
        if any(token in uses for token in ("low-latency", "high-volume", "quick")):
            score += 4
    elif stage == "edit":
        score += capability * 6 + effort * 3 - max(0, cost - 1) * 2
        if any(token in uses for token in ("general coding", "standard implementation", "multi-file")):
            score += 4
    elif stage == "validate":
        score += capability * 6 + effort * 4 + speed * 2
        if any(token in uses for token in ("review", "debugging", "deep reasoning")):
            score += 4

    return score


def _rank_models_for_subtask(
    candidates: list[dict],
    task: dict,
    request_task: dict,
    routing_history: dict | None,
    model_usage: dict[str, int],
    provider_usage: dict[str, int],
) -> list[tuple[int, dict]]:
    analysis = _analyze_subtask(task, request_task)
    stage = task.get("stage") or "inspect"
    scored: list[tuple[int, dict]] = []
    for candidate in candidates:
        score = _score_model_for_task(candidate, analysis, routing_history)
        score += _subtask_model_stage_bonus(candidate, stage)
        candidate_id = str(candidate.get("id") or "")
        provider = str(candidate.get("provider") or candidate.get("runtime") or "")
        if model_usage.get(candidate_id):
            score -= (1 if stage == "edit" else 4) * model_usage[candidate_id]
        if provider and provider_usage.get(provider):
            score -= (0 if stage == "edit" else 2) * provider_usage[provider]
        scored.append((score, candidate))
    scored.sort(key=lambda item: (item[0], str(item[1].get("label") or item[1].get("id") or "")), reverse=True)
    return scored


def _subtask_model_selection_reason(task: dict, chosen_entry: dict | None, request_task: dict) -> str:
    analysis = _analyze_subtask(task, request_task)
    stage = task.get("stage") or "inspect"
    cost_tier = str((chosen_entry or {}).get("cost_tier") or "medium").lower()
    speed_tier = str((chosen_entry or {}).get("speed_tier") or "medium").lower()
    capability_tier = str((chosen_entry or {}).get("capability_tier") or "high").lower()

    if stage == "inspect":
        subject = "This is a read-heavy inspection step"
        if speed_tier == "high" and cost_tier == "low":
            fit = "a faster lower-cost scan model fit best"
        elif speed_tier == "high":
            fit = "a faster scan model fit best"
        elif cost_tier == "low":
            fit = "a lower-cost scan model fit best"
        else:
            fit = "a balanced scan model fit best"
        return f"{subject}, so {fit}."

    if stage == "edit":
        subject = "This is the main code-writing step"
        if analysis.get("multi_file") or analysis.get("needs_deep_reasoning") or capability_tier == "very_high":
            fit = "BetterCode kept a stronger implementation model on it"
        elif capability_tier == "high":
            fit = "BetterCode kept a balanced implementation model on it"
        else:
            fit = "a lighter implementation model was enough"
        return f"{subject}, so {fit}."

    subject = "This is a validation and review step"
    if analysis.get("task_type") in {"review", "debugging"} or analysis.get("needs_deep_reasoning") or capability_tier == "very_high":
        fit = "BetterCode preferred a stronger checking model here"
    elif capability_tier == "high":
        fit = "BetterCode preferred a balanced checking model here"
    else:
        fit = "a lighter validation model was enough"
    return f"{subject}, so {fit}."


def _assign_subtask_models(tasks: list[dict], candidates: list[dict], request_task: dict, routing_history: dict | None) -> list[dict]:
    if not candidates:
        for task in tasks:
            stage_label = task.get("stage", "inspect").title()
            task["model_id"] = ""
            task["model_label"] = ""
            task["track_key"] = f"stage:{task.get('stage') or 'inspect'}"
            task["track_label"] = f"{stage_label} Track"
            task["track_kind"] = "stage"
            task["selection_reason"] = _subtask_model_selection_reason(task, None, request_task)
            task["parallel_group"] = (
                f"{task.get('stage') or 'inspect'}:{'-'.join(task.get('depends_on') or []) or 'root'}"
                if task.get("execution") == "async"
                else ""
            )
        return tasks

    candidate_map = {entry["id"]: entry for entry in candidates if entry.get("id")}
    model_usage: dict[str, int] = {}
    provider_usage: dict[str, int] = {}

    def _assignment_sort_key(task: dict) -> tuple[int, int, str]:
        stage = task.get("stage") or "inspect"
        try:
            stage_index = SUBTASK_MODEL_ASSIGNMENT_ORDER.index(stage)
        except ValueError:
            stage_index = len(SUBTASK_MODEL_ASSIGNMENT_ORDER)
        return (stage_index, len(task.get("depends_on") or []), task.get("id") or "")

    for task in sorted(tasks, key=_assignment_sort_key):
        ranked = _rank_models_for_subtask(
            candidates,
            task,
            request_task,
            routing_history,
            model_usage,
            provider_usage,
        )
        requested_model_id = str(task.pop("requested_model_id", "") or "").strip()
        chosen_entry = ranked[0][1] if ranked else None
        if requested_model_id in candidate_map and ranked:
            ranked_by_id = {entry["id"]: score for score, entry in ranked}
            top_score = ranked[0][0]
            requested_score = ranked_by_id.get(requested_model_id)
            if requested_score is not None and top_score - requested_score <= 4:
                chosen_entry = candidate_map[requested_model_id]
        if chosen_entry is None:
            chosen_entry = candidate_map.get(requested_model_id)

        chosen_model_id = str((chosen_entry or {}).get("id") or "")
        chosen_label = str((chosen_entry or {}).get("label") or chosen_model_id or "").strip()
        provider = str((chosen_entry or {}).get("provider") or (chosen_entry or {}).get("runtime") or "").strip()
        if chosen_model_id:
            model_usage[chosen_model_id] = model_usage.get(chosen_model_id, 0) + 1
        if provider:
            provider_usage[provider] = provider_usage.get(provider, 0) + 1

        task["model_id"] = chosen_model_id
        task["model_label"] = chosen_label
        task["track_key"] = f"model:{chosen_model_id}" if chosen_model_id else f"stage:{task.get('stage') or 'inspect'}"
        task["track_label"] = chosen_label or f"{(task.get('stage') or 'inspect').title()} Track"
        task["track_kind"] = "model" if chosen_model_id else "stage"
        task["selection_reason"] = _subtask_model_selection_reason(task, chosen_entry, request_task)
        task["parallel_group"] = (
            f"{task.get('stage') or 'inspect'}:{'-'.join(task.get('depends_on') or []) or 'root'}"
            if task.get("execution") == "async"
            else ""
        )
    return tasks


def _finalize_subtask_plan(
    raw_tasks: list[dict],
    available_models: list[str] | list[dict],
    request_task: dict,
    routing_history: dict | None = None,
) -> list[dict]:
    model_entries = _normalize_model_entries(available_models)
    candidates = _planning_candidates(model_entries)
    normalized = _normalize_raw_subtasks(raw_tasks, request_task)
    normalized = _normalize_subtask_dependencies(normalized)
    return _assign_subtask_models(normalized, candidates, request_task, routing_history)


def _task_complexity_score(prompt_text: str, workspace_context: str = "") -> int:
    prompt = prompt_text.lower()
    context = workspace_context.lower()
    combined = f"{prompt}\n{context}"
    score = 0

    if len(prompt_text.strip()) > 280:
        score += 1
    # High-signal complexity keywords — search both prompt and context
    if any(word in prompt for word in ("architecture", "migrate", "deep", "complex", "investigate", "debug", "refactor", "design", "review", "trace", "regression", "production")):
        score += 2
    if any(word in prompt for word in ("error", "failed", "failing", "bug", "issue", "broken", "fix")):
        score += 2
    # File extension mentions only count from the explicit prompt, not the workspace
    # context (every code project workspace mentions .py/.js, inflating complexity).
    # Structured "changed files:" header is a reliable signal regardless of source.
    if "changed files:" in combined or any(word in prompt for word in (".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java")):
        score += 1
    if any(word in combined for word in ("attachments:", "recent history:", "context summary:")):
        score += 1
    if any(word in prompt for word in ("multi-step", "multiple files", "large", "big", "across the codebase")):
        score += 2

    return score


def _estimate_context_tokens(prompt_text: str, workspace_context: str = "") -> int:
    combined = f"{prompt_text}\n{workspace_context}".strip()
    if not combined:
        return 0
    return max(1, len(combined) // 4)


def _classify_task_type(prompt_text: str, workspace_context: str = "") -> str:
    combined = prompt_text.lower()
    for task_type in ("conversational", "small_edit", "architecture", "debugging", "review", "implementation"):
        if any(keyword in combined for keyword in TASK_TYPE_KEYWORDS[task_type]):
            return task_type
    return "general"


def _trivial_local_edit_request(prompt_text: str, task: dict) -> bool:
    prompt = " ".join((prompt_text or "").strip().lower().split())
    if task.get("task_type") != "small_edit":
        return False
    if task.get("multi_file"):
        return False
    if len(prompt) > 600:
        return False
    if not any(token in prompt for token in ("change", "rename", "fix", "update")):
        return False
    return any(token in prompt for token in (
        "color", "font", "border", "radius", "spacing", "padding", "margin",
        "align", "label", "placeholder", "typo", "css class", "import path",
    ))


def _analyze_task(prompt_text: str, workspace_context: str = "") -> dict:
    combined = f"{prompt_text}\n{workspace_context}".lower()
    estimated_tokens = _estimate_context_tokens(prompt_text, workspace_context)
    task_type = _classify_task_type(prompt_text, workspace_context)
    complexity = _task_complexity_score(prompt_text, workspace_context)
    multi_file = any(token in combined for token in ("multiple files", "multi-file", "across the codebase", "changed files:")) or combined.count(".py") + combined.count(".js") + combined.count(".ts") >= 2
    has_recent_history = "recent history:" in combined or "context summary:" in combined
    has_attachments = "attachments:" in combined
    needs_deep_reasoning = (task_type in {"architecture", "debugging", "review"} and complexity >= 2) or estimated_tokens > 6000
    return {
        "task_type": task_type,
        "complexity": complexity,
        "estimated_tokens": estimated_tokens,
        "multi_file": multi_file,
        "has_recent_history": has_recent_history,
        "has_attachments": has_attachments,
        "needs_deep_reasoning": needs_deep_reasoning,
    }


def analyze_routing_task(prompt_text: str, workspace_context: str = "") -> dict:
    return _analyze_task(prompt_text, workspace_context)


def _self_contained_local_request(prompt_text: str, task: dict) -> bool:
    prompt = (prompt_text or "").lower()
    if task.get("task_type") not in LOCAL_EXECUTION_ALLOWED_TASK_TYPES:
        return False
    if int(task.get("complexity") or 0) > 1:
        return False
    if int(task.get("estimated_tokens") or 0) > LOCAL_EXECUTION_MAX_ESTIMATED_TOKENS:
        return False
    if task.get("multi_file") or task.get("has_attachments") or task.get("has_recent_history") or task.get("needs_deep_reasoning"):
        return False
    if any(token in prompt for token in LOCAL_EXECUTION_REPO_HINTS):
        return False
    if task.get("task_type") == "implementation":
        return any(token in prompt for token in LOCAL_EXECUTION_SELF_CONTAINED_HINTS)
    return True


_MATH_PREFIXES: tuple[str, ...] = (
    "whatis", "whatsequal", "whats", "compute", "calculate",
    "evaluate", "eval", "solve", "simplify",
)

def _looks_like_simple_math(prompt_text: str) -> bool:
    compact = re.sub(r"\s+", "", (prompt_text or "").lower())
    if not compact:
        return False
    compact = compact.rstrip("=?")
    for prefix in _MATH_PREFIXES:
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break
    return bool(compact) and bool(re.fullmatch(r"[0-9().+\-*/^%]+", compact))


def _obvious_local_answer_request(prompt_text: str, task: dict) -> bool:
    prompt = " ".join((prompt_text or "").strip().lower().split())
    if not prompt:
        return False
    if not _self_contained_local_request(prompt_text, task):
        return False
    if any(token in prompt for token in OBVIOUS_LOCAL_DYNAMIC_HINTS):
        return False
    if _looks_like_simple_math(prompt):
        return True
    if any(prompt.startswith(prefix) for prefix in OBVIOUS_LOCAL_PROMPT_PREFIXES):
        return True
    if any(token in prompt for token in ("joke", "riddle", "haiku")) and len(prompt) <= 120:
        return True
    # Short general questions with no complexity are trivially self-contained.
    if task.get("task_type") == "general" and int(task.get("complexity") or 0) == 0 and len(prompt) <= 120 and prompt.endswith("?"):
        return True
    return False


def _score_tier(value: str | None, tiers: tuple[str, ...]) -> int:
    try:
        return tiers.index(value or "")
    except ValueError:
        return max(0, len(tiers) // 2)


def _apply_cost_cap(model_entries: list[dict]) -> tuple[list[dict], str | None, bool]:
    max_cost_tier = get_max_cost_tier()
    if not max_cost_tier:
        return model_entries, None, False
    cap_value = _score_tier(max_cost_tier, COST_TIER_ORDER)
    capped = [
        entry
        for entry in model_entries
        if _score_tier(entry.get("cost_tier"), COST_TIER_ORDER) <= cap_value
    ]
    if capped:
        return capped, max_cost_tier, False
    return model_entries, max_cost_tier, True


def _apply_cost_cap_note(selection: dict, max_cost_tier: str | None, cap_exceeded: bool) -> dict:
    if not cap_exceeded or not max_cost_tier:
        return selection
    note = f" Max cost tier '{max_cost_tier}' could not be enforced; no eligible models were available."
    reasoning = (selection.get("reasoning") or "").strip()
    selection["reasoning"] = f"{reasoning}{note}".strip() if reasoning else note.strip()
    selection["cost_cap_exceeded"] = True
    return selection


def _task_fit_bonus(model: dict, task_type: str) -> int:
    uses = " ".join(model.get("suggested_uses") or []).lower()
    cost = _score_tier(model.get("cost_tier"), ("low", "medium", "high"))
    speed = _score_tier(model.get("speed_tier"), ("low", "medium", "high"))
    capability = _score_tier(model.get("capability_tier"), ("medium", "high", "very_high"))

    if task_type == "conversational":
        if cost == 0 and speed == 2:
            return 8
        if capability == 2:
            return -6
        return 3

    if task_type == "small_edit":
        if any(token in uses for token in ("small edits", "quick", "fast-path")):
            return 8
        if cost == 0 and speed == 2:
            return 6
        if any(token in uses for token in ("architecture", "deep reasoning", "complex")):
            return -6
        if capability == 2:
            return -4
        return 2

    if task_type == "implementation":
        if any(token in uses for token in ("general coding", "standard implementation", "balanced")):
            return 7
        if capability >= 1 and cost <= 1:
            return 5
        if any(token in uses for token in ("cheap fast-path", "small edits")):
            return -2
        return 3

    if task_type == "debugging":
        if any(token in uses for token in ("debugging", "review", "multi-file", "deep reasoning")):
            return 8
        if capability == 2:
            return 6
        return 2

    if task_type == "review":
        if any(token in uses for token in ("review", "deep reasoning")):
            return 7
        if capability == 2:
            return 5
        return 2

    if task_type == "architecture":
        if any(token in uses for token in ("architecture", "deep reasoning", "complex")):
            return 9
        if capability == 2:
            return 7
        return 1

    return 0


def _task_profile_bonus(model: dict, task: dict) -> int:
    task_type = task["task_type"]
    capability = _score_tier(model.get("capability_tier"), ("medium", "high", "very_high"))
    effort = _effort_score(model)
    cost = _score_tier(model.get("cost_tier"), ("low", "medium", "high"))
    speed = _score_tier(model.get("speed_tier"), ("low", "medium", "high"))

    if task_type == "conversational":
        return speed * 4 - capability * 3 - effort * 2 - cost * 3

    if task_type == "review":
        bonus = capability * 8 + effort * 4
        if capability == 0:
            bonus -= 10
        if cost == 0:
            bonus -= 2
        return bonus

    if task_type == "architecture":
        bonus = capability * 10 + effort * 5
        if capability <= 1:
            bonus -= 8
        if speed == 0:
            bonus -= 2
        return bonus

    if task_type == "debugging":
        bonus = capability * 6 + effort * 4
        if capability == 0:
            bonus -= 8
        if cost == 0 and effort == 0:
            bonus -= 4
        return bonus

    if task_type == "implementation":
        return capability * 2 + effort - max(0, cost - 1) * 2

    if task_type == "small_edit":
        return speed * 3 - capability * 2 - effort * 2 - cost * 2

    return 0


def _context_fit_bonus(model: dict, estimated_tokens: int) -> int:
    context_window = int(model.get("context_window") or 0)
    if estimated_tokens <= 0 or context_window <= 0:
        return 0
    if context_window < estimated_tokens:
        return -40
    if context_window < estimated_tokens * 2:
        return -8
    if context_window > estimated_tokens * 8:
        return 4
    return 1


def _stability_bonus(model: dict, complexity: int) -> int:
    stability = str(model.get("stability") or "stable").lower()
    if stability == "stable":
        return 4
    if stability == "preview":
        return -8 if complexity >= 1 else -4
    if stability == "deprecated":
        return -50
    return 0


def _history_bonus(model: dict, task: dict, routing_history: dict | None) -> int:
    if not routing_history:
        return 0

    model_id = model["id"]
    task_type = task["task_type"]
    workspace_stats = ((routing_history.get("workspace") or {}).get("by_model") or {}).get(model_id) or {}
    global_stats = ((routing_history.get("global") or {}).get("by_model") or {}).get(model_id) or {}
    stats = workspace_stats or global_stats
    if not stats:
        return 0

    task_stats = (stats.get("task_types") or {}).get(task_type) or {}
    attempts = int(task_stats.get("attempts") or stats.get("attempts") or 0)
    successes = int(task_stats.get("successes") or stats.get("successes") or 0)
    if attempts < 2:
        return 0

    # Item 11: weight success rate by average files changed per successful turn.
    # Models that succeed on real multi-file work score higher than those that
    # only win on trivial one-liners.
    changed_files_total = int(stats.get("changed_files_total") or 0)
    avg_impact = changed_files_total / max(1, successes) if successes > 0 else 0
    impact_weight = min(2.0, 1.0 + avg_impact / 4.0)

    success_rate = successes / max(1, attempts)
    weighted_rate = success_rate * impact_weight

    if weighted_rate >= 1.6:
        return 10
    if weighted_rate >= 0.8:
        return 8
    if weighted_rate >= 0.65:
        return 4
    if success_rate <= 0.35:
        return -8
    if success_rate <= 0.5:
        return -4
    return 0


def _effort_score(model: dict) -> int:
    """Return the effort tier index for scoring purposes.

    Models with no effort specified are treated as "medium" (index 1) — a neutral
    baseline — rather than the _score_tier fallback (index 2 = "high") which would
    unfairly penalise base models on simple tasks vs. explicitly-labelled @medium variants.
    """
    effort_value = model.get("reasoning_effort") or model.get("default_reasoning_effort")
    return _score_tier(effort_value, ("low", "medium", "high", "xhigh")) if effort_value else 1


def _preference_bonus(model: dict, preference: str) -> int:
    cost = _score_tier(model.get("cost_tier"), ("low", "medium", "high"))
    speed = _score_tier(model.get("speed_tier"), ("low", "medium", "high"))
    capability = _score_tier(model.get("capability_tier"), ("medium", "high", "very_high"))
    effort = _effort_score(model)

    if preference == "cheaper":
        return (2 - cost) * 8 + speed * 2 - capability * 2 - effort * 2
    if preference == "faster":
        return speed * 8 + (2 - cost) * 2 - effort * 3 - max(0, capability - 1) * 2
    if preference == "smarter":
        return capability * 12 + effort * 7 - cost * 1 - max(0, 1 - speed) * 1
    return 0


def _score_model_for_task(model: dict, task: dict, routing_history: dict | None = None) -> int:
    complexity = task["complexity"]
    task_type = task["task_type"]
    preference = get_auto_model_preference()
    cost = _score_tier(model.get("cost_tier"), ("low", "medium", "high"))
    speed = _score_tier(model.get("speed_tier"), ("low", "medium", "high"))
    capability = _score_tier(model.get("capability_tier"), ("medium", "high", "very_high"))
    effort = _effort_score(model)
    cost_over_medium = max(0, cost - 1)
    effort_over_medium = max(0, effort - 1)
    score = 0

    if complexity <= 0:
        # Trivial tasks — minimise cost, prefer fast, don't over-engineer
        score += 30
        score -= abs(cost - 0) * 8
        score -= abs(capability - 0) * 5
        score += speed * 4
        score -= effort * 3
    elif complexity <= 2:
        # Simple-to-moderate tasks — medium cost is ideal
        preferred_capability = 2 if task_type in {"review", "architecture"} and task["needs_deep_reasoning"] else 1
        score += 40
        score -= abs(cost - 1) * 7
        score -= cost_over_medium * 6
        score -= abs(capability - preferred_capability) * (4 if preferred_capability == 2 else 6)
        score += speed * 2
        score -= effort_over_medium * 6
    elif complexity <= 3:
        # Standard complex tasks — capability matters, but don't blindly escalate cost
        preferred_capability = 2 if task_type in {"review", "architecture", "debugging"} or task["needs_deep_reasoning"] else 1
        score += 46
        score -= abs(cost - 1) * 3
        score -= cost_over_medium * 4
        score -= abs(capability - preferred_capability) * (4 if preferred_capability == 2 else 7)
        score += effort * 2
        score -= effort_over_medium * 2
        score -= max(0, 1 - speed) * 1
    else:
        # Highly complex tasks — escalate to the best available model
        score += 50
        score -= abs(cost - 2) * 4
        score -= abs(capability - 2) * 8
        score += effort * 3
        score -= max(0, 1 - speed) * 2

    if task["multi_file"]:
        score += capability * 3
    if task["needs_deep_reasoning"]:
        score += effort * 4
        score += capability * 3
    if task["has_recent_history"] or task["has_attachments"]:
        score += 2
    if preference == "cheaper" and complexity <= 2 and task_type in {"general", "small_edit", "implementation"}:
        score -= cost * 12

    score += _task_fit_bonus(model, task["task_type"])
    score += _task_profile_bonus(model, task)
    score += _context_fit_bonus(model, task["estimated_tokens"])
    score += _stability_bonus(model, complexity)
    score += _history_bonus(model, task, routing_history)
    score += _preference_bonus(model, preference)
    return score


ROUTING_FEW_SHOTS = (
    "Examples of correct routing decisions:\n"
    "- small_edit, complexity 0, one CSS file → low cost_tier model; reason: trivial visual change, no logic involved\n"
    "- small_edit, complexity 1, rename a variable, one file → low cost_tier model; reason: mechanical edit, no reasoning needed\n"
    "- implementation, complexity 1, add a helper function → medium cost_tier model; reason: simple addition, medium tier is sufficient\n"
    "- implementation, complexity 2, two .py files → medium cost_tier model; reason: standard coding, balanced tier fits\n"
    "- debugging, complexity 2, fix a failing unit test → medium cost_tier model; reason: contained fix, high tier not needed\n"
    "- debugging, complexity 4, error in logs, 3 changed files → high capability_tier model; reason: root-cause tracing needs stronger reasoning\n"
    "- architecture, complexity 5, migration plan, multi-file → high capability_tier model; reason: design decisions require deep reasoning\n"
    "- review, complexity 3, pr diff attached → high capability_tier model; reason: audit quality matters more than speed\n"
)


def _trim_context(workspace_context: str) -> str:
    if len(workspace_context) <= MAX_SELECTOR_CONTEXT_CHARS:
        return workspace_context
    return workspace_context[:MAX_SELECTOR_CONTEXT_CHARS] + "…[truncated]"


def _trim_request(prompt_text: str) -> str:
    if len(prompt_text) <= MAX_SELECTOR_REQUEST_CHARS:
        return prompt_text
    return prompt_text[:MAX_SELECTOR_REQUEST_CHARS] + "…[truncated]"


def _trim_history(routing_history: dict | None) -> dict:
    if not routing_history:
        return {}
    result = {}
    for scope in ("workspace", "global"):
        section = (routing_history.get(scope) or {})
        by_model = section.get("by_model") or {}
        if not by_model:
            result[scope] = section
            continue
        top_models = sorted(
            by_model.items(),
            key=lambda kv: int((kv[1] or {}).get("attempts") or 0),
            reverse=True,
        )[:MAX_SELECTOR_HISTORY_MODELS]
        result[scope] = {
            "by_model": {k: v for k, v in top_models},
            "sample_size": section.get("sample_size", 0),
        }
    return result


def _top_candidates(model_entries: list[dict], task: dict, routing_history: dict | None) -> list[dict]:
    # Exclude effort variants — the local router selects the base model; effort is a system-level choice.
    base_entries = [m for m in model_entries if "@" not in str(m.get("id") or "")]
    scored = sorted(
        base_entries or model_entries,
        key=lambda m: _score_model_for_task(m, task, routing_history),
        reverse=True,
    )
    diversified = []
    seen_ids = set()
    seen_providers = set()
    for entry in scored:
        provider = str(entry.get("provider") or entry.get("runtime") or "")
        if provider and provider in seen_providers:
            continue
        diversified.append(entry)
        seen_ids.add(entry["id"])
        if provider:
            seen_providers.add(provider)
        if len(diversified) >= TOP_CANDIDATE_COUNT:
            break
    for entry in scored:
        if entry["id"] in seen_ids:
            continue
        diversified.append(entry)
        if len(diversified) >= TOP_CANDIDATE_COUNT:
            break
    return [
        {
            "id": m["id"],
            "label": m["label"],
            "cost_tier": m["cost_tier"],
            "capability_tier": m["capability_tier"],
            "stability": m.get("stability") or "stable",
            "suggested_uses": m.get("suggested_uses") or [],
        }
        for m in diversified[:TOP_CANDIDATE_COUNT]
    ]


def heuristic_confidence(model_entries: list[dict], task: dict, routing_history: dict | None = None) -> int:
    if len(model_entries) <= 1:
        return HEURISTIC_CONFIDENCE_HIGH
    scores = sorted(
        (_score_model_for_task(entry, task, routing_history), entry["id"]) for entry in model_entries
    )
    top_score = scores[-1][0]
    next_score = scores[-2][0]
    return max(0, int(top_score - next_score))


def should_skip_local_preprocessing(task: dict) -> bool:
    if task.get("has_attachments") or task.get("multi_file") or task.get("needs_deep_reasoning"):
        return False
    if int(task.get("estimated_tokens") or 0) > CHEAP_INTENT_MAX_ESTIMATED_TOKENS:
        return False
    return task.get("complexity", 0) <= 1 and task.get("task_type") in {"general", "conversational", "small_edit", "implementation"}


def maybe_select_local_execution(
    prompt_text: str,
    workspace_context: str = "",
    task_analysis: dict | None = None,
    selector_runtime_status: dict | None = None,
) -> dict | None:
    task = task_analysis or _analyze_task(prompt_text, workspace_context)
    if get_local_preprocess_mode() == "off" or not _self_contained_local_request(prompt_text, task):
        return None

    status = selector_runtime_status or ensure_selector_runtime(start_if_needed=True, warm_model=False)
    if not (status.get("running") and status.get("model_ready")):
        return None

    local_model_id = status.get("selected_model") or resolve_local_preprocess_model(status.get("mode"))
    if not local_model_id:
        return None

    if _obvious_local_answer_request(prompt_text, task):
        return {
            "selected_model": f"local/{local_model_id}",
            "selected_model_label": f"{local_preprocess_model_label(local_model_id)} / Local",
            "reasoning": "This is a short self-contained request, so BetterCode can answer it locally.",
            "source": "local_direct",
            "task_analysis": task,
            "confidence": 10,
        }

    assessment_prompt = json.dumps(
        {
            "request": _trim_request(prompt_text),
            "task_analysis": task,
        },
        ensure_ascii=True,
    )
    system_prompt = (
        "You are deciding whether BetterCode should answer this turn directly with the local Ollama model.\n"
        "Approve ONLY when the request is fully self-contained and can be answered correctly without files, tools, repo context, execution, or external CLIs.\n"
        "Reject anything involving codebase edits, debugging a project, tests, file changes, commits, or uncertain context.\n"
        "Return JSON with exactly these keys: use_local (boolean), confidence (integer 0-10), reasoning (string).\n"
    )

    try:
        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": local_model_id,
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": assessment_prompt},
                ],
                "options": {"num_predict": 120, "temperature": 0.0},
            },
            timeout=20.0,
        )
        content = payload.get("message", {}).get("content", "")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        decision = json.loads(content[start : end + 1])
        if not decision.get("use_local"):
            return None
        confidence = int(decision.get("confidence") or 0)
        if confidence < 10:
            return None
        reason = (decision.get("reasoning") or "").strip() or "The request is self-contained, so BetterCode can answer it locally."
        return {
            "selected_model": f"local/{local_model_id}",
            "selected_model_label": f"{local_preprocess_model_label(local_model_id)} / Local",
            "reasoning": reason,
            "source": "local_direct",
            "task_analysis": task,
            "confidence": confidence,
        }
    except Exception:
        return None


def run_local_model_response(
    prompt_text: str,
    model_id: str | None = None,
    timeout: float = 60.0,
    human_language: str | None = None,
) -> dict:
    status = require_selector_runtime(start_if_needed=True, warm_model=False, startup_timeout=5.0)
    resolved_model_id = model_id or status.get("selected_model") or resolve_local_preprocess_model(status.get("mode"))
    if not resolved_model_id:
        raise RuntimeError("No local preprocess model is ready.")
    system_prompt = (
        "You are BetterCode's local fast path.\n"
        "Answer only the user's request directly.\n"
        "Do not claim to have edited files, run commands, or changed the repository.\n"
        "Keep the answer concise and accurate.\n"
        f"{language_runtime_instruction(human_language)}"
    )
    payload = _api_request(
        "POST",
        "/api/chat",
        {
            "model": resolved_model_id,
            "stream": False,
            "keep_alive": SELECTOR_KEEP_ALIVE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text},
            ],
            "options": {"num_predict": 1200, "temperature": 0.1},
        },
        timeout=max(10.0, timeout),
    )
    reply = (payload.get("message", {}).get("content") or "").strip()
    if not reply:
        raise RuntimeError("Local model returned no output.")
    return {
        "reply": reply,
        "model": f"local/{resolved_model_id}",
        "runtime": "local",
        "session_id": None,
    }


def run_local_prompt_enrichment(
    request_text: str,
    codebase_snippets: str = "",
    timeout: float = 22.0,
) -> str | None:
    """
    Use the local model to rewrite a coding request into a clear, structured
    task brief for the CLI model. Returns the brief or None on failure/skip.
    """
    try:
        status = require_selector_runtime(start_if_needed=True, warm_model=False, startup_timeout=5.0)
        model_id = status.get("selected_model") or resolve_local_preprocess_model(status.get("mode"))
        if not model_id:
            return None

        system_prompt = (
            "You are a coding task analyst preprocessing a request for an AI coding assistant.\n"
            "Given a user request and any relevant codebase snippets, produce a concise structured "
            "task brief under 180 words.\n"
            "Format your output exactly as:\n"
            "Task: [clear 1-2 sentence restatement of what needs to be done]\n"
            "Relevant code: [specific function/class/file names from the context, or 'None']\n"
            "Outcome: [what a fully successful result looks like in one sentence]\n"
            "Be concrete and specific. Do not restate the user's words verbatim. "
            "Do not add steps, explanations, or any other sections."
        )

        user_content = f"User request:\n{request_text[:700]}"
        if codebase_snippets:
            user_content += f"\n\nRelevant codebase snippets:\n{codebase_snippets[:1400]}"

        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": model_id,
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "options": {"num_predict": 320, "temperature": 0.1},
            },
            timeout=max(10.0, timeout),
        )
        result = (payload.get("message", {}).get("content") or "").strip()
        return result if len(result) > 30 else None
    except Exception:
        return None


def _model_history_brief(model_id: str, routing_history: dict | None) -> str | None:
    """Return a short success-rate string for a model from routing history."""
    if not routing_history:
        return None
    for scope in ("workspace", "global"):
        stats = ((routing_history.get(scope) or {}).get("by_model") or {}).get(model_id)
        if not stats:
            continue
        attempts = int(stats.get("attempts") or 0)
        successes = int(stats.get("successes") or 0)
        if attempts >= 2:
            return f"{successes}/{attempts} successful"
    return None


def _build_model_candidates(model_entries: list[dict], routing_history: dict | None = None) -> list[dict]:
    """Build model candidate descriptions with real names for the local routing model."""
    candidates = []
    seen_ids: set[str] = set()
    for entry in model_entries:
        model_id = str(entry.get("id") or "").strip()
        if not model_id or model_id in seen_ids:
            continue
        if "@" in model_id:
            continue
        seen_ids.add(model_id)
        candidate: dict = {
            "id": model_id,
            "label": entry.get("label") or model_id,
            "provider": entry.get("provider") or entry.get("runtime") or "",
            "cost_tier": entry.get("cost_tier") or "medium",
            "speed_tier": entry.get("speed_tier") or "medium",
            "capability_tier": entry.get("capability_tier") or "high",
            "stability": entry.get("stability") or "stable",
            "suggested_uses": entry.get("suggested_uses") or [],
        }
        history = _model_history_brief(model_id, routing_history)
        if history:
            candidate["past_performance"] = history
        candidates.append(candidate)
    return candidates


def _generate_heuristic_reasoning(task: dict, chosen_model: dict) -> str:
    """Generate dynamic reasoning for heuristic model selection."""
    task_type = task.get("task_type") or "general"
    complexity = int(task.get("complexity") or 0)
    model_label = chosen_model.get("label") or chosen_model.get("id") or "the selected model"
    capability_tier = str(chosen_model.get("capability_tier") or "high").lower()
    type_desc = {
        "conversational": "a conversational request",
        "architecture": "an architecture/design task",
        "debugging": "a debugging task",
        "review": "a code review task",
        "implementation": "an implementation task",
        "small_edit": "a small edit",
    }.get(task_type, "a general request")

    if complexity <= 0:
        return f"This is {type_desc} with low complexity — {model_label} is cost-effective and fast enough."
    if complexity <= 2:
        if capability_tier == "very_high":
            return f"This is {type_desc} that benefits from deeper reasoning — {model_label} provides the capability needed."
        return f"This is {type_desc} at moderate complexity — {model_label} balances capability and cost well."
    if capability_tier != "very_high":
        return f"This is a complex {type_desc} — {model_label} was the best available option within cost constraints."
    return f"This is a complex {type_desc} requiring strong reasoning — {model_label} is best suited for this."


def _policy_filtered_model_entries(model_entries: list[dict], task: dict) -> list[dict]:
    filtered = list(model_entries)
    if task.get("task_type") == "conversational":
        cheaper = [entry for entry in filtered if str(entry.get("capability_tier") or "").lower() != "very_high"]
        if cheaper:
            filtered = cheaper
    elif task.get("task_type") == "small_edit" and int(task.get("complexity") or 0) <= 1:
        lighter = [entry for entry in filtered if str(entry.get("capability_tier") or "").lower() != "very_high"]
        if lighter:
            filtered = lighter
    return filtered


def _local_model_select(
    prompt_text: str,
    model_entries: list[dict],
    workspace_context: str,
    task: dict,
    routing_history: dict | None,
    status: dict,
) -> dict:
    """Use the local model to select the best cloud model and produce a refined context.

    The local model receives real model names and metadata so it can leverage its
    training knowledge of each model's strengths.  It returns the chosen model id,
    a reasoning string, and a refined context brief optimised for the chosen model.
    """
    preference = get_auto_model_preference()
    complexity = int(task.get("complexity") or 0)

    # For trivial/simple tasks, restrict candidates to low-cost models so the
    # local router cannot accidentally escalate to an expensive cloud model.
    all_candidates = _build_model_candidates(model_entries, routing_history)
    if not all_candidates:
        raise ValueError("No candidates for local model selection.")

    if complexity <= 1:
        cheap_candidates = [c for c in all_candidates if c.get("cost_tier") == "low"]
        candidates = cheap_candidates if cheap_candidates else all_candidates
    elif complexity <= 2:
        affordable_candidates = [c for c in all_candidates if c.get("cost_tier") in ("low", "medium")]
        candidates = affordable_candidates if affordable_candidates else all_candidates
    else:
        candidates = all_candidates

    candidate_ids = {c["id"] for c in candidates}

    complexity_guidance = ""
    if complexity <= 1:
        complexity_guidance = (
            "\nIMPORTANT: This is a TRIVIAL or SIMPLE task (complexity ≤ 1). "
            "You MUST select the cheapest, fastest model available. "
            "Using an expensive or high-capability model here is wasteful and wrong.\n"
        )
    elif complexity <= 2:
        complexity_guidance = (
            "\nNote: This is a simple-to-moderate task (complexity ≤ 2). "
            "Prefer a low or medium cost model. Do not escalate to expensive models.\n"
        )

    system_prompt = (
        "You are BetterCode's intelligent model router. Your job is to:\n"
        "1. Analyze the user's coding request\n"
        "2. Select the single best model from the candidates list\n"
        "3. Create an optimized context brief for the chosen model\n\n"
        "Use your knowledge of each model's real-world strengths — coding ability, "
        "reasoning depth, speed, and cost-effectiveness. Different providers and model "
        "families have different strengths:\n"
        "- Consider what each model is known for in practice\n"
        "- Match model strengths to the specific demands of the task\n"
        "- Factor in the user's preference, cost tier, and the task complexity\n"
        "- Simple conversational questions, math, and general knowledge should use cheap fast models\n"
        "- Only escalate to high-capability models for genuinely complex coding tasks\n"
        f"{complexity_guidance}\n"
        f"User preference: {preference}\n"
        "- 'cheaper': favor cost-effective models; only use expensive ones for genuinely hard tasks\n"
        "- 'faster': favor low-latency, high-speed models\n"
        "- 'smarter': favor the most capable model available\n"
        "- 'balanced': find the best quality-to-cost ratio for the task\n\n"
        "Return JSON with exactly these keys:\n"
        "- selected_model: the exact model id from the candidates (must match exactly)\n"
        "- reasoning: 1-2 sentences explaining why this model is the best fit\n"
        "- refined_context: a concise structured brief that rephrases the user's request "
        "and workspace context into the clearest possible input for the chosen model. "
        "State the core goal, key constraints, relevant files, and important context. "
        "Remove noise and ambiguity. Keep it under 300 words.\n"
    )

    user_prompt = json.dumps(
        {
            "request": _trim_request(prompt_text),
            "workspace_context": _trim_context(workspace_context),
            "task_analysis": task,
            "user_preference": preference,
            "candidates": candidates,
        },
        ensure_ascii=True,
    )

    payload = _api_request(
        "POST",
        "/api/chat",
        {
            "model": status.get("selected_model") or status["model"],
            "stream": False,
            "keep_alive": SELECTOR_KEEP_ALIVE,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"num_predict": 500, "temperature": 0.15},
        },
        timeout=30.0,
    )

    content = payload.get("message", {}).get("content", "")
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Local model did not return JSON.")

    result = json.loads(content[start : end + 1])
    selected_model = str(result.get("selected_model") or "").strip()

    if selected_model not in candidate_ids:
        raise ValueError(f"Local model selected unknown model: {selected_model}")

    reasoning = (result.get("reasoning") or "").strip() or "Selected by local model router."
    refined_context = (result.get("refined_context") or "").strip()

    return {
        "selected_model": selected_model,
        "reasoning": reasoning,
        "source": "local",
        "task_analysis": task,
        "refined_context": refined_context,
    }


def _fallback_selection(prompt_text: str, available_models: list[str] | list[dict], workspace_context: str = "", routing_history: dict | None = None) -> dict:
    model_entries = _normalize_model_entries(available_models)
    task = _analyze_task(prompt_text, workspace_context)
    if not model_entries:
        raise ValueError("No models are available for Auto Model Select.")
    model_entries = _policy_filtered_model_entries(model_entries, task)

    preferred = max(
        model_entries,
        key=lambda entry: (
            _score_model_for_task(entry, task, routing_history),
            int(entry.get("context_window") or 0),
            entry["id"],
        ),
    )

    return {
        "selected_model": preferred["id"],
        "reasoning": _generate_heuristic_reasoning(task, preferred),
        "source": "heuristic",
        "task_analysis": task,
    }


def select_best_model(
    prompt_text: str,
    available_models: list[str] | list[dict],
    workspace_context: str = "",
    routing_history: dict | None = None,
    selector_runtime_status: dict | None = None,
) -> dict:
    model_entries = _normalize_model_entries(available_models)
    if not model_entries:
        raise ValueError("No models are available for Auto Model Select.")
    model_entries, cost_cap, cap_exceeded = _apply_cost_cap(model_entries)
    task = _analyze_task(prompt_text, workspace_context)

    # Short-circuit: route obvious trivial requests (simple math, short
    # conversational questions, jokes) directly to the local model when it
    # is available, bypassing both the local router and any cloud model.
    if get_local_preprocess_mode() != "off":
        try:
            status = selector_runtime_status or ensure_selector_runtime(
                start_if_needed=True, warm_model=False,
            )
        except Exception:
            status = None

        if status and status.get("running") and status.get("model_ready"):
            local_model_id = status.get("selected_model") or resolve_local_preprocess_model(status.get("mode"))
            if local_model_id and _obvious_local_answer_request(prompt_text, task):
                selection = {
                    "selected_model": f"local/{local_model_id}",
                    "selected_model_label": f"{local_preprocess_model_label(local_model_id)} / Local",
                    "reasoning": "This is a short self-contained request, so BetterCode answered it locally.",
                    "source": "local_direct",
                    "task_analysis": task,
                    "confidence": 10,
                }
                return _apply_cost_cap_note(selection, cost_cap, cap_exceeded)

            try:
                selection = _local_model_select(
                    prompt_text, model_entries, workspace_context,
                    task, routing_history, status,
                )
                return _apply_cost_cap_note(selection, cost_cap, cap_exceeded)
            except Exception:
                pass

    # Heuristic fallback when local model is unavailable
    selection = _fallback_selection(prompt_text, model_entries, workspace_context, routing_history)
    return _apply_cost_cap_note(selection, cost_cap, cap_exceeded)


def select_best_model_heuristic(
    prompt_text: str,
    available_models: list[str] | list[dict],
    workspace_context: str = "",
    routing_history: dict | None = None,
) -> dict:
    """Heuristic-only model selection (no local Ollama routing call).

    Intended for lightweight subtask recommendations during preprocessing.
    """

    model_entries = _normalize_model_entries(available_models)
    if not model_entries:
        raise ValueError("No models are available for Auto Model Select.")
    model_entries, cost_cap, cap_exceeded = _apply_cost_cap(model_entries)
    selection = _fallback_selection(prompt_text, model_entries, workspace_context, routing_history)
    return _apply_cost_cap_note(selection, cost_cap, cap_exceeded)


def plan_subtasks(
    prompt_text: str,
    available_models: list[str] | list[dict],
    workspace_context: str = "",
    routing_history: dict | None = None,
    selector_runtime_status: dict | None = None,
    max_tasks: int = 6,
) -> dict:
    """Ask the local router (via Ollama) to break the request into subtasks.

    Returns: {"source": "local"|"fallback", "tasks": [ ... ]}
    Each task: {"id","title","detail","depends_on","execution","stage","model_id","model_label","selection_reason"}
    """

    model_entries = _normalize_model_entries(available_models)
    if not model_entries:
        return {"source": "fallback", "tasks": []}

    max_tasks = max(1, min(int(max_tasks or 6), 10))
    trimmed_request = _trim_request(prompt_text)
    trimmed_context = _trim_context(workspace_context)
    trimmed_history = _trim_history(routing_history)
    task = _analyze_task(prompt_text, workspace_context)
    fallback_tasks = _fallback_subtask_outline(task)
    direct_tasks = _fallback_subtask_outline(task, direct_only=True)

    if get_local_preprocess_mode() == "off":
        return {
            "source": "local_off",
            "tasks": _finalize_subtask_plan(
                fallback_tasks,
                model_entries,
                task,
                routing_history=routing_history,
            ),
        }

    if should_skip_local_preprocessing(task):
        return {
            "source": "intent_gate",
            "tasks": _finalize_subtask_plan(
                direct_tasks,
                model_entries,
                task,
                routing_history=routing_history,
            ),
        }

    status = selector_runtime_status or ensure_selector_runtime(start_if_needed=True, warm_model=False)
    if not (status.get("running") and status.get("model_ready")):
        return {
            "source": "fallback",
            "tasks": _finalize_subtask_plan(
                fallback_tasks,
                model_entries,
                task,
                routing_history=routing_history,
            ),
        }

    candidates = _planning_candidates(model_entries)

    system_prompt = (
        "You are a project manager that decomposes software tasks.\n"
        "Break the user's request into a small set of concrete implementation subtasks.\n"
        "If the request contains multiple asks, keep them as separate sibling tasks instead of collapsing them into one large task.\n"
        "Assign an appropriate model_id for each subtask from the provided candidates list.\n"
        "The local model has already handled requirements gathering and planning. Do NOT add inspect or validate tasks — only generate implementation tasks.\n"
        "Mark only genuinely independent tasks execution=async. Sequential work must stay execution=sync.\n"
        "Dependencies should be minimal and precise.\n"
        "Output ONLY valid JSON (no markdown).\n"
        "Return a JSON array of objects with keys:\n"
        "- id: short slug (unique)\n"
        "- title: short title\n"
        "- detail: one sentence\n"
        "- depends_on: array of ids (can be empty)\n"
        "- execution: 'sync' or 'async'\n"
        "- stage: 'edit' (always — no inspect or validate tasks)\n"
        "- model_id: string (must match a candidate id)\n"
        "Keep it to at most "
        + str(max_tasks)
        + " tasks."
    )
    user_prompt = json.dumps(
        {
            "request": trimmed_request,
            "workspace_context": trimmed_context,
            "routing_history": trimmed_history,
            "candidates": candidates,
            "max_tasks": max_tasks,
        },
        ensure_ascii=True,
    )

    try:
        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": status.get("selected_model") or status["model"],
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"num_predict": 400, "temperature": 0.2},
            },
            timeout=45.0,
        )
        content = payload.get("message", {}).get("content", "")
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("Planner did not return JSON array.")
        tasks = json.loads(content[start : end + 1])
        if not isinstance(tasks, list):
            raise ValueError("Planner did not return a list.")

        valid_ids = {entry.get("id") for entry in candidates if entry.get("id")}

        usable_tasks = []
        for raw in tasks[:max_tasks]:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("model_id") or "").strip() not in valid_ids:
                raw = {**raw, "model_id": ""}
            usable_tasks.append(raw)

        if not usable_tasks:
            raise ValueError("Planner returned no usable tasks.")
        return {
            "source": "local",
            "tasks": _finalize_subtask_plan(
                usable_tasks,
                model_entries,
                task,
                routing_history=routing_history,
            ),
        }
    except Exception:
        return {
            "source": "fallback",
            "tasks": _finalize_subtask_plan(
                fallback_tasks,
                model_entries,
                task,
                routing_history=routing_history,
            ),
        }


def _fallback_recommendations(prompt_text: str, reply_text: str, change_log: list[dict]) -> list[str]:
    if not change_log:
        return []

    changed_paths = [
        str(change.get("path", "")).lower()
        for change in change_log
        if change.get("status") != "truncated"
    ]
    if not changed_paths:
        return []

    if any("/tests/" in path or path.startswith("tests/") or "/test_" in path or path.endswith("_test.py") or ".spec." in path for path in changed_paths):
        return []

    combined = f"{prompt_text}\n{reply_text}".lower()
    if any(term in combined for term in ("spacing", "padding", "margin", "alignment", "align", "color", "theme", "label", "rename", "wording", "copy", "placeholder", "button text", "subtitle")):
        return []

    def extension(path: str) -> str:
        index = path.rfind(".")
        return path[index:] if index != -1 else ""

    non_code_only = all(extension(path) in NON_CODE_EXTENSIONS for path in changed_paths)
    if non_code_only:
        return []

    has_code = any(extension(path) in CODE_EXTENSIONS for path in changed_paths)
    if not has_code:
        return []

    if any(term in combined for term in ("bug", "fix", "failing", "error", "logic", "behavior", "api", "auth", "router", "state", "selector", "session", "model", "git", "refactor", "implement")):
        return [TEST_RECOMMENDATION]

    if len(changed_paths) >= 2:
        return [TEST_RECOMMENDATION]

    return []


def _reply_ends_with_question(reply: str) -> bool:
    """True when the assistant reply closes with a direct question to the user."""
    return bool(re.search(r"[^.!?\s][^.!?]*\?[\s\"']*$", reply.strip()))


def _trailing_question_text(reply: str) -> str:
    text = reply.strip()
    if not text:
        return ""
    question_index = text.rfind("?")
    if question_index == -1:
        return ""

    boundary = max(
        text.rfind("\n", 0, question_index),
        text.rfind(". ", 0, question_index),
        text.rfind("! ", 0, question_index),
        text.rfind("? ", 0, question_index),
    )
    start = boundary + 1 if boundary != -1 else 0
    return text[start : question_index + 1].strip().strip("\"'")


def _reply_expects_binary_response(reply: str) -> bool:
    question = _trailing_question_text(reply)
    return bool(re.match(r"^(?:do|did|does|can|could|would|should|will|is|are|was|were|have|has|had|want|need)\b", question, re.IGNORECASE))


def _looks_like_ui_instruction(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.startswith(("click ", "select ", "open ", "tap ", "press ", "go to ", "head to ", "navigate to ", "switch to "))


def suggest_follow_up_recommendations(prompt_text: str, reply_text: str, change_log: list[dict]) -> list[str]:
    is_question = _reply_ends_with_question(reply_text)
    if is_question and _reply_expects_binary_response(reply_text):
        return []

    fallback = [] if is_question else _fallback_recommendations(prompt_text, reply_text, change_log)
    if get_local_preprocess_mode() == "off":
        return fallback

    status = ensure_selector_runtime(start_if_needed=True, warm_model=False)
    if not (status["running"] and status["model_ready"]):
        return fallback

    if is_question:
        # Generate short reply options contextual to the question, not next-action suggestions
        system_prompt = (
            "The assistant's reply ends with a direct question to the user.\n"
            "Generate 1 or 2 concise, natural response options the user might select.\n"
            "Each option must directly answer the question — no filler, no restating the question.\n"
            "Write each option as the user's actual reply, not as an instruction.\n"
            "Never output UI actions or commands like Click, Select, Open, or Go to.\n"
            "Keep each option under 60 characters. Be specific to the actual question asked.\n"
            'Return JSON: {"recommendations": ["...", "..."]} with at most 2 items.\n'
        )
        num_predict = 120
    else:
        system_prompt = (
            "You decide whether BetterCode should suggest a single next prompt after a coding turn.\n"
            "Be conservative. Return no recommendation unless there is a clear, high-value next step.\n"
            "Do not default to tests. Suggest tests only when behavior or logic likely changed and verification would materially help.\n"
            "If you recommend something, it must be one short, specific user-facing prompt BetterCode could prefill next.\n"
            'Return JSON with exactly one key: recommendations, which must be either [] or ["..."] with at most one item.\n'
        )
        num_predict = 80

    user_prompt = json.dumps(
        {
            "request": _trim_request(prompt_text),
            "reply": reply_text[-2000:] if len(reply_text) > 2000 else reply_text,
            "changed_files": [
                {"path": change.get("path", ""), "status": change.get("status", "")}
                for change in change_log[:8]
            ],
        },
        ensure_ascii=True,
    )

    try:
        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": status.get("selected_model") or status["model"],
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"num_predict": num_predict, "temperature": 0.2},
            },
            timeout=20.0,
        )
        content = payload.get("message", {}).get("content", "")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Recommendation selector did not return JSON.")
        result = json.loads(content[start : end + 1])
        recommendations = result.get("recommendations", [])
        if not isinstance(recommendations, list):
            raise ValueError("Recommendation selector returned an invalid payload.")

        max_items = 2 if is_question else MAX_FOLLOW_UP_RECOMMENDATIONS
        normalized = []
        for recommendation in recommendations[:max_items]:
            if not isinstance(recommendation, str):
                continue
            text = " ".join(recommendation.split()).strip()
            if not text:
                continue
            if len(text) > MAX_FOLLOW_UP_RECOMMENDATION_LENGTH:
                continue
            if is_question and _looks_like_ui_instruction(text):
                continue
            normalized.append(text)
        return normalized
    except Exception:
        pass

    return fallback


def _scan_project_for_run_hints(workspace_path: str) -> dict:
    from pathlib import Path as _Path
    path = _Path(workspace_path)
    hints: dict = {}

    pkg = path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            if scripts:
                hints["package.json"] = {"scripts": scripts}
        except Exception:
            pass

    for fname in ("Makefile", "makefile"):
        mf = path / fname
        if mf.exists():
            try:
                hints["Makefile"] = {"content": mf.read_text(encoding="utf-8")[:1500]}
            except Exception:
                pass
            break

    for fname in ("pyproject.toml", "setup.py", "setup.cfg"):
        f = path / fname
        if f.exists():
            try:
                hints[fname] = {"content": f.read_text(encoding="utf-8")[:1500]}
            except Exception:
                hints[fname] = {"exists": True}
            break

    for fname in ("Cargo.toml",):
        f = path / fname
        if f.exists():
            hints[fname] = {"exists": True}

    for fname in ("go.mod",):
        f = path / fname
        if f.exists():
            try:
                hints[fname] = {"content": f.read_text(encoding="utf-8")[:500]}
            except Exception:
                hints[fname] = {"exists": True}

    for env_file in (".env.example", ".env.template", ".env.sample"):
        ep = path / env_file
        if ep.exists():
            try:
                hints[env_file] = {"content": ep.read_text(encoding="utf-8")[:1500]}
            except Exception:
                pass
            break

    for main_file in ("main.py", "app.py", "server.py", "index.js", "server.js"):
        if (path / main_file).exists():
            hints[main_file] = {"exists": True}

    return hints


def _detect_settings_suggestions(hints: dict) -> list[dict]:
    """Heuristic-based run settings suggestions (HOST, PORT, etc.)."""
    web_indicators = ("package.json", "app.py", "main.py", "server.py", "server.js", "index.js",
                      "pyproject.toml")
    if not any(k in hints for k in web_indicators):
        return []

    default_port = ""
    if "package.json" in hints:
        scripts = hints["package.json"].get("scripts", {})
        for script_val in scripts.values():
            m = re.search(r'--port[= ](\d+)', str(script_val))
            if m:
                default_port = m.group(1)
                break
    if not default_port:
        content = ""
        for key in ("pyproject.toml", "app.py", "main.py", "server.py"):
            if key in hints:
                content = hints[key].get("content", "")
                break
        m = re.search(r'port[=\s]+(\d{4,5})', content)
        if m:
            default_port = m.group(1)

    return [
        {"name": "HOST", "label": "Host", "description": "Network interface to bind to", "default_value": "127.0.0.1"},
        {"name": "PORT", "label": "Port", "description": "Port to listen on", "default_value": default_port},
    ]


def _fallback_run_config(hints: dict) -> dict:
    settings_suggested = _detect_settings_suggestions(hints)
    if "package.json" in hints:
        scripts = hints["package.json"].get("scripts", {})
        for key in ("dev", "start", "serve"):
            if key in scripts:
                return {"command": f"npm run {key}", "detected_from": f"package.json scripts.{key}", "env_required": [], "settings_suggested": settings_suggested}

    if "Cargo.toml" in hints:
        return {"command": "cargo run", "detected_from": "Cargo.toml", "env_required": [], "settings_suggested": settings_suggested}

    if "go.mod" in hints:
        return {"command": "go run ./...", "detected_from": "go.mod", "env_required": [], "settings_suggested": settings_suggested}

    if "pyproject.toml" in hints:
        content = hints["pyproject.toml"].get("content", "").lower()
        if "uvicorn" in content or "fastapi" in content:
            return {"command": "uvicorn main:app --reload", "detected_from": "pyproject.toml", "env_required": [], "settings_suggested": settings_suggested}
        if "flask" in content:
            return {"command": "flask run", "detected_from": "pyproject.toml", "env_required": [], "settings_suggested": settings_suggested}

    if "main.py" in hints:
        return {"command": "python main.py", "detected_from": "main.py", "env_required": [], "settings_suggested": settings_suggested}
    if "app.py" in hints:
        return {"command": "python app.py", "detected_from": "app.py", "env_required": [], "settings_suggested": settings_suggested}
    if "server.py" in hints:
        return {"command": "python server.py", "detected_from": "server.py", "env_required": [], "settings_suggested": settings_suggested}
    if "index.js" in hints:
        return {"command": "node index.js", "detected_from": "index.js", "env_required": [], "settings_suggested": settings_suggested}
    if "server.js" in hints:
        return {"command": "node server.js", "detected_from": "server.js", "env_required": [], "settings_suggested": settings_suggested}

    return {"command": "", "detected_from": "", "env_required": [], "settings_suggested": []}


def detect_project_run_config(workspace_path: str) -> dict:
    hints = _scan_project_for_run_hints(workspace_path)
    fallback = _fallback_run_config(hints)

    status = ensure_selector_runtime(start_if_needed=True, warm_model=False)
    if not (status["running"] and status["model_ready"]):
        return fallback

    system_prompt = (
        "You are a project run config detector for BetterCode.\n"
        "Given project file hints, detect the single best command to run the project, required environment variables, and configurable run settings.\n"
        "Prefer specific scripts: use 'npm run dev' over 'npm start' when a dev script exists.\n"
        "For env_required, only include variables that are clearly required (not optional). Keep the list short.\n"
        "For settings_suggested, include only variables the user would commonly want to configure before running "
        "(e.g. HOST, PORT, DATABASE_URL, API keys). Only include items relevant to this project. Limit to 6 items.\n"
        "Return JSON with exactly four keys: "
        "command (string, the shell command to run the project), "
        "detected_from (string, which file you used), "
        "env_required (array of {name, description} objects for required env vars), "
        "settings_suggested (array of {name, label, description, default_value} objects for configurable settings).\n"
        "If you cannot determine a command, set command to empty string.\n"
    )
    user_prompt = json.dumps({"project_hints": hints}, ensure_ascii=True)

    try:
        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": status.get("selected_model") or status["model"],
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"num_predict": 256, "temperature": 0.1},
            },
            timeout=20.0,
        )
        content = payload.get("message", {}).get("content", "")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return fallback

        result = json.loads(content[start:end + 1])
        command = str(result.get("command") or "").strip()
        detected_from = str(result.get("detected_from") or "").strip()
        env_required_raw = result.get("env_required") or []
        env_required = []
        if isinstance(env_required_raw, list):
            for item in env_required_raw[:10]:
                if isinstance(item, dict) and item.get("name"):
                    env_required.append({
                        "name": str(item["name"]).strip(),
                        "description": str(item.get("description") or "").strip(),
                    })
        settings_suggested_raw = result.get("settings_suggested") or []
        settings_suggested = []
        if isinstance(settings_suggested_raw, list):
            for item in settings_suggested_raw[:6]:
                if isinstance(item, dict) and item.get("name"):
                    settings_suggested.append({
                        "name": str(item["name"]).strip(),
                        "label": str(item.get("label") or item["name"]).strip(),
                        "description": str(item.get("description") or "").strip(),
                        "default_value": str(item.get("default_value") or "").strip(),
                    })
        if not settings_suggested:
            settings_suggested = fallback.get("settings_suggested", [])

        return {
            "command": command or fallback.get("command", ""),
            "detected_from": detected_from or fallback.get("detected_from", ""),
            "env_required": env_required,
            "settings_suggested": settings_suggested,
        }
    except Exception:
        return fallback


_FALLBACK_SUMMARY_MAX_CHARS = 1_280  # matches Ollama's num_predict: 320 budget (~4 chars/token)


def _fallback_context_summary(previous_summary: str, transcript: str) -> str:
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    important = []

    for line in lines:
        lower = line.lower()
        if any(token in lower for token in ("error", "failed", "bug", "fix", "todo", "path", ".py", ".js", ".ts", "commit", "model", "workspace")):
            important.append(line)

    if not important:
        important = lines[-12:]

    summary_parts = []
    if previous_summary.strip():
        summary_parts.append(f"Previous summary: {previous_summary.strip()[:600]}")
    if important:
        summary_parts.append("Relevant context:\n" + "\n".join(f"- {line[:180]}" for line in important[:8]))

    result = "\n\n".join(summary_parts).strip()
    # Hard cap so the fallback never exceeds what Ollama would have produced.
    return result[:_FALLBACK_SUMMARY_MAX_CHARS]


def squash_workspace_context(previous_summary: str, transcript: str) -> str:
    transcript = transcript.strip()
    if not transcript:
        return previous_summary.strip()

    status = ensure_selector_runtime(start_if_needed=True, warm_model=False)
    if not (status["running"] and status["model_ready"]):
        return _fallback_context_summary(previous_summary, transcript)

    system_prompt = (
        "You are a workspace context manager for a coding assistant.\n"
        "Compress old chat history into a compact technical summary.\n"
        "Keep durable facts only: requirements, architecture, constraints, bugs, decisions, file paths, commands, models, and unresolved work.\n"
        "Drop filler, repetition, status chatter, greetings, and irrelevant detail.\n"
        "Output plain text only.\n"
    )
    user_prompt = json.dumps(
        {
            "previous_summary": previous_summary,
            "transcript": transcript,
        },
        ensure_ascii=True,
    )

    try:
        payload = _api_request(
            "POST",
            "/api/chat",
            {
                "model": status.get("selected_model") or status["model"],
                "stream": False,
                "keep_alive": SELECTOR_KEEP_ALIVE,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"num_predict": 320, "temperature": 0.1},
            },
            timeout=30.0,
        )
        content = (payload.get("message", {}).get("content") or "").strip()
        if not content:
            raise ValueError("Selector summary was empty.")
        return content
    except Exception:
        return _fallback_context_summary(previous_summary, transcript)
