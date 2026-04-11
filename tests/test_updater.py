from bettercode import updater


def _manifest(version, macos_url="", windows_url="", linux_url="", release_url=""):
    return {
        "version": version,
        "release_name": f"BetterCode {version}",
        "release_url": release_url or f"https://codebetter.org/releases/{version}",
        "platforms": {
            "macos": macos_url,
            "windows": windows_url,
            "linux": linux_url,
        },
    }


def test_check_for_updates_reports_newer_release(monkeypatch):
    monkeypatch.setattr(
        updater,
        "fetch_update_manifest",
        lambda manifest_url=updater.DEFAULT_UPDATE_MANIFEST_URL, timeout=updater.UPDATE_CHECK_TIMEOUT_SECONDS: _manifest(
            "0.2.0",
            macos_url="https://codebetter.org/releases/0.2.0/BetterCode-0.2.0.dmg",
        ),
    )

    payload = updater.check_for_updates(current_version="0.1.0", platform_name="darwin")

    assert payload["update_available"] is True
    assert payload["latest_version"] == "0.2.0"
    assert payload["asset_name"] == "BetterCode-0.2.0.dmg"
    assert payload["source"] == "manifest"


def test_check_for_updates_reports_no_update_when_versions_match(monkeypatch):
    monkeypatch.setattr(
        updater,
        "fetch_update_manifest",
        lambda manifest_url=updater.DEFAULT_UPDATE_MANIFEST_URL, timeout=updater.UPDATE_CHECK_TIMEOUT_SECONDS: _manifest("0.1.0"),
    )

    payload = updater.check_for_updates(current_version="0.1.0", platform_name="linux")

    assert payload["update_available"] is False
    assert payload["latest_version"] == "0.1.0"


def test_check_for_updates_handles_missing_version(monkeypatch):
    monkeypatch.setattr(
        updater,
        "fetch_update_manifest",
        lambda manifest_url=updater.DEFAULT_UPDATE_MANIFEST_URL, timeout=updater.UPDATE_CHECK_TIMEOUT_SECONDS: {"platforms": {}},
    )

    payload = updater.check_for_updates(current_version="0.1.0", platform_name="linux")

    assert payload["update_available"] is False
    assert "version" in payload["error"].lower()


def test_check_for_updates_handles_network_error(monkeypatch):
    from urllib.error import URLError

    def _raise(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(updater, "fetch_update_manifest", _raise)

    payload = updater.check_for_updates(current_version="0.1.0")

    assert payload["update_available"] is False
    assert payload["error"] != ""


def test_check_for_updates_picks_correct_platform_url(monkeypatch):
    monkeypatch.setattr(
        updater,
        "fetch_update_manifest",
        lambda manifest_url=updater.DEFAULT_UPDATE_MANIFEST_URL, timeout=updater.UPDATE_CHECK_TIMEOUT_SECONDS: _manifest(
            "0.2.0",
            macos_url="https://codebetter.org/releases/BetterCode.dmg",
            windows_url="https://codebetter.org/releases/BetterCode-Setup.exe",
            linux_url="https://codebetter.org/releases/BetterCode.AppImage",
        ),
    )

    mac = updater.check_for_updates(current_version="0.1.0", platform_name="darwin")
    win = updater.check_for_updates(current_version="0.1.0", platform_name="windows")
    lin = updater.check_for_updates(current_version="0.1.0", platform_name="linux")

    assert mac["asset_name"] == "BetterCode.dmg"
    assert win["asset_name"] == "BetterCode-Setup.exe"
    assert lin["asset_name"] == "BetterCode.AppImage"


def test_check_for_updates_reads_checksum_from_platform_entry(monkeypatch):
    monkeypatch.setattr(
        updater,
        "fetch_update_manifest",
        lambda manifest_url=updater.DEFAULT_UPDATE_MANIFEST_URL, timeout=updater.UPDATE_CHECK_TIMEOUT_SECONDS: {
            "version": "0.2.0",
            "platforms": {
                "macos": {
                    "download_url": "https://codebetter.org/releases/0.2.0/BetterCode-0.2.0.dmg",
                    "asset_name": "BetterCode-0.2.0.dmg",
                    "sha256": "A" * 64,
                },
            },
        },
    )

    payload = updater.check_for_updates(current_version="0.1.0", platform_name="darwin")

    assert payload["update_available"] is True
    assert payload["download_url"] == "https://codebetter.org/releases/0.2.0/BetterCode-0.2.0.dmg"
    assert payload["asset_name"] == "BetterCode-0.2.0.dmg"
    assert payload["sha256"] == "a" * 64
