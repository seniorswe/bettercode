import queue
import subprocess
import threading
import time


ACTIVE_CHAT_PROCESSES: dict[int, subprocess.Popen] = {}
ACTIVE_CHAT_PROCESSES_LOCK = threading.Lock()
ACTIVE_CHAT_PROCESS_META: dict[int, dict] = {}
ACTIVE_CHAT_PROCESS_META_LOCK = threading.Lock()
PENDING_CHAT_INPUT: dict[int, "queue.Queue[str]"] = {}
PENDING_CHAT_INPUT_LOCK = threading.Lock()


def wait_for_chat_input(workspace_id: int, timeout: float = 300.0) -> str | None:
    q: queue.Queue[str] = queue.Queue()
    with PENDING_CHAT_INPUT_LOCK:
        PENDING_CHAT_INPUT[workspace_id] = q
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return None
    finally:
        with PENDING_CHAT_INPUT_LOCK:
            PENDING_CHAT_INPUT.pop(workspace_id, None)


def register_active_chat_process(workspace_id: int, process: subprocess.Popen, runtime: str) -> None:
    with ACTIVE_CHAT_PROCESSES_LOCK:
        ACTIVE_CHAT_PROCESSES[workspace_id] = process
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        ACTIVE_CHAT_PROCESS_META[workspace_id] = {
            "started_at": time.monotonic(),
            "last_output_at": time.monotonic(),
            "input_waiting": False,
            "stop_requested": False,
            "runtime": runtime,
            "pid": process.pid,
        }


def clear_active_chat_process(workspace_id: int) -> None:
    with ACTIVE_CHAT_PROCESSES_LOCK:
        ACTIVE_CHAT_PROCESSES.pop(workspace_id, None)
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        ACTIVE_CHAT_PROCESS_META.pop(workspace_id, None)
    with PENDING_CHAT_INPUT_LOCK:
        PENDING_CHAT_INPUT.pop(workspace_id, None)


def touch_active_chat_process(workspace_id: int | None) -> None:
    if workspace_id is None:
        return
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        meta = ACTIVE_CHAT_PROCESS_META.get(workspace_id)
        if meta is not None:
            meta["last_output_at"] = time.monotonic()


def set_chat_input_waiting(workspace_id: int | None, waiting: bool) -> None:
    if workspace_id is None:
        return
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        meta = ACTIVE_CHAT_PROCESS_META.get(workspace_id)
        if meta is not None:
            meta["input_waiting"] = bool(waiting)
            if not waiting:
                meta["last_output_at"] = time.monotonic()


def request_chat_stop(workspace_id: int) -> None:
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        meta = ACTIVE_CHAT_PROCESS_META.get(workspace_id)
        if meta is not None:
            meta["stop_requested"] = True


def chat_stop_requested(workspace_id: int | None) -> bool:
    if workspace_id is None:
        return False
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        meta = ACTIVE_CHAT_PROCESS_META.get(workspace_id)
        return bool(meta and meta.get("stop_requested"))


def active_chat_status_payload(workspace_id: int, stall_warning_seconds: float) -> dict:
    with ACTIVE_CHAT_PROCESSES_LOCK:
        process = ACTIVE_CHAT_PROCESSES.get(workspace_id)
    with ACTIVE_CHAT_PROCESS_META_LOCK:
        meta = dict(ACTIVE_CHAT_PROCESS_META.get(workspace_id) or {})

    if process is None or process.poll() is not None or not meta:
        clear_active_chat_process(workspace_id)
        return {"active": False}

    now = time.monotonic()
    started_at = float(meta.get("started_at") or now)
    last_output_at = float(meta.get("last_output_at") or started_at)
    idle_seconds = max(0.0, now - last_output_at)
    input_waiting = bool(meta.get("input_waiting"))
    stalled = idle_seconds >= stall_warning_seconds and not input_waiting
    return {
        "active": True,
        "pid": int(meta.get("pid") or process.pid),
        "runtime": meta.get("runtime") or "",
        "idle_seconds": round(idle_seconds, 1),
        "running_seconds": round(max(0.0, now - started_at), 1),
        "input_waiting": input_waiting,
        "stop_requested": bool(meta.get("stop_requested")),
        "stalled": stalled,
    }


def sweep_inactive_chat_processes() -> list[int]:
    cleared = []
    with ACTIVE_CHAT_PROCESSES_LOCK:
        snapshot = list(ACTIVE_CHAT_PROCESSES.items())
    for workspace_id, process in snapshot:
        with ACTIVE_CHAT_PROCESS_META_LOCK:
            has_meta = workspace_id in ACTIVE_CHAT_PROCESS_META
        if process.poll() is None and has_meta:
            continue
        clear_active_chat_process(workspace_id)
        cleared.append(workspace_id)
    return cleared
