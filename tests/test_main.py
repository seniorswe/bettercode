from unittest.mock import Mock
import plistlib

import bettercode.main as main_module


def test_build_parser_defaults():
    args = main_module._build_parser().parse_args([])

    assert args.dev is False
    assert args.launched_from_app is False


def test_build_parser_dev_flag():
    args = main_module._build_parser().parse_args(["--dev"])

    assert args.dev is True
    assert args.launched_from_app is False


def test_build_parser_launched_from_app_flag():
    args = main_module._build_parser().parse_args(["--launched-from-app"])

    assert args.dev is False
    assert args.launched_from_app is True


def test_macos_bundle_root_delegates_to_app_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "macos_bundle_root", lambda: tmp_path / "BetterCode.app")

    assert main_module._macos_bundle_root() == tmp_path / "BetterCode.app"


def test_main_launches_desktop_web_app(monkeypatch):
    runner = Mock()

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)

    main_module.main([])

    runner.assert_called_once_with(dev_mode=False)


def test_main_enables_dev_mode(monkeypatch):
    runner = Mock()

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)

    main_module.main(["--dev"])

    runner.assert_called_once_with(dev_mode=True)


def test_main_enables_dev_mode_from_environment(monkeypatch):
    runner = Mock()

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)
    monkeypatch.setenv("BETTERCODE_DEV", "1")

    main_module.main([])

    runner.assert_called_once_with(dev_mode=True)


def test_main_reports_desktop_runtime_errors(monkeypatch):
    def fail():
        raise RuntimeError("Missing system library 'libxcb-cursor0'")

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", fail)

    try:
        main_module.main([])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit")


def test_main_reports_missing_desktop_runtime_import(monkeypatch):
    def fail(**kwargs):
        raise ModuleNotFoundError("No module named 'PyQt6'")

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", fail)

    try:
        main_module.main([])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit")


def test_main_returns_early_after_macos_relaunch(monkeypatch):
    runner = Mock()
    ensure_layout = Mock()

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: True)
    monkeypatch.setattr(main_module, "ensure_app_support_layout", ensure_layout)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)

    main_module.main([])

    ensure_layout.assert_called_once_with()
    runner.assert_not_called()


def test_main_relaunches_via_macos_app_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.delenv("BETTERCODE_MACOS_APP_LAUNCHED", raising=False)
    monkeypatch.setattr(main_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(main_module.sys, "executable", "/tmp/venv/bin/python", raising=False)
    monkeypatch.setattr(main_module.shutil, "which", lambda command: "/usr/bin/open" if command == "open" else None)
    opened = {}

    def fake_run(command, check):
        opened["command"] = command
        opened["check"] = check

    monkeypatch.setattr(main_module.subprocess, "run", fake_run)
    runner = Mock()
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)

    main_module.main(["--dev"])

    runner.assert_not_called()
    assert opened["check"] is True
    assert opened["command"][:4] == ["/usr/bin/open", "-W", "-n", str(tmp_path / "Library" / "Application Support" / "BetterCode" / "BetterCode.app")]
    assert opened["command"][-2:] == ["--args", "--dev"]


def test_ensure_macos_app_bundle_writes_launcher_and_plist(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(main_module.sys, "executable", "/tmp/venv/bin/python", raising=False)
    captured = {}

    def fake_write_native_launcher(launcher_path, source_path, launch_cwd, python_executable):
        captured["launcher_path"] = launcher_path
        captured["source_path"] = source_path
        captured["launch_cwd"] = launch_cwd
        captured["python_executable"] = python_executable
        source_path.write_text("/* launcher source */", encoding="utf-8")
        launcher_path.write_bytes(b"launcher")
        return True

    monkeypatch.setattr(main_module, "_write_macos_native_launcher", fake_write_native_launcher)

    bundle_root = main_module._ensure_macos_app_bundle(cwd="/tmp/project")

    launcher = bundle_root / "Contents" / "MacOS" / "BetterCode"
    plist_path = bundle_root / "Contents" / "Info.plist"
    launcher_source = bundle_root / "Contents" / "Resources" / "bettercode-launcher.c"

    assert launcher.exists() is True
    assert launcher.read_bytes() == b"launcher"
    assert launcher_source.read_text(encoding="utf-8") == "/* launcher source */"
    assert captured["launcher_path"] == launcher
    assert captured["source_path"] == launcher_source
    assert captured["launch_cwd"] == "/tmp/project"
    assert captured["python_executable"] == "/tmp/venv/bin/python"

    with plist_path.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["CFBundleName"] == "BetterCode"
    assert payload["CFBundleDisplayName"] == "BetterCode"
    assert payload["CFBundleExecutable"] == "BetterCode"


def test_build_macos_embedded_launcher_source_contains_python_entrypoint():
    source = main_module._build_macos_embedded_launcher_source("/tmp/venv/bin/python", "/tmp/project")

    assert 'setenv("BETTERCODE_MACOS_APP_LAUNCHED", "1", 1);' in source
    assert 'setenv("__PYVENV_LAUNCHER__", python_executable, 1);' in source
    assert 'Py_SetProgramName(program);' in source
    assert 'Py_BytesMain(child_argc, child_argv);' in source
    assert 'const char *launch_cwd = "/tmp/project";' in source
    assert 'const char *python_executable = "/tmp/venv/bin/python";' in source


def test_ensure_macos_app_bundle_copies_icns_when_present(monkeypatch, tmp_path):
    fake_icns = tmp_path / "bettercode.icns"
    # Must be >20 KB to pass the stub-guard in _ensure_macos_app_bundle that
    # prevents tiny/corrupted ICNS files from overwriting a good bundle icon.
    fake_icns.write_bytes(b"icns" + b"\x00" * 21_000)
    monkeypatch.setattr(main_module, "_macos_bundle_root", lambda: tmp_path / "BetterCode.app")
    monkeypatch.setattr(main_module, "APP_NAME", "BetterCode")
    monkeypatch.setattr(main_module, "APP_ICNS_PATH", fake_icns)
    monkeypatch.setattr(main_module.sys, "executable", "/tmp/venv/bin/python", raising=False)
    monkeypatch.setattr(
        main_module,
        "_write_macos_native_launcher",
        lambda launcher_path, source_path, launch_cwd, python_executable: (launcher_path.write_bytes(b"launcher"), True)[1],
    )

    bundle_root = main_module._ensure_macos_app_bundle(cwd="/tmp/project")

    copied = bundle_root / "Contents" / "Resources" / "bettercode.icns"
    assert copied.exists()
    assert copied.read_bytes() == fake_icns.read_bytes()


def test_main_calls_ensure_app_support_layout_on_normal_path(monkeypatch):
    ensure_layout = Mock()
    runner = Mock()

    monkeypatch.setattr(main_module, "_relaunch_macos_app_if_needed", lambda args: False)
    monkeypatch.setattr(main_module, "ensure_app_support_layout", ensure_layout)
    monkeypatch.setattr("bettercode.router.selector.bootstrap_selector_runtime", lambda **kwargs: None)
    monkeypatch.setattr("bettercode.web.desktop.run_desktop_app", runner)

    main_module.main([])

    ensure_layout.assert_called_once_with()


def test_ensure_macos_app_bundle_uses_current_working_directory_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "_macos_bundle_root", lambda: tmp_path / "BetterCode.app")
    monkeypatch.setattr(main_module, "APP_NAME", "BetterCode")
    monkeypatch.setattr(main_module.sys, "executable", "/tmp/venv/bin/python", raising=False)
    monkeypatch.setattr(main_module.os, "getcwd", lambda: "/tmp/current-project")
    captured = {}

    def fake_write_native_launcher(launcher_path, source_path, launch_cwd, python_executable):
        captured["launch_cwd"] = launch_cwd
        launcher_path.write_bytes(b"launcher")
        return True

    monkeypatch.setattr(main_module, "_write_macos_native_launcher", fake_write_native_launcher)

    main_module._ensure_macos_app_bundle()

    assert captured["launch_cwd"] == "/tmp/current-project"


def test_relaunch_macos_app_if_needed_skips_when_not_macos(monkeypatch):
    args = main_module._build_parser().parse_args([])

    monkeypatch.setattr(main_module.sys, "platform", "linux", raising=False)

    assert main_module._relaunch_macos_app_if_needed(args) is False


def test_relaunch_macos_app_if_needed_skips_when_already_in_app(monkeypatch):
    args = main_module._build_parser().parse_args(["--launched-from-app"])

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)

    assert main_module._relaunch_macos_app_if_needed(args) is False


def test_relaunch_macos_app_if_needed_skips_when_marked_from_environment(monkeypatch):
    args = main_module._build_parser().parse_args([])

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.setenv("BETTERCODE_MACOS_APP_LAUNCHED", "1")

    assert main_module._relaunch_macos_app_if_needed(args) is False


def test_relaunch_macos_app_if_needed_skips_without_open(monkeypatch):
    args = main_module._build_parser().parse_args([])

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.delenv("BETTERCODE_MACOS_APP_LAUNCHED", raising=False)
    monkeypatch.setattr(main_module.shutil, "which", lambda command: None)

    assert main_module._relaunch_macos_app_if_needed(args) is False


def test_relaunch_macos_app_if_needed_returns_false_on_subprocess_error(monkeypatch, tmp_path):
    args = main_module._build_parser().parse_args([])

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.delenv("BETTERCODE_MACOS_APP_LAUNCHED", raising=False)
    monkeypatch.setattr(main_module, "_ensure_macos_app_bundle", lambda cwd=None: tmp_path / "BetterCode.app")
    monkeypatch.setattr(main_module.shutil, "which", lambda command: "/usr/bin/open" if command == "open" else None)

    def fail(command, check):
        raise RuntimeError("open failed")

    monkeypatch.setattr(main_module.subprocess, "run", fail)

    assert main_module._relaunch_macos_app_if_needed(args) is False


def test_relaunch_macos_app_if_needed_returns_true_on_success(monkeypatch, tmp_path):
    args = main_module._build_parser().parse_args([])
    calls = []

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.delenv("BETTERCODE_MACOS_APP_LAUNCHED", raising=False)
    monkeypatch.setattr(main_module, "_ensure_macos_app_bundle", lambda cwd=None: tmp_path / "BetterCode.app")
    monkeypatch.setattr(main_module.shutil, "which", lambda command: "/usr/bin/open" if command == "open" else None)
    monkeypatch.setattr(main_module.subprocess, "run", lambda command, check: calls.append((command, check)))

    assert main_module._relaunch_macos_app_if_needed(args) is True
    assert calls == [(["/usr/bin/open", "-W", "-n", str(tmp_path / "BetterCode.app"), "--args"], True)]


def test_relaunch_macos_app_if_needed_quits_app_on_keyboard_interrupt(monkeypatch, tmp_path):
    args = main_module._build_parser().parse_args([])
    calls = []

    monkeypatch.setattr(main_module.sys, "platform", "darwin", raising=False)
    monkeypatch.delenv("BETTERCODE_MACOS_APP_LAUNCHED", raising=False)
    monkeypatch.setattr(main_module, "_ensure_macos_app_bundle", lambda cwd=None: tmp_path / "BetterCode.app")
    monkeypatch.setattr(
        main_module.shutil,
        "which",
        lambda command: "/usr/bin/open" if command == "open" else "/usr/bin/osascript" if command == "osascript" else None,
    )

    def fake_run(command, check, stdout=None, stderr=None):
        calls.append(command)
        if command[0] == "/usr/bin/open":
            raise KeyboardInterrupt
        return None

    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    try:
        main_module._relaunch_macos_app_if_needed(args)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("Expected KeyboardInterrupt")

    assert calls == [
        ["/usr/bin/open", "-W", "-n", str(tmp_path / "BetterCode.app"), "--args"],
        ["/usr/bin/osascript", "-e", f'tell application id "{main_module.APP_BUNDLE_ID}" to quit'],
    ]


def test_run_desktop_app_starts_selector_warmup_before_qt_import(monkeypatch):
    import bettercode.web.desktop as desktop

    calls = {"warmup": 0}
    monkeypatch.setattr(desktop, "_check_linux_qt_prereqs", lambda: None)
    monkeypatch.setattr(desktop, "_start_selector_runtime_warmup", lambda: calls.__setitem__("warmup", calls["warmup"] + 1))
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("PyQt6"):
            raise ModuleNotFoundError("PyQt6 missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    try:
        desktop.run_desktop_app()
    except ModuleNotFoundError as exc:
        assert str(exc) == "PyQt6 missing"
    else:
        raise AssertionError("Expected ModuleNotFoundError")

    assert calls["warmup"] == 1
