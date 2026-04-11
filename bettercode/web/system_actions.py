import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys

from fastapi import HTTPException


def build_terminal_command(inner_command: list[str], runtime_terminals: tuple[str, ...]) -> list[str]:
    shell_command = shlex.join(inner_command)
    if sys.platform == "darwin":
        osascript_path = shutil.which("osascript")
        if osascript_path:
            apple_script_command = shell_command.replace("\\", "\\\\").replace('"', '\\"')
            return [
                osascript_path,
                "-e",
                'tell application "Terminal"',
                "-e",
                "activate",
                "-e",
                f'do script "{apple_script_command}"',
                "-e",
                "end tell",
            ]

    if os.name == "nt":
        shell_path = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or shutil.which("cmd")
        if shell_path:
            return [shell_path, "/c", "start", '""', shell_path, "/k", subprocess.list2cmdline(inner_command)]

    persistent_shell_command = (
        f"{shell_command}; "
        "printf '\\nBetterCode: runtime login command finished.\\n'; "
        "exec bash -i"
    )
    for terminal_name in runtime_terminals:
        terminal_path = shutil.which(terminal_name)
        if not terminal_path:
            continue

        basename = Path(terminal_path).name
        if basename == "gnome-terminal":
            return [terminal_path, "--", "bash", "-lc", persistent_shell_command]
        if basename == "konsole":
            return [terminal_path, "-e", "bash", "-lc", persistent_shell_command]
        if basename == "wezterm":
            return [terminal_path, "start", "--", "bash", "-lc", persistent_shell_command]
        return [terminal_path, "-e", "bash", "-lc", persistent_shell_command]

    raise HTTPException(status_code=400, detail="No supported terminal emulator is available for runtime login.")


def launch_detached_command(command: list[str], workspace_path: str | None = None) -> None:
    popen_kwargs: dict = {
        "cwd": workspace_path or os.getcwd(),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, **popen_kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Required command is not installed: {command[0]}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to launch command: {exc}") from exc


def open_with_system_default(path: Path, launch_fn=launch_detached_command):
    path_str = str(path)
    if sys.platform == "darwin":
        opener = shutil.which("open")
        if not opener:
            raise HTTPException(status_code=500, detail="No supported file opener is available in this environment.")
        launch_fn([opener, path_str])
        return

    if os.name == "nt":
        shell_path = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or shutil.which("cmd")
        if not shell_path:
            raise HTTPException(status_code=500, detail="No supported file opener is available in this environment.")
        launch_fn([shell_path, "/c", "start", '""', path_str])
        return

    opener = shutil.which("xdg-open")
    if opener:
        launch_fn([opener, path_str])
        return

    gio = shutil.which("gio")
    if gio:
        launch_fn([gio, "open", path_str])
        return

    raise HTTPException(status_code=500, detail="No supported file opener is available in this environment.")


def kill_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return

    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
