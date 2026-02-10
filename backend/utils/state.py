from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class ServersState:
    """Locking + atomic helpers for servers/servers.json."""

    def __init__(self, path: str | Path = "servers/servers.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._lock_path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            finally:
                fh.close()

    def ensure_exists(self) -> None:
        with self._lock():
            if not self.path.exists():
                self._atomic_write([])

    def read(self) -> list[dict[str, Any]]:
        self.ensure_exists()
        with self._lock():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return [d for d in data if isinstance(d, dict)]

    def write(self, servers: list[dict[str, Any]]) -> None:
        with self._lock():
            self._atomic_write(servers)

    def mutate(self, fn) -> list[dict[str, Any]]:
        """Mutate state under a lock and return new state."""
        self.ensure_exists()
        with self._lock():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
            servers = [d for d in data if isinstance(d, dict)]
            new_servers = fn(servers)
            if not isinstance(new_servers, list):
                raise ValueError("Mutation function must return list")
            self._atomic_write(new_servers)
            return new_servers

    def _atomic_write(self, obj: Any) -> None:
        fd, tmp_path = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=4)
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


STATE = ServersState()
