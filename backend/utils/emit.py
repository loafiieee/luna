from __future__ import annotations

import io
import json
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_RAW_STDOUT = sys.__stdout__
_RAW_STDERR = sys.__stderr__
_CAPTURE_INSTALLED = False


class _LineBufferedWriter(io.TextIOBase):
    def __init__(self, underlying, level: str):
        self._u = underlying
        self._level = level
        self._buf = ""
        self._lock = threading.Lock()

    def writable(self):
        return True

    def write(self, s):
        if not s:
            return 0
        if not _JSON_MODE:
            return self._u.write(s)
        with self._lock:
            self._buf += s
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    _print_json(
                        {
                            "event": "log",
                            "level": self._level,
                            "message": line,
                            "timestamp": _ts(),
                        }
                    )
        return len(s)

    def flush(self):
        if not _JSON_MODE:
            try:
                self._u.flush()
            except Exception:
                pass
            return
        with self._lock:
            if self._buf:
                _print_json(
                    {
                        "event": "log",
                        "level": self._level,
                        "message": self._buf.rstrip("\r"),
                        "timestamp": _ts(),
                    }
                )
                self._buf = ""


def install_output_capture():
    """Wrap sys.stdout/sys.stderr so prints become NDJSON log events in --json mode."""
    global _CAPTURE_INSTALLED
    if _CAPTURE_INSTALLED:
        return
    _CAPTURE_INSTALLED = True
    sys.stdout = _LineBufferedWriter(sys.stdout, "info")
    sys.stderr = _LineBufferedWriter(sys.stderr, "error")


_JSON_MODE: bool = False


def set_json_mode(enabled: bool) -> None:
    global _JSON_MODE
    _JSON_MODE = bool(enabled)


def is_json_mode() -> bool:
    return _JSON_MODE


def _ts() -> str:
    # RFC3339-ish, stable for machines + humans
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _print_json(obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    try:
        # Write UTF-8 bytes directly so emojis/non-ASCII from APIs don't fail on cp1252/charmap consoles.
        _RAW_STDOUT.buffer.write(line.encode("utf-8", errors="replace"))
        _RAW_STDOUT.buffer.flush()
    except Exception:
        _RAW_STDOUT.write(json.dumps(obj, ensure_ascii=True) + "\n")
        _RAW_STDOUT.flush()


def info(message: str) -> None:
    if _JSON_MODE:
        _print_json({"event": "log", "level": "info", "message": message, "timestamp": _ts()})
    else:
        print(f"[LUNA] {message}", flush=True)


def warn(message: str) -> None:
    if _JSON_MODE:
        _print_json({"event": "log", "level": "warn", "message": message, "timestamp": _ts()})
    else:
        print(f"[LUNA][WARN] {message}", flush=True)


def error(message: str, *, code: Optional[str] = None) -> None:
    if _JSON_MODE:
        payload: Dict[str, Any] = {"event": "error", "message": message, "timestamp": _ts()}
        if code:
            payload["code"] = code
        _print_json(payload)
    else:
        print(f"[LUNA][ERROR] {message}", file=sys.stderr, flush=True)


def event(event_type: str, **data: Any) -> None:
    """Emit a structured event.

    Only outputs in JSON mode; in human mode this is a no-op.
    """
    if not _JSON_MODE:
        return

    payload: Dict[str, Any] = {"event": event_type, "timestamp": _ts()}
    payload.update(data)
    _print_json(payload)


def result(command: str, data: Any) -> None:
    """Emit a structured result payload for a command."""
    if _JSON_MODE:
        _print_json({"event": "result", "command": command, "data": data, "timestamp": _ts()})
    else:
        # Human mode: pretty-ish print
        try:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            print(data)


def server_console(*, server_id: str, line: str) -> None:
    """Emit a console line for a running server session.

    In JSON mode this is a stable NDJSON event.
    In human mode, we print the line as-is.
    """
    if _JSON_MODE:
        _print_json({"event": "server_console", "server_id": server_id, "line": line, "timestamp": _ts()})
    else:
        # Avoid extra prefixes; keep it terminal-like.
        print(line, flush=True)


def server_state(*, server_id: str, state: str, **data: Any) -> None:
    """Emit a server lifecycle/state change event."""
    if not _JSON_MODE:
        return
    payload: Dict[str, Any] = {"event": "server_state", "server_id": server_id, "state": state, "timestamp": _ts()}
    payload.update(data)
    _print_json(payload)
