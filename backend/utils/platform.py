from __future__ import annotations

import os
import sys
import platform as _platform
from pathlib import Path


def is_windows() -> bool:
    return os.name == "nt"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def arch() -> str:
    """Return a normalized architecture string ("x64" or "aarch64" when known)."""
    machine = _platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "aarch64"
    return machine


def exe_suffix() -> str:
    return ".exe" if is_windows() else ""


def data_dir(app_name: str = "luna") -> Path:
    """OS-correct per-user data directory."""
    if is_windows():
        base = Path(os.environ.get("APPDATA") or Path.home())
        return base / app_name

    if is_macos():
        return Path.home() / "Library" / "Application Support" / app_name

    # Linux / other unix: prefer XDG_STATE_HOME
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / app_name

    return Path.home() / ".local" / "state" / app_name


def ensure_data_dir(app_name: str = "luna") -> Path:
    p = data_dir(app_name)
    p.mkdir(parents=True, exist_ok=True)
    return p
