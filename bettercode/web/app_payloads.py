from bettercode.settings import get_app_settings


def app_settings_payload() -> dict:
    return {"settings": get_app_settings()}


def build_app_info_payload(
    *,
    cwd: str,
    dev_mode: bool,
    languages: dict,
    models: list[dict],
    platform: str,
    runtimes: dict,
    auth: dict,
    selector: dict,
    settings: dict,
    telemetry: dict,
    update: dict | None,
    version: str,
) -> dict:
    return {
        "cwd": cwd,
        "dev_mode": dev_mode,
        "languages": languages,
        "models": models,
        "platform": platform,
        "runtimes": runtimes,
        "auth": auth,
        "selector": selector,
        "settings": settings,
        "telemetry": telemetry,
        "update": update,
        "version": version,
    }
