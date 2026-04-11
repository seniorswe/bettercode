import json
from pathlib import Path

import bettercode.packaging as packaging


def test_build_pyinstaller_command_for_macos_contains_bundle_metadata():
    command = packaging.build_pyinstaller_command("macos")

    assert command[0] == "pyinstaller"
    assert "--windowed" in command
    assert "--osx-bundle-identifier" in command
    assert packaging.APP_BUNDLE_ID in command
    assert str(packaging.ENTRYPOINT_PATH) == command[-1]


def test_build_pyinstaller_command_for_windows_uses_windows_data_separator():
    command = packaging.build_pyinstaller_command("windows")
    add_data_index = command.index("--add-data") + 1

    assert ";" in command[add_data_index]
    assert packaging.platform_bundle_name("windows") == "BetterCode.exe"


def test_build_pyinstaller_command_includes_qtwebengine_dictionaries_when_available(monkeypatch):
    dictionaries_dir = packaging.PROJECT_ROOT / "qtwebengine_dictionaries"
    monkeypatch.setattr(packaging, "_qtwebengine_dictionaries_dir", lambda: dictionaries_dir)

    command = packaging.build_pyinstaller_command("linux")
    add_data_entries = [command[index + 1] for index, value in enumerate(command) if value == "--add-data"]

    assert f"{dictionaries_dir}:qtwebengine_dictionaries" in add_data_entries


def test_platform_icon_path_for_linux_falls_back_to_embedded_png():
    icon_path = packaging.platform_icon_path("linux")

    assert icon_path == packaging.APP_ICON_PNG_PATH
    assert icon_path.exists() is True


def test_write_build_plan_writes_json_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(packaging, "BUILD_ROOT", tmp_path / "build")
    monkeypatch.setattr(packaging, "DIST_ROOT", tmp_path / "dist")

    plan_path = packaging.write_build_plan("linux")
    payload = json.loads(plan_path.read_text(encoding="utf-8"))

    assert plan_path == tmp_path / "build" / "linux" / "build-plan.json"
    assert payload["platform"] == "linux"
    assert payload["bundle_name"] == packaging.platform_bundle_name("linux")
    assert payload["dist_dir"] == str(tmp_path / "dist" / "linux")


def test_package_desktop_dry_run_returns_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(packaging, "BUILD_ROOT", tmp_path / "build")
    monkeypatch.setattr(packaging, "DIST_ROOT", tmp_path / "dist")

    payload = packaging.package_desktop("linux", dry_run=True)

    assert payload["platform"] == "linux"
    assert payload["built"] is False
    assert Path(payload["plan_path"]).exists() is True
    assert Path(payload["manifest_path"]).exists() is True
    assert "validation" in payload


def test_packaging_validation_reports_required_checks(monkeypatch):
    monkeypatch.setattr(packaging, "ENTRYPOINT_PATH", packaging.PROJECT_ROOT / "bettercode" / "main.py")
    monkeypatch.setattr(packaging, "APP_ICON_PATH", packaging.PROJECT_ROOT / "bettercode" / "web" / "static" / "app-icon.svg")
    monkeypatch.setattr(packaging.shutil, "which", lambda command: "/usr/bin/pyinstaller" if command == "pyinstaller" else None)

    payload = packaging.packaging_validation_payload("linux")

    assert payload["platform"] == "linux"
    assert any(check["name"] == "entrypoint" and check["ok"] for check in payload["checks"])
    assert any(check["name"] == "svg_app_icon" and check["ok"] for check in payload["checks"])
    assert any(check["name"] == "pyinstaller" and check["ok"] for check in payload["checks"])


def test_write_release_manifest_writes_expected_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(packaging, "BUILD_ROOT", tmp_path / "build")
    monkeypatch.setattr(packaging, "DIST_ROOT", tmp_path / "dist")

    manifest_path = packaging.write_release_manifest("linux")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["app_name"] == packaging.APP_NAME
    assert payload["platform"] == "linux"
    assert payload["bundle_name"] == packaging.platform_bundle_name("linux")
