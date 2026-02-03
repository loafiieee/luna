"""backend/utils/emit.py

Small, dependency-free logger/event emitter.

- Default: human-readable logs.
- Optional JSON-lines mode (best for a GUI like Tauri).

Design note:
`event_type` is the first positional argument so payloads are free to use the key
`name` without colliding (a prior bug when the param itself was called `name`).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict

_JSON_MODE: bool = False


def set_json_mode(enabled: bool) -> None:
    global _JSON_MODE
    _JSON_MODE = bool(enabled)


def is_json_mode() -> bool:
    return _JSON_MODE


def _ts() -> str:
    # RFC3339-ish, stable for machines + humans
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _print_json(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def info(message: str) -> None:
    if _JSON_MODE:
        _print_json({
            "event": "log",
            "level": "info",
            "message": message,
            "timestamp": _ts(),
        })
    else:
        print(f"[LUNA] {message}", flush=True)


def warn(message: str) -> None:
    if _JSON_MODE:
        _print_json({
            "event": "log",
            "level": "warn",
            "message": message,
            "timestamp": _ts(),
        })
    else:
        print(f"[LUNA][WARN] {message}", flush=True)


def error(message: str) -> None:
    if _JSON_MODE:
        _print_json({
            "event": "error",
            "message": message,
            "timestamp": _ts(),
        })
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
