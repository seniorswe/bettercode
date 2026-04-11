import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from bettercode import __version__


DEFAULT_UPDATE_MANIFEST_URL = (
    os.environ.get("BETTERCODE_UPDATE_URL", "https://codebetter.org/updates/latest.json").strip()
    or "https://codebetter.org/updates/latest.json"
)
UPDATE_CHECK_TIMEOUT_SECONDS = 4.0
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def normalize_update_platform(platform_name: str | None = None) -> str:
    value = (platform_name or sys.platform).strip().lower()
    if value.startswith("darwin") or value.startswith("mac"):
        return "macos"
    if value.startswith("win"):
        return "windows"
    return "linux"


def normalize_version_tag(tag: str) -> str:
    value = str(tag or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value


def normalize_sha256(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if SHA256_RE.fullmatch(normalized) else ""


def version_key(version: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", normalize_version_tag(version))]
    return tuple(parts or [0])


def is_newer_version(latest_version: str, current_version: str) -> bool:
    return version_key(latest_version) > version_key(current_version)


def fetch_update_manifest(
    manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
    timeout: float = UPDATE_CHECK_TIMEOUT_SECONDS,
) -> dict:
    """Fetch the update manifest from codebetter.org (or override URL).

    Expected manifest format::

        {
          "version": "0.2.0",
          "release_name": "BetterCode 0.2.0",
          "release_url": "https://github.com/seniorswe/bettercode/releases/tag/v0.2.0",
          "platforms": {
            "macos":   "https://.../BetterCode-0.2.0.dmg",
            "windows": "https://.../BetterCode-Setup-0.2.0.exe",
            "linux":   "https://.../BetterCode-0.2.0.AppImage"
          }
        }
    """
    request = Request(
        manifest_url,
        headers={"User-Agent": f"BetterCode/{__version__}"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_updates(
    *,
    current_version: str = __version__,
    manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
    platform_name: str | None = None,
    timeout: float = UPDATE_CHECK_TIMEOUT_SECONDS,
) -> dict:
    normalized_platform = normalize_update_platform(platform_name)
    payload = {
        "source": "manifest",
        "manifest_url": manifest_url,
        "channel": "stable",
        "platform": normalized_platform,
        "current_version": current_version,
        "checked_at": datetime.now(UTC).isoformat(),
        "update_available": False,
        "latest_version": None,
        "release_name": "",
        "release_url": "",
        "download_url": "",
        "asset_name": "",
        "sha256": "",
        "error": "",
    }

    try:
        manifest = fetch_update_manifest(manifest_url, timeout=timeout)
        latest_version = normalize_version_tag(str(manifest.get("version") or ""))
        if not latest_version:
            payload["error"] = "Manifest missing 'version' field."
            return payload
        platforms: dict = manifest.get("platforms") or {}
        platform_entry = platforms.get(normalized_platform) or {}
        checksums = manifest.get("checksums") or {}
        download_url = ""
        asset_name = ""
        sha256 = ""
        if isinstance(platform_entry, dict):
            download_url = str(platform_entry.get("url") or platform_entry.get("download_url") or "").strip()
            asset_name = Path(str(platform_entry.get("asset_name") or "")).name.strip()
            sha256 = normalize_sha256(platform_entry.get("sha256"))
        else:
            download_url = str(platform_entry or "").strip()
        if not sha256 and isinstance(checksums, dict):
            sha256 = normalize_sha256(checksums.get(normalized_platform))
        if not asset_name and download_url:
            asset_name = download_url.rsplit("/", 1)[-1]
        payload.update(
            {
                "latest_version": latest_version,
                "release_name": str(manifest.get("release_name") or "").strip(),
                "release_url": str(manifest.get("release_url") or "").strip(),
                "download_url": download_url,
                "asset_name": asset_name,
                "sha256": sha256,
            }
        )
        if is_newer_version(latest_version, current_version):
            payload["update_available"] = True
        return payload
    except URLError as exc:
        payload["error"] = str(exc.reason or exc)
        return payload
    except Exception as exc:
        payload["error"] = str(exc)
        return payload
