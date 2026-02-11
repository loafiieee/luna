from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from backend.utils.platform import ensure_data_dir

APP_NAME = os.environ.get("LUNA_APP_NAME", "luna")

# In-process override (useful for tests)
_DATA_ROOT: Optional[Path] = None


def _truthy(v: str | None) -> bool:
    if v is None:
        return False
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _norm_path(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def compute_data_root(*, data_dir: Optional[str] = None, portable: bool = False) -> Path:
    """Compute the directory where Luna stores all writable data.

    Priority:
      1) explicit data_dir argument
      2) LUNA_DATA_DIR env var
      3) portable mode (arg or LUNA_PORTABLE env var): ./luna-data
      4) OS app-data directory
    """
    if data_dir:
        return _norm_path(data_dir)

    env_dir = os.environ.get("LUNA_DATA_DIR")
    if env_dir:
        return _norm_path(env_dir)

    portable = portable or _truthy(os.environ.get("LUNA_PORTABLE"))
    if portable:
        return _norm_path(Path.cwd() / "luna-data")

    # Default: OS per-user app-data dir
    return _norm_path(ensure_data_dir(APP_NAME))


def _dir_is_effectively_empty(p: Path) -> bool:
    if not p.exists() or not p.is_dir():
        return True
    try:
        for child in p.iterdir():
            # ignore common junk
            name = child.name
            if name in {".DS_Store"}:
                continue
            return False
        return True
    except Exception:
        return False


def maybe_migrate_legacy_servers(*, data_root: Path) -> None:
    """Best-effort migration from legacy ./servers -> <data_root>/servers.

    We only migrate when the destination doesn't already look populated.
    """
    if _truthy(os.environ.get("LUNA_DISABLE_LEGACY_MIGRATION")):
        return

    legacy = Path.cwd() / "servers"
    dest = data_root / "servers"

    # Nothing to migrate
    if not legacy.exists() or not legacy.is_dir():
        return

    # Avoid migrating into itself
    try:
        if legacy.resolve() == dest.resolve():
            return
    except Exception:
        pass

    # If destination already has real content, leave it alone
    if dest.exists() and not _dir_is_effectively_empty(dest):
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        if not dest.exists():
            shutil.move(str(legacy), str(dest))
        else:
            # dest exists but empty: move contents
            for item in legacy.iterdir():
                shutil.move(str(item), str(dest / item.name))
            try:
                legacy.rmdir()
            except Exception:
                pass
    except Exception:
        # If migration fails, don't block the app
        return


def configure_data_root(*, data_dir: Optional[str] = None, portable: bool = False) -> Path:
    """Resolve + create the data root, set env vars, and migrate legacy layout."""
    global _DATA_ROOT
    root = compute_data_root(data_dir=data_dir, portable=portable)
    root.mkdir(parents=True, exist_ok=True)

    # One-time best-effort migration (safe no-op if not applicable)
    maybe_migrate_legacy_servers(data_root=root)

    _DATA_ROOT = root
    os.environ["LUNA_DATA_DIR"] = str(root)
    if portable:
        os.environ["LUNA_PORTABLE"] = "1"
    return root


def get_data_root() -> Path:
    global _DATA_ROOT
    if _DATA_ROOT is None:
        _DATA_ROOT = compute_data_root()
        _DATA_ROOT.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("LUNA_DATA_DIR", str(_DATA_ROOT))
    return _DATA_ROOT


def servers_dir() -> Path:
    return get_data_root() / "servers"


def servers_state_path() -> Path:
    return servers_dir() / "servers.json"


def runtime_dir() -> Path:
    return get_data_root() / "runtime"


def runtime_server_dir(server_id: str) -> Path:
    return runtime_dir() / str(server_id)


def runtime_console_path(server_id: str) -> Path:
    return runtime_server_dir(server_id) / "console.ndjson"


def runtime_state_path(server_id: str) -> Path:
    return runtime_server_dir(server_id) / "state.json"


def runtime_control_path(server_id: str) -> Path:
    return runtime_server_dir(server_id) / "control.ndjson"
