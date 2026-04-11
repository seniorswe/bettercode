import json
import logging
import os
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

from bettercode.app_meta import bettercode_home_dir
from bettercode.i18n import detect_system_human_language, normalize_human_language
from bettercode.updater import normalize_version_tag


COST_TIER_ORDER = ("low", "medium", "high")
AUTO_MODEL_PREFERENCE_ORDER = ("balanced", "cheaper", "faster", "smarter")
PERFORMANCE_PROFILE_ORDER = ("fast", "balanced", "full")
LOCAL_PREPROCESS_MODE_ORDER = ("off", "tiny", "small")
FONT_SIZE_ORDER = ("extra-small", "small", "medium", "large")
PERFORMANCE_PROFILE_DEFAULTS = {
    "fast": {
        "auto_model_preference": "faster",
        "enable_task_breakdown": False,
        "enable_follow_up_suggestions": False,
    },
    "balanced": {
        "auto_model_preference": "balanced",
        "enable_task_breakdown": True,
        "enable_follow_up_suggestions": True,
    },
    "full": {
        "auto_model_preference": "smarter",
        "enable_task_breakdown": True,
        "enable_follow_up_suggestions": True,
    },
}
_UNSET = object()


def normalize_cost_tier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in COST_TIER_ORDER else None


def normalize_auto_model_preference(value: str | None) -> str:
    if value is None:
        return "balanced"
    normalized = str(value).strip().lower()
    return normalized if normalized in AUTO_MODEL_PREFERENCE_ORDER else "balanced"


def normalize_performance_profile(value: str | None) -> str:
    if value is None:
        return "balanced"
    normalized = str(value).strip().lower()
    return normalized if normalized in PERFORMANCE_PROFILE_ORDER else "balanced"


def normalize_local_preprocess_mode(value: str | None) -> str:
    if value is None:
        return "off"
    normalized = str(value).strip().lower()
    return normalized if normalized in LOCAL_PREPROCESS_MODE_ORDER else "off"


def normalize_local_preprocess_model(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_font_size(value: str | None) -> str:
    if value is None:
        return "medium"
    normalized = str(value).strip().lower()
    return normalized if normalized in FONT_SIZE_ORDER else "medium"


def normalize_human_language_setting(value: str | None) -> str:
    return normalize_human_language(value)


def normalize_mock_update_version(value: str | None) -> str | None:
    normalized = normalize_version_tag(str(value or ""))
    return normalized or None


def normalize_bool_setting(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _bettercode_home_dir():
    return bettercode_home_dir(create=True)


def _settings_path() -> Path:
    return _bettercode_home_dir() / "settings.json"


_settings_cache: dict | None = None
_settings_cache_mtime: float = -1.0
_settings_cache_lock = threading.Lock()


def _invalidate_settings_cache() -> None:
    global _settings_cache, _settings_cache_mtime
    with _settings_cache_lock:
        _settings_cache = None
        _settings_cache_mtime = -1.0


def load_settings() -> dict:
    global _settings_cache, _settings_cache_mtime
    path = _settings_path()
    try:
        mtime = path.stat().st_mtime if path.exists() else -1.0
    except OSError:
        mtime = -1.0
    with _settings_cache_lock:
        if _settings_cache is not None and mtime == _settings_cache_mtime:
            return dict(_settings_cache)
    if mtime == -1.0:
        with _settings_cache_lock:
            _settings_cache = {}
            _settings_cache_mtime = mtime
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        _logger.warning("Failed to parse settings file %s; using defaults", path)
        return {}
    result = data if isinstance(data, dict) else {}
    with _settings_cache_lock:
        _settings_cache = result
        _settings_cache_mtime = mtime
    return dict(result)


def save_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, sort_keys=True))
    _invalidate_settings_cache()


def get_max_cost_tier() -> str | None:
    settings = load_settings()
    if "max_cost_tier" in settings:
        normalized = normalize_cost_tier(settings.get("max_cost_tier"))
        if normalized is not None or settings.get("max_cost_tier") is None:
            return normalized
    return normalize_cost_tier(os.environ.get("BETTERCODE_MAX_COST_TIER"))


def get_performance_profile() -> str:
    settings = load_settings()
    if "performance_profile" in settings:
        return normalize_performance_profile(settings.get("performance_profile"))
    return normalize_performance_profile(os.environ.get("BETTERCODE_PERFORMANCE_PROFILE"))


def update_settings(updates: dict) -> dict:
    settings = load_settings()
    settings.update(updates)
    save_settings(settings)
    return settings


def set_max_cost_tier(value: str | None) -> dict:
    if value is None:
        return update_settings({"max_cost_tier": None})
    normalized = normalize_cost_tier(value)
    if normalized is None:
        raise ValueError("Invalid cost tier")
    return update_settings({"max_cost_tier": normalized})


def get_auto_model_preference() -> str:
    settings = load_settings()
    if "auto_model_preference" in settings:
        value = settings.get("auto_model_preference")
        if value is not None:
            return normalize_auto_model_preference(value)
    env_value = os.environ.get("BETTERCODE_AUTO_MODEL_PREFERENCE")
    if env_value is not None:
        return normalize_auto_model_preference(env_value)
    profile = get_performance_profile()
    return PERFORMANCE_PROFILE_DEFAULTS[profile]["auto_model_preference"]


def get_enable_task_breakdown() -> bool:
    settings = load_settings()
    if "enable_task_breakdown" in settings:
        value = settings.get("enable_task_breakdown")
        if value is not None:
            return normalize_bool_setting(value, default=True)
    env_value = os.environ.get("BETTERCODE_ENABLE_TASK_BREAKDOWN")
    if env_value is not None:
        return normalize_bool_setting(env_value, default=True)
    profile = get_performance_profile()
    return bool(PERFORMANCE_PROFILE_DEFAULTS[profile]["enable_task_breakdown"])


def get_enable_follow_up_suggestions() -> bool:
    settings = load_settings()
    if "enable_follow_up_suggestions" in settings:
        value = settings.get("enable_follow_up_suggestions")
        if value is not None:
            return normalize_bool_setting(value, default=True)
    env_value = os.environ.get("BETTERCODE_ENABLE_FOLLOW_UP_SUGGESTIONS")
    if env_value is not None:
        return normalize_bool_setting(env_value, default=True)
    profile = get_performance_profile()
    return bool(PERFORMANCE_PROFILE_DEFAULTS[profile]["enable_follow_up_suggestions"])


def get_local_preprocess_mode() -> str:
    settings = load_settings()
    if "local_preprocess_mode" in settings:
        value = settings.get("local_preprocess_mode")
        if value is not None:
            return normalize_local_preprocess_mode(value)
    if normalize_local_preprocess_model(settings.get("local_preprocess_model")):
        return "small"
    env_value = os.environ.get("BETTERCODE_LOCAL_PREPROCESS_MODE")
    if env_value is not None:
        return normalize_local_preprocess_mode(env_value)
    if normalize_local_preprocess_model(os.environ.get("BETTERCODE_LOCAL_PREPROCESS_MODEL")):
        return "small"
    return "off"


def get_local_preprocess_model() -> str | None:
    settings = load_settings()
    if "local_preprocess_model" in settings:
        return normalize_local_preprocess_model(settings.get("local_preprocess_model"))
    return normalize_local_preprocess_model(os.environ.get("BETTERCODE_LOCAL_PREPROCESS_MODEL"))


def get_font_size() -> str:
    settings = load_settings()
    if "font_size" in settings:
        return normalize_font_size(settings.get("font_size"))
    return normalize_font_size(os.environ.get("BETTERCODE_FONT_SIZE"))


def get_human_language() -> str:
    settings = load_settings()
    if "human_language" in settings:
        return normalize_human_language_setting(settings.get("human_language"))
    env_value = os.environ.get("BETTERCODE_HUMAN_LANGUAGE")
    if env_value is not None:
        return normalize_human_language_setting(env_value)
    return detect_system_human_language()


def get_mock_update_version() -> str | None:
    settings = load_settings()
    if "mock_update_version" in settings:
        return normalize_mock_update_version(settings.get("mock_update_version"))
    return normalize_mock_update_version(os.environ.get("BETTERCODE_FAKE_UPDATE_VERSION"))


def has_explicit_human_language_setting() -> bool:
    settings = load_settings()
    return "human_language" in settings and bool(str(settings.get("human_language") or "").strip())


def set_mock_update_version(value: str | None) -> dict:
    return update_settings({"mock_update_version": normalize_mock_update_version(value)})


def set_auto_model_preference(value: str | None) -> dict:
    normalized = normalize_auto_model_preference(value)
    return update_settings({"auto_model_preference": normalized})


def set_app_settings(
    max_cost_tier=_UNSET,
    auto_model_preference=_UNSET,
    enable_task_breakdown=_UNSET,
    enable_follow_up_suggestions=_UNSET,
    performance_profile=_UNSET,
    local_preprocess_mode=_UNSET,
    local_preprocess_model=_UNSET,
    font_size=_UNSET,
    human_language=_UNSET,
) -> dict:
    updates: dict[str, object] = {}
    profile_changed = performance_profile is not _UNSET
    if max_cost_tier is not _UNSET:
        if max_cost_tier is None:
            updates["max_cost_tier"] = None
        else:
            normalized_cost = normalize_cost_tier(max_cost_tier)
            if normalized_cost is None:
                raise ValueError("Invalid cost tier")
            updates["max_cost_tier"] = normalized_cost
    if auto_model_preference is not _UNSET:
        updates["auto_model_preference"] = None if auto_model_preference is None else normalize_auto_model_preference(auto_model_preference)
    if enable_task_breakdown is not _UNSET:
        updates["enable_task_breakdown"] = None if enable_task_breakdown is None else bool(enable_task_breakdown)
    if enable_follow_up_suggestions is not _UNSET:
        updates["enable_follow_up_suggestions"] = None if enable_follow_up_suggestions is None else bool(enable_follow_up_suggestions)
    if performance_profile is not _UNSET:
        updates["performance_profile"] = normalize_performance_profile(performance_profile)
    if local_preprocess_mode is not _UNSET:
        updates["local_preprocess_mode"] = None if local_preprocess_mode is None else normalize_local_preprocess_mode(local_preprocess_mode)
    if local_preprocess_model is not _UNSET:
        normalized_model = normalize_local_preprocess_model(local_preprocess_model)
        updates["local_preprocess_model"] = normalized_model
        if local_preprocess_mode is _UNSET:
            updates["local_preprocess_mode"] = "small" if normalized_model else "off"
    if font_size is not _UNSET:
        updates["font_size"] = None if font_size is None else normalize_font_size(font_size)
    if human_language is not _UNSET:
        updates["human_language"] = None if human_language is None else normalize_human_language_setting(human_language)
    if profile_changed and auto_model_preference is _UNSET:
        updates["auto_model_preference"] = None
    if profile_changed and enable_task_breakdown is _UNSET:
        updates["enable_task_breakdown"] = None
    if profile_changed and enable_follow_up_suggestions is _UNSET:
        updates["enable_follow_up_suggestions"] = None
    return update_settings(updates)


def get_app_settings() -> dict:
    return {
        "performance_profile": get_performance_profile(),
        "max_cost_tier": get_max_cost_tier(),
        "auto_model_preference": get_auto_model_preference(),
        "enable_task_breakdown": get_enable_task_breakdown(),
        "enable_follow_up_suggestions": get_enable_follow_up_suggestions(),
        "local_preprocess_mode": get_local_preprocess_mode(),
        "local_preprocess_model": get_local_preprocess_model(),
        "font_size": get_font_size(),
        "human_language": get_human_language(),
    }
