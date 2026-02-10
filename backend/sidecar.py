from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from backend.scripts.delete_server import delete_server
from backend.utils.state import STATE
from backend.utils.process_manager import MANAGER


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "cli.py"


@dataclass
class ServerSession:
    session_id: str
    edition: str
    platform: str
    version: str
    name: str


SERVER_SESSIONS: Dict[str, ServerSession] = {}


def _server_key(edition: str, platform: str, version: str, name: str) -> str:
    return f"{edition}:{platform}:{version}:{name}"


def _json(handler: BaseHTTPRequestHandler, code: int, obj: Dict[str, Any]) -> None:
    data = json.dumps(obj).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "content-type")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(data)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    if not raw:
        return {}
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Request body must be a JSON object")
    return obj


class SidecarHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silence noisy default logs
        return

    def do_OPTIONS(self) -> None:
        _json(self, HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/servers":
                servers = STATE.read()
                for server in servers:
                    ed = str(server.get("edition") or "java")
                    key = _server_key(
                        ed,
                        str(server.get("platform") or ""),
                        str(server.get("version") or ""),
                        str(server.get("name") or ""),
                    )
                    sess = SERVER_SESSIONS.get(key)
                    if sess:
                        try:
                            st = MANAGER.status(sess.session_id)
                            server["runtime"] = {"session_id": sess.session_id, **st}
                        except Exception:
                            server["runtime"] = {"session_id": sess.session_id, "running": False, "exit_code": None}
                    else:
                        server["runtime"] = {"running": False, "exit_code": None}
                _json(self, HTTPStatus.OK, {"servers": servers})
                return

            if parsed.path == "/pty/poll":
                q = parse_qs(parsed.query)
                session_id = (q.get("session_id") or [None])[0]
                if not session_id:
                    _json(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required"})
                    return
                lines = MANAGER.poll_output(session_id)
                status = MANAGER.status(session_id)
                _json(self, HTTPStatus.OK, {"session_id": session_id, "lines": lines, **status})
                return

            if parsed.path == "/pty/status":
                q = parse_qs(parsed.query)
                session_id = (q.get("session_id") or [None])[0]
                if not session_id:
                    _json(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required"})
                    return
                _json(self, HTTPStatus.OK, {"session_id": session_id, **MANAGER.status(session_id)})
                return

            _json(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
        except Exception as e:
            _json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    def do_POST(self) -> None:
        try:
            if self.path == "/servers/install":
                body = _read_json(self)
                edition = str(body["edition"])
                platform = str(body["platform"])
                version = str(body["version"])
                name = str(body["name"])
                ram = int(body["ram"])
                eula = bool(body["eula"])
                sticky_address = bool(body.get("sticky_address", True))
                from backend.scripts.server_installer import install_server
                folder = install_server(edition, platform, version, name, ram, eula, sticky_address=sticky_address)
                _json(self, HTTPStatus.OK, {"ok": True, "folder": str(folder)})
                return

            if self.path == "/servers/delete":
                body = _read_json(self)
                platform = str(body["platform"])
                version = str(body["version"])
                name = str(body["name"])
                folder = f"{platform}-{version}-{name}"
                delete_server(folder)
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if self.path == "/servers/start":
                body = _read_json(self)
                edition = str(body["edition"])
                platform = str(body["platform"])
                version = str(body["version"])
                name = str(body["name"])

                cmd = [sys.executable, str(CLI_PATH), "run_server", edition, platform, version, name, "--json"]
                session_id = MANAGER.start(cmd, cwd=str(REPO_ROOT))

                key = _server_key(edition, platform, version, name)
                SERVER_SESSIONS[key] = ServerSession(
                    session_id=session_id,
                    edition=edition,
                    platform=platform,
                    version=version,
                    name=name,
                )
                _json(self, HTTPStatus.OK, {"ok": True, "session_id": session_id, "key": key})
                return

            if self.path == "/servers/command":
                body = _read_json(self)
                session_id = str(body["session_id"])
                command = str(body["command"])
                if not command.endswith("\n"):
                    command += "\n"
                MANAGER.write(session_id, command)
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if self.path == "/servers/stop":
                body = _read_json(self)
                session_id = body.get("session_id")
                if not session_id:
                    key = _server_key(
                        str(body["edition"]),
                        str(body["platform"]),
                        str(body["version"]),
                        str(body["name"]),
                    )
                    sess = SERVER_SESSIONS.get(key)
                    if not sess:
                        _json(self, HTTPStatus.NOT_FOUND, {"error": "session not found"})
                        return
                    session_id = sess.session_id
                MANAGER.stop(str(session_id))
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if self.path == "/pty/start":
                body = _read_json(self)
                cmd = body.get("cmd")
                if not isinstance(cmd, list) or not cmd:
                    _json(self, HTTPStatus.BAD_REQUEST, {"error": "cmd must be a non-empty list"})
                    return
                cwd = body.get("cwd")
                session_id = MANAGER.start([str(c) for c in cmd], cwd=str(cwd) if cwd else str(REPO_ROOT))
                _json(self, HTTPStatus.OK, {"ok": True, "session_id": session_id})
                return

            if self.path == "/pty/write":
                body = _read_json(self)
                session_id = str(body["session_id"])
                data = str(body.get("data", ""))
                MANAGER.write(session_id, data)
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if self.path == "/pty/resize":
                body = _read_json(self)
                session_id = str(body["session_id"])
                cols = int(body["cols"])
                rows = int(body["rows"])
                MANAGER.resize(session_id, cols, rows)
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            if self.path == "/pty/stop":
                body = _read_json(self)
                session_id = str(body["session_id"])
                MANAGER.stop(session_id)
                _json(self, HTTPStatus.OK, {"ok": True})
                return

            _json(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
        except KeyError as e:
            _json(self, HTTPStatus.BAD_REQUEST, {"error": f"missing field: {e}"})
        except Exception as e:
            _json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})


def main() -> int:
    host = os.environ.get("LUNA_SIDECAR_HOST", "127.0.0.1")
    port = int(os.environ.get("LUNA_SIDECAR_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), SidecarHandler)
    print(json.dumps({"event": "sidecar_started", "host": host, "port": port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
