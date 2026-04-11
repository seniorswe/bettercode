import json
import os
from datetime import UTC, datetime
from pathlib import Path
import sys

from bettercode import __version__

APP_NAME = "BetterCode"
APP_SLUG = "bettercode"
APP_BUNDLE_ID = "com.bettercode.desktop"
APP_LAYOUT_VERSION = 1
APP_STATE_FILENAME = "app-state.json"
APP_ICON_PATH = Path(__file__).resolve().parent / "web" / "static" / "app-icon.svg"
APP_ICON_PNG_PATH = Path(__file__).resolve().parent / "web" / "static" / "app-icon-dark.png"
APP_TRAY_ICON_PATH = Path(__file__).resolve().parent / "web" / "static" / "app-icon-tray.svg"
APP_ICNS_PATH = Path(__file__).resolve().parent / "web" / "static" / "bettercode.icns"


def legacy_bettercode_home_dir() -> Path:
    return Path.home() / ".bettercode"


def platform_app_support_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base_dir = Path(appdata).expanduser() if appdata else Path.home() / "AppData" / "Roaming"
        return base_dir / APP_NAME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base_dir = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return base_dir / APP_SLUG


def bettercode_home_dir(*, create: bool = True) -> Path:
    override_dir = os.environ.get("BETTERCODE_HOME")
    if override_dir:
        home_dir = Path(override_dir).expanduser().resolve()
    else:
        legacy_dir = legacy_bettercode_home_dir()
        home_dir = legacy_dir if legacy_dir.exists() else platform_app_support_dir()
    if create:
        home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


def app_state_path() -> Path:
    return bettercode_home_dir(create=True) / APP_STATE_FILENAME


def ensure_app_support_layout() -> Path:
    home_dir = bettercode_home_dir(create=True)
    state_path = app_state_path()
    payload = {
        "app_name": APP_NAME,
        "bundle_id": APP_BUNDLE_ID,
        "layout_version": APP_LAYOUT_VERSION,
        "version": __version__,
        "home_dir": str(home_dir),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    try:
        state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
    return home_dir


def macos_bundle_root() -> Path:
    return platform_app_support_dir() / f"{APP_NAME}.app"
