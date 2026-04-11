import subprocess
import sys
from pathlib import Path

from bettercode.web.desktop import (
    _app_icon_path,
    _ensure_linux_desktop_entry,
    _fallback_notification_command,
    _linux_desktop_file_id,
    _linux_desktop_file_name,
    _launch_detached_command,
    _normalize_html_filename,
    _qt_application_argv,
    _send_completion_notification,
    _start_selector_runtime_warmup,
    _should_show_completion_notification,
    _write_html_report,
    _warm_selector_runtime_best_effort,
)


def test_app_icon_path_points_to_static_icon():
    icon_path = _app_icon_path()

    expected_name = "app-icon-dark.png" if (sys.platform == "darwin" or sys.platform.startswith("linux")) else "app-icon.svg"
    assert icon_path.name == expected_name
    assert icon_path.exists() is True


def test_light_logo_variant_exists():
    light_logo_path = Path(__file__).resolve().parents[1] / "bettercode" / "web" / "static" / "app-icon-light.svg"

    assert light_logo_path.exists() is True


def test_linux_desktop_file_name_uses_slug_with_desktop_extension():
    assert _linux_desktop_file_name() == "bettercode.desktop"


def test_linux_desktop_file_id_uses_slug_without_extension():
    assert _linux_desktop_file_id() == "bettercode"


def test_ensure_linux_desktop_entry_writes_branded_launcher(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/bettercode"], raising=False)

    desktop_path = _ensure_linux_desktop_entry()

    assert desktop_path == tmp_path / "xdg" / "applications" / "bettercode.desktop"
    payload = desktop_path.read_text(encoding="utf-8")
    assert "Name=BetterCode" in payload
    assert "Icon=bettercode" in payload
    assert "StartupWMClass=BetterCode" in payload
    assert "Exec=/usr/local/bin/bettercode" in payload
    assert (tmp_path / "xdg" / "icons" / "hicolor" / "512x512" / "apps" / "bettercode.png").exists() is True


def test_qt_application_argv_rewrites_program_name():
    assert _qt_application_argv(["python", "-m", "bettercode.main"]) == ["BetterCode", "-m", "bettercode.main"]


def test_qt_application_argv_defaults_when_empty():
    assert _qt_application_argv([]) == ["BetterCode"]


def test_normalize_html_filename_adds_extension_and_strips_path():
    assert _normalize_html_filename("report") == "report.html"
    assert _normalize_html_filename("nested/review-output") == "review-output.html"
    assert _normalize_html_filename("done.HTML") == "done.HTML"


def test_write_html_report_forces_html_extension(tmp_path):
    target = tmp_path / "review-output"

    saved_path = _write_html_report(target, "<html><body>ok</body></html>")

    assert saved_path.endswith("review-output.html")
    assert Path(saved_path).read_text(encoding="utf-8") == "<html><body>ok</body></html>"


def test_should_show_completion_notification_only_when_window_not_effectively_open():
    assert _should_show_completion_notification(is_visible=True, is_minimized=False, is_active=True) is False
    assert _should_show_completion_notification(is_visible=False, is_minimized=False, is_active=False) is True
    assert _should_show_completion_notification(is_visible=True, is_minimized=True, is_active=False) is True
    assert _should_show_completion_notification(is_visible=True, is_minimized=False, is_active=False) is True


def test_fallback_notification_command_uses_osascript_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(
        "bettercode.web.desktop.shutil.which",
        lambda command: "/usr/bin/osascript" if command == "osascript" else None,
    )

    command = _fallback_notification_command("BetterCode", "Ready")

    assert command == [
        "/usr/bin/osascript",
        "-e",
        'display notification "Ready" with title "BetterCode"',
    ]


def test_fallback_notification_command_uses_notify_send_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setattr(
        "bettercode.web.desktop.shutil.which",
        lambda command: "/usr/bin/notify-send" if command == "notify-send" else None,
    )

    command = _fallback_notification_command("BetterCode", "Ready")

    assert command == [
        "/usr/bin/notify-send",
        "-a",
        "BetterCode",
        "-i",
        "bettercode",
        "-h",
        "string:desktop-entry:bettercode",
        "BetterCode",
        "Ready",
    ]


def test_fallback_notification_command_uses_powershell_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setattr(
        "bettercode.web.desktop.shutil.which",
        lambda command: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" if command in {"powershell", "powershell.exe"} else None,
    )

    command = _fallback_notification_command("BetterCode", "Ready")

    assert command is not None
    assert command[:3] == [
        "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
    ]
    assert "BalloonTipTitle = 'BetterCode'" in command[-1]
    assert "BalloonTipText = 'Ready'" in command[-1]


def test_fallback_notification_command_returns_none_without_supported_notifier(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setattr("bettercode.web.desktop.shutil.which", lambda command: None)

    assert _fallback_notification_command("BetterCode", "Ready") is None


def test_send_completion_notification_uses_fallback_when_tray_missing(monkeypatch):
    launched = {}
    monkeypatch.setattr("bettercode.web.desktop._fallback_notification_command", lambda title, message: ["notify-send", title, message])

    def fake_launch(command):
        launched["command"] = command
        return True

    monkeypatch.setattr("bettercode.web.desktop._launch_detached_command", fake_launch)

    result = _send_completion_notification(None, "BetterCode", "Ready")

    assert result is True
    assert launched["command"] == ["notify-send", "BetterCode", "Ready"]


def test_launch_detached_command_uses_new_process_group_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("bettercode.web.desktop.subprocess.Popen", fake_popen)

    assert _launch_detached_command(["cmd", "/c", "echo", "ok"]) is True
    assert captured["command"] == ["cmd", "/c", "echo", "ok"]
    assert captured["kwargs"]["creationflags"] == 512
    assert "start_new_session" not in captured["kwargs"]


def test_launch_detached_command_uses_new_session_on_posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("bettercode.web.desktop.subprocess.Popen", fake_popen)

    assert _launch_detached_command(["notify-send", "BetterCode", "Ready"]) is True
    assert captured["command"] == ["notify-send", "BetterCode", "Ready"]
    assert captured["kwargs"]["start_new_session"] is True
    assert "creationflags" not in captured["kwargs"]


def test_warm_selector_runtime_best_effort_returns_false_on_runtime_error(monkeypatch):
    monkeypatch.setattr(
        "bettercode.web.bootstrap.require_selector_runtime",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("selector missing")),
    )

    assert _warm_selector_runtime_best_effort() is False


def test_start_selector_runtime_warmup_spawns_daemon_thread(monkeypatch):
    captured = {}

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            captured["target"] = target
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr("bettercode.web.desktop.threading.Thread", FakeThread)

    _start_selector_runtime_warmup()

    assert captured["target"] is _warm_selector_runtime_best_effort
    assert captured["daemon"] is True
    assert captured["started"] is True
