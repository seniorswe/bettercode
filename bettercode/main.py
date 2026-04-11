import argparse
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import stat
import subprocess
import sys
import sysconfig

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - depends on local environment
    class Console:
        def print(self, *args, **kwargs):
            print(*args)

from bettercode import __version__
from bettercode.app_meta import APP_BUNDLE_ID, APP_ICNS_PATH, APP_NAME, ensure_app_support_layout, macos_bundle_root

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bettercode")
    parser.add_argument(
        "--dev",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--launched-from-app",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def _macos_bundle_root() -> Path:
    return macos_bundle_root()


def _escape_c_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_macos_embedded_launcher_source(python_executable: str, launch_cwd: str) -> str:
    app_name = _escape_c_string(APP_NAME)
    python_path = _escape_c_string(python_executable)
    cwd_path = _escape_c_string(launch_cwd)
    return "\n".join([
        "#include <Python.h>",
        "#include <stdlib.h>",
        "#include <stdio.h>",
        "#include <unistd.h>",
        "#include <wchar.h>",
        "",
        "int main(int argc, char **argv) {",
        f'    const char *python_executable = "{python_path}";',
        f'    const char *launch_cwd = "{cwd_path}";',
        f'    const char *app_name = "{app_name}";',
        "",
        '    setenv("BETTERCODE_MACOS_APP_LAUNCHED", "1", 1);',
        '    setenv("__PYVENV_LAUNCHER__", python_executable, 1);',
        '    setenv("PYTHONEXECUTABLE", python_executable, 1);',
        "    (void)chdir(launch_cwd);",
        "",
        "    wchar_t *program = Py_DecodeLocale(python_executable, NULL);",
        "    if (program == NULL) {",
        '        fprintf(stderr, "BetterCode launcher failed to decode Python path.\\n");',
        "        return 2;",
        "    }",
        "",
        "    Py_SetProgramName(program);",
        "",
        "    int child_argc = argc + 3;",
        "    char **child_argv = calloc((size_t)child_argc + 1, sizeof(char *));",
        "    if (child_argv == NULL) {",
        '        fprintf(stderr, "BetterCode launcher failed to allocate argv.\\n");',
        "        PyMem_RawFree(program);",
        "        return 3;",
        "    }",
        "",
        "    child_argv[0] = (char *)app_name;",
        '    child_argv[1] = "-m";',
        '    child_argv[2] = "bettercode.main";',
        '    child_argv[3] = "--launched-from-app";',
        "    for (int i = 1; i < argc; ++i) {",
        "        child_argv[i + 3] = argv[i];",
        "    }",
        "",
        "    int status = Py_BytesMain(child_argc, child_argv);",
        "    free(child_argv);",
        "    PyMem_RawFree(program);",
        "    return status;",
        "}",
        "",
    ])


def _macos_launcher_compile_command(source_path: Path, launcher_path: Path) -> list[str]:
    clang_path = shutil.which("clang") or shutil.which("cc")
    include_dir = sysconfig.get_config_var("INCLUDEPY")
    link_for_shared = shlex.split(sysconfig.get_config_var("LINKFORSHARED") or "")
    libs = shlex.split(sysconfig.get_config_var("LIBS") or "")
    syslibs = shlex.split(sysconfig.get_config_var("SYSLIBS") or "")
    if not clang_path or not include_dir:
        raise RuntimeError("macOS launcher build prerequisites unavailable")
    return [
        clang_path,
        "-Os",
        "-Wno-deprecated-declarations",
        "-I",
        str(include_dir),
        "-o",
        str(launcher_path),
        str(source_path),
        *link_for_shared,
        *libs,
        *syslibs,
    ]


def _write_macos_shell_launcher(launcher_path: Path, launch_cwd: str, python_executable: str) -> None:
    launcher_path.write_text(
        "\n".join([
            "#!/bin/bash",
            "export BETTERCODE_MACOS_APP_LAUNCHED=1",
            f"cd {shlex.quote(launch_cwd)}",
            f'exec -a {shlex.quote(APP_NAME)} {shlex.quote(python_executable)} -m bettercode.main --launched-from-app "$@"',
            "",
        ]),
        encoding="utf-8",
    )
    launcher_path.chmod(
        launcher_path.stat().st_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


def _write_macos_native_launcher(launcher_path: Path, source_path: Path, launch_cwd: str, python_executable: str) -> bool:
    source_path.write_text(
        _build_macos_embedded_launcher_source(python_executable, launch_cwd),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            _macos_launcher_compile_command(source_path, launcher_path),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _ensure_macos_app_bundle(cwd: str | None = None) -> Path:
    bundle_root = _macos_bundle_root()
    contents_dir = bundle_root / "Contents"
    macos_dir = contents_dir / "MacOS"
    contents_dir.mkdir(parents=True, exist_ok=True)
    macos_dir.mkdir(parents=True, exist_ok=True)

    launch_cwd = cwd or os.getcwd()
    launcher_path = macos_dir / APP_NAME

    resources_dir = contents_dir / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    launcher_source_path = resources_dir / "bettercode-launcher.c"
    if not _write_macos_native_launcher(launcher_path, launcher_source_path, launch_cwd, sys.executable):
        _write_macos_shell_launcher(launcher_path, launch_cwd, sys.executable)
    # Only copy the .icns if it's a proper multi-resolution file (>20 KB).
    # The source was historically a 4 KB stub that rendered as transparent in
    # the Dock; guard against that here so a bad file never overwrites a good one.
    if APP_ICNS_PATH.exists() and APP_ICNS_PATH.stat().st_size > 20_000:
        shutil.copy2(APP_ICNS_PATH, resources_dir / APP_ICNS_PATH.name)
    elif APP_ICNS_PATH.exists() and APP_ICNS_PATH.stat().st_size <= 20_000:
        # Silently skip — the bundle may already have a valid icon from a
        # previous run; don't overwrite it with a stub.
        pass

    plist_path = contents_dir / "Info.plist"
    with plist_path.open("wb") as handle:
        plistlib.dump(
            {
                "CFBundleDevelopmentRegion": "en",
                "CFBundleDisplayName": APP_NAME,
                "CFBundleExecutable": APP_NAME,
                "CFBundleIconFile": APP_ICNS_PATH.stem,
                "CFBundleIdentifier": APP_BUNDLE_ID,
                "CFBundleInfoDictionaryVersion": "6.0",
                "CFBundleName": APP_NAME,
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": __version__,
                "CFBundleVersion": __version__,
                "LSMinimumSystemVersion": "11.0",
                "NSHighResolutionCapable": True,
            },
            handle,
        )

    return bundle_root


def _relaunch_macos_app_if_needed(args: argparse.Namespace) -> bool:
    if sys.platform != "darwin":
        return False
    if args.launched_from_app or os.environ.get("BETTERCODE_MACOS_APP_LAUNCHED") == "1":
        return False

    open_path = shutil.which("open")
    if not open_path:
        return False

    bundle_root = _ensure_macos_app_bundle()
    command = [open_path, "-W", "-n", str(bundle_root), "--args"]
    if args.dev:
        command.append("--dev")
    try:
        subprocess.run(command, check=True)
        return True
    except KeyboardInterrupt:
        osascript_path = shutil.which("osascript")
        if osascript_path:
            try:
                subprocess.run(
                    [osascript_path, "-e", f'tell application id "{APP_BUNDLE_ID}" to quit'],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        raise
    except Exception:
        return False


def main(argv: list[str] | None = None):
    args = _build_parser().parse_args(argv)
    dev_mode = args.dev or os.environ.get("BETTERCODE_DEV") == "1"
    ensure_app_support_layout()

    if _relaunch_macos_app_if_needed(args):
        return

    console.print("[bold green]Welcome to bettercode![/bold green]", justify="center")
    console.print("Starting Application", justify="center")
    try:
        from bettercode.router.selector import bootstrap_selector_runtime

        bootstrap_selector_runtime(log_fn=lambda msg: console.print(f"  {msg}"))

        from bettercode.web.desktop import run_desktop_app

        run_desktop_app(dev_mode=dev_mode)
    except ModuleNotFoundError as exc:
        console.print(f"\n[bold red]Fatal Desktop Runtime Error:[/bold red] {exc}")
        console.print("Install the desktop web runtime with `PyQt6` and `PyQt6-WebEngine` in the active environment.")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[bold red]Fatal App Error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
