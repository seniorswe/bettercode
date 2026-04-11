import json

import bettercode.app_meta as app_meta


def test_bettercode_home_dir_uses_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-home"
    monkeypatch.setenv("BETTERCODE_HOME", str(override))

    assert app_meta.bettercode_home_dir() == override.resolve()


def test_bettercode_home_dir_prefers_legacy_dir_when_present(monkeypatch, tmp_path):
    legacy_dir = tmp_path / ".bettercode"
    legacy_dir.mkdir()
    monkeypatch.delenv("BETTERCODE_HOME", raising=False)
    monkeypatch.setattr(app_meta.Path, "home", lambda: tmp_path)

    assert app_meta.bettercode_home_dir() == legacy_dir


def test_platform_app_support_dir_uses_platform_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(app_meta.Path, "home", lambda: tmp_path)

    monkeypatch.setattr(app_meta.sys, "platform", "darwin", raising=False)
    assert app_meta.platform_app_support_dir() == tmp_path / "Library" / "Application Support" / app_meta.APP_NAME

    monkeypatch.setattr(app_meta.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(app_meta.os, "name", "posix", raising=False)
    assert app_meta.platform_app_support_dir() == tmp_path / ".local" / "share" / app_meta.APP_SLUG

    monkeypatch.setattr(app_meta.sys, "platform", "win32", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    assert app_meta.platform_app_support_dir() == tmp_path / "AppData" / "Roaming" / app_meta.APP_NAME


def test_ensure_app_support_layout_writes_app_state(monkeypatch, tmp_path):
    override = tmp_path / "bettercode-home"
    monkeypatch.setenv("BETTERCODE_HOME", str(override))

    home_dir = app_meta.ensure_app_support_layout()
    payload = json.loads((override / app_meta.APP_STATE_FILENAME).read_text(encoding="utf-8"))

    assert home_dir == override.resolve()
    assert payload["app_name"] == app_meta.APP_NAME
    assert payload["bundle_id"] == app_meta.APP_BUNDLE_ID
    assert payload["layout_version"] == app_meta.APP_LAYOUT_VERSION
    assert payload["home_dir"] == str(override.resolve())
