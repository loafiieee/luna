from __future__ import annotations

import shutil
from pathlib import Path

from backend.utils.state import STATE
from backend.utils.paths import runtime_server_dir


def delete_server(folder: str) -> None:
    """Delete a server folder and remove it from servers.json.

    This is a local-only operation. Edge reservation cleanup is handled by
    sync_desired_sticky_servers() (called by the CLI wrapper).
    """

    server_folder = Path("servers") / folder

    if not server_folder.exists() or not server_folder.is_dir():
        raise ValueError(f"Server folder {server_folder} does not exist.")

    # Capture server_id before we delete servers.json entry (best-effort)
    server_id: str | None = None
    try:
        for s in STATE.read():
            if s.get("folder") == folder:
                server_id = str(s.get("server_id") or "") or None
                break
    except Exception:
        server_id = None

    # Remove the server folder
    shutil.rmtree(server_folder)

    # Remove from servers.json (locked + atomic)
    def _mutate(servers):
        return [s for s in servers if s.get("folder") != folder]

    STATE.mutate(_mutate)

    # Clean runtime dir (console/state/control) so UI doesn't show stale sessions
    if server_id:
        try:
            shutil.rmtree(runtime_server_dir(server_id), ignore_errors=True)
        except Exception:
            pass
