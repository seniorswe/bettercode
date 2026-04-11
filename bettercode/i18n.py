import locale


SUPPORTED_HUMAN_LANGUAGES = {
    "en": {
        "code": "en",
        "label": "English",
        "native_label": "English",
        "locale": "en-US",
        "prompt_label": "English",
    },
    "fr": {
        "code": "fr",
        "label": "French",
        "native_label": "Français",
        "locale": "fr-FR",
        "prompt_label": "French",
    },
    "de": {
        "code": "de",
        "label": "German",
        "native_label": "Deutsch",
        "locale": "de-DE",
        "prompt_label": "German",
    },
    "hi": {
        "code": "hi",
        "label": "Hindi",
        "native_label": "हिन्दी",
        "locale": "hi-IN",
        "prompt_label": "Hindi",
    },
    "pl": {
        "code": "pl",
        "label": "Polish",
        "native_label": "Polski",
        "locale": "pl-PL",
        "prompt_label": "Polish",
    },
    "zh": {
        "code": "zh",
        "label": "Chinese",
        "native_label": "简体中文",
        "locale": "zh-CN",
        "prompt_label": "Simplified Chinese",
    },
    "ja": {
        "code": "ja",
        "label": "Japanese",
        "native_label": "日本語",
        "locale": "ja-JP",
        "prompt_label": "Japanese",
    },
    "ko": {
        "code": "ko",
        "label": "Korean",
        "native_label": "한국어",
        "locale": "ko-KR",
        "prompt_label": "Korean",
    },
}

DEFAULT_HUMAN_LANGUAGE = "en"


def normalize_human_language(value: str | None) -> str:
    if value is None:
        return DEFAULT_HUMAN_LANGUAGE
    normalized = str(value).strip().lower().replace("_", "-")
    if not normalized:
        return DEFAULT_HUMAN_LANGUAGE
    if normalized in SUPPORTED_HUMAN_LANGUAGES:
        return normalized
    base = normalized.split("-", 1)[0]
    return base if base in SUPPORTED_HUMAN_LANGUAGES else DEFAULT_HUMAN_LANGUAGE


def detect_system_human_language() -> str:
    try:
        system_locale = locale.getlocale()[0]
    except Exception:
        system_locale = None
    return normalize_human_language(system_locale)


def human_language_meta(code: str | None) -> dict:
    normalized = normalize_human_language(code)
    return dict(SUPPORTED_HUMAN_LANGUAGES[normalized])


def supported_human_languages_payload() -> dict:
    return {
        "default": DEFAULT_HUMAN_LANGUAGE,
        "supported": [dict(entry) for entry in SUPPORTED_HUMAN_LANGUAGES.values()],
    }


def language_runtime_instruction(code: str | None) -> str:
    meta = human_language_meta(code)
    prompt_label = meta["prompt_label"]
    native_label = meta["native_label"]
    return (
        "Human language rule:\n"
        f"- Write all user-facing prose in {prompt_label} ({native_label}).\n"
        f"- If you ask a question, ask it in {prompt_label}.\n"
        f"- Keep code, commands, filenames, API fields, and existing identifiers unchanged unless the task explicitly requires translating them.\n"
        f"- Keep comments in the repo's existing language unless the user explicitly wants translated comments.\n"
    )
