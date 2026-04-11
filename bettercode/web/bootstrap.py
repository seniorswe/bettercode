import threading

from bettercode.router.selector import require_selector_runtime, selector_status
from bettercode.settings import get_local_preprocess_mode


def _require_selector_for_app_startup() -> dict:
    try:
        status = require_selector_runtime(
            start_if_needed=True,
            warm_model=True,
            startup_timeout=10.0,
        )
        return {"ok": True, "status": status, "error": ""}
    except RuntimeError as exc:
        return {"ok": False, "status": selector_status(), "error": str(exc)}


def _warm_selector_runtime_best_effort() -> bool:
    return _require_selector_for_app_startup().get("ok") is True


def _start_selector_warmup() -> None:
    if get_local_preprocess_mode() == "off":
        return
    threading.Thread(
        target=_require_selector_for_app_startup,
        daemon=True,
    ).start()


def _start_selector_runtime_warmup() -> None:
    threading.Thread(
        target=_warm_selector_runtime_best_effort,
        daemon=True,
    ).start()
