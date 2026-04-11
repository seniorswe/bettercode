import json
import os
import sys
import threading
import time
from datetime import datetime, UTC
from pathlib import Path

from bettercode.app_meta import bettercode_home_dir

_DEV_MODE = os.environ.get("BETTERCODE_DEV") == "1"
_TELEMETRY_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


TELEMETRY_LOG_FILENAME = "telemetry.jsonl"
TELEMETRY_LOG_LOCK = threading.Lock()


def _normalize_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return str(value)


def duration_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def telemetry_log_path() -> Path:
    return bettercode_home_dir(create=True) / TELEMETRY_LOG_FILENAME


def telemetry_info_payload() -> dict:
    path = telemetry_log_path()
    exists = path.exists()
    size = 0
    modified_at = ""
    if exists:
        try:
            stat_result = path.stat()
            size = int(stat_result.st_size)
            modified_at = datetime.fromtimestamp(stat_result.st_mtime, UTC).isoformat()
        except OSError:
            pass
    return {
        "path": str(path),
        "exists": exists,
        "size": size,
        "modified_at": modified_at,
    }


def _tail_lines(path: Path, n: int, chunk_size: int = 8192) -> list[str]:
    """Return the last n text lines of a file without reading the whole thing."""
    with path.open("rb") as fh:
        fh.seek(0, 2)
        remaining = fh.tell()
        buf = b""
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            fh.seek(remaining)
            buf = fh.read(read_size) + buf
            lines = buf.decode("utf-8", errors="replace").splitlines()
            if len(lines) > n + 1:  # +1 because the first line may be partial
                return lines[-(n):]
    return buf.decode("utf-8", errors="replace").splitlines()


def recent_events(limit: int = 200) -> list[dict]:
    path = telemetry_log_path()
    if not path.exists():
        return []
    try:
        lines = _tail_lines(path, max(1, int(limit)))
    except OSError:
        return []
    events: list[dict] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _rotate_log_if_needed(path: Path) -> None:
    """Rename the log to .1 and start fresh once it exceeds _TELEMETRY_MAX_BYTES."""
    try:
        if path.exists() and path.stat().st_size >= _TELEMETRY_MAX_BYTES:
            path.replace(path.with_suffix(".jsonl.1"))
    except OSError:
        pass


def log_event(event: str, **fields) -> None:
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
    }
    payload.update({key: _normalize_value(value) for key, value in fields.items()})
    line = json.dumps(payload, sort_keys=True)
    if _DEV_MODE:
        print(line, file=sys.stderr, flush=True)
    try:
        path = telemetry_log_path()
        with TELEMETRY_LOG_LOCK:
            _rotate_log_if_needed(path)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        pass
