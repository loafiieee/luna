# run_server.py
from __future__ import annotations

import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from backend.utils.state import STATE
from backend.utils.paths import (
    runtime_dir,
    runtime_server_dir,
    runtime_console_path,
    runtime_state_path,
    runtime_control_path,
)

# Import tunnel + emitter in a way that works whether this is executed as a script
# (imports like utils.*) or imported as a module (imports like backend.utils.*).
try:  # noqa: E402
    from utils.tunnel import TunnelRunner  # type: ignore
    from utils.emit import info, warn, error, server_console as _emit_console, server_state as _emit_state  # type: ignore
    from utils.get_reseved_ports import get_reserved_ports  # type: ignore
except Exception:  # pragma: no cover
    from backend.utils.tunnel import TunnelRunner  # type: ignore
    from backend.utils.emit import info, warn, error, server_console as _emit_console, server_state as _emit_state  # type: ignore
    from backend.utils.get_reseved_ports import get_reserved_ports  # type: ignore


# ---------------- Tunnel runner ----------------

TUNNEL = TunnelRunner(
    edge_url="wss://tunnel.loafiieee.com",
    domain_suffix="mc.loafiieee.com",
    on_status=lambda s: info(f"[tunnel] {s}"),
)


# ---------------- Runtime helpers ----------------


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def _mark_runtime_stopped(server_id: str, *, reason: Optional[str] = None) -> None:
    """Best-effort: reconcile runtime state file to stopped."""
    st_path = runtime_state_path(str(server_id))
    try:
        current: Dict[str, Any] = {}
        if st_path.exists():
            raw = json.loads(st_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                current = raw
        current["state"] = "stopped"
        current["server_pid"] = None
        current["detached_process"] = False
        if reason:
            current["stop_reason"] = reason
        _atomic_write_json(st_path, current)
    except Exception:
        pass


class RuntimeRecorder:
    """Writes console.ndjson + state.json for a running server."""

    def __init__(self, server_id: str):
        self.server_id = str(server_id)
        self.dir = runtime_server_dir(self.server_id)
        self.dir.mkdir(parents=True, exist_ok=True)

        self.console_path = runtime_console_path(self.server_id)
        self.state_path = runtime_state_path(self.server_id)
        self.control_path = runtime_control_path(self.server_id)

        # Reset control queue for this session
        try:
            self.control_path.write_text("", encoding="utf-8")
        except Exception:
            pass

        self._lock = threading.Lock()
        self._fh = open(self.console_path, "a", encoding="utf-8", errors="replace", buffering=1)

    def write_console(self, line: str) -> None:
        # Record as NDJSON line (not necessarily identical timestamp to emitted event)
        payload = {
            "event": "server_console",
            "server_id": self.server_id,
            "line": line,
            "timestamp": time.time(),
        }
        with self._lock:
            self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._fh.flush()

    def write_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            _atomic_write_json(self.state_path, state)

    def close(self) -> None:
        try:
            with self._lock:
                try:
                    self._fh.flush()
                except Exception:
                    pass
                try:
                    self._fh.close()
                except Exception:
                    pass
        except Exception:
            pass


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int, *, timeout_s: float = 8.0) -> bool:
    """Best-effort terminate a PID cross-platform. Returns True if process is gone."""
    if pid <= 0:
        return True
    if not _pid_exists(pid):
        return True

    try:
        if os.name == "nt":
            # os.kill(SIGTERM) is effectively TerminateProcess on Windows
            os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    end = time.time() + timeout_s
    while time.time() < end:
        if not _pid_exists(pid):
            return True
        time.sleep(0.2)

    # Hard kill
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass

    time.sleep(0.5)
    return not _pid_exists(pid)


def _can_bind_tcp(port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", int(port)))
        s.close()
        return True
    except OSError:
        return False


def _can_bind_udp(port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", int(port)))
        s.close()
        return True
    except OSError:
        return False


def _pid_listening_on_tcp_port(port: int) -> int:
    """Best-effort PID lookup for a listening TCP port."""
    try:
        p = int(port)
    except Exception:
        return 0

    if p <= 0:
        return 0

    try:
        if os.name == "nt":
            # netstat output line ends with PID on Windows
            out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="ignore")
            needle = f":{p}"
            for line in out.splitlines():
                low = line.strip().lower()
                if "listen" not in low:
                    continue
                if needle not in line:
                    continue
                parts = line.split()
                if parts:
                    try:
                        pid = int(parts[-1])
                        if pid > 0:
                            return pid
                    except Exception:
                        continue
        else:
            # Try ss first
            try:
                out = subprocess.check_output(["ss", "-ltnp"], text=True, errors="ignore")
                needle = f":{p}"
                for line in out.splitlines():
                    if needle not in line:
                        continue
                    if "LISTEN" not in line.upper():
                        continue
                    marker = "pid="
                    idx = line.find(marker)
                    if idx == -1:
                        continue
                    tail = line[idx + len(marker) :]
                    pid_digits = ""
                    for ch in tail:
                        if ch.isdigit():
                            pid_digits += ch
                        else:
                            break
                    if pid_digits:
                        pid = int(pid_digits)
                        if pid > 0:
                            return pid
            except Exception:
                pass

            # Fallback to lsof when ss is unavailable
            try:
                out = subprocess.check_output(["lsof", "-nP", f"-iTCP:{p}", "-sTCP:LISTEN", "-t"], text=True, errors="ignore")
                for line in out.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    pid = int(line)
                    if pid > 0:
                        return pid
            except Exception:
                pass

            # Last fallback to fuser
            try:
                out = subprocess.check_output(["fuser", "-n", "tcp", str(p)], text=True, errors="ignore")
                for tok in out.replace("\n", " ").split():
                    tok = tok.strip().strip(":")
                    if tok.isdigit():
                        pid = int(tok)
                        if pid > 0:
                            return pid
            except Exception:
                pass
    except Exception:
        return 0

    return 0


def _is_reserved(port: int, ranges: List[Tuple[int, int]]) -> bool:
    for a, b in ranges:
        if a <= port <= b:
            return True
    return False


def _alloc_free_port(
    *,
    need_tcp: bool,
    need_udp: bool,
    used_tcp: set[int],
    used_udp: set[int],
    reserved_tcp: List[Tuple[int, int]],
    reserved_udp: List[Tuple[int, int]],
    start: int = 25565,
    end: int = 65535,
) -> int:
    import random

    for _ in range(50000):
        cand = random.randint(start, end)
        if need_tcp:
            if cand in used_tcp or _is_reserved(cand, reserved_tcp) or not _can_bind_tcp(cand):
                continue
        if need_udp:
            if cand in used_udp or _is_reserved(cand, reserved_udp) or not _can_bind_udp(cand):
                continue
        return cand

    # fallback linear scan
    for cand in range(start, end + 1):
        if need_tcp:
            if cand in used_tcp or _is_reserved(cand, reserved_tcp) or not _can_bind_tcp(cand):
                continue
        if need_udp:
            if cand in used_udp or _is_reserved(cand, reserved_udp) or not _can_bind_udp(cand):
                continue
        return cand

    raise RuntimeError("Could not allocate a free port")


def _alloc_free_udp_port(*, used_udp: set[int], reserved_udp: List[Tuple[int, int]], start: int = 20000, end: int = 65535) -> int:
    import random

    for _ in range(50000):
        cand = random.randint(start, end)
        if cand in used_udp:
            continue
        if _is_reserved(cand, reserved_udp):
            continue
        if not _can_bind_udp(cand):
            continue
        return cand

    for cand in range(start, end + 1):
        if cand in used_udp:
            continue
        if _is_reserved(cand, reserved_udp):
            continue
        if not _can_bind_udp(cand):
            continue
        return cand

    raise RuntimeError("Could not allocate a free UDP port")


# ---------------- Servers JSON helpers ----------------


def reconcile_servers_with_disk() -> None:
    """Reconcile servers/servers.json with the actual folders in servers/.

    - Removes entries whose server folder no longer exists.
    - Adds entries for server folders that exist but are missing from servers.json.

    This is intentionally conservative: it does not try to infer RAM/ports/EULA beyond safe defaults.
    Further migrations (server_id, voice_port, etc.) are handled by read_servers_file().

    Important: If entries are removed due to missing folders, we sync desired sticky servers so the
    edge deallocates orphan reservations.
    """
    servers_dir = "servers"
    os.makedirs(servers_dir, exist_ok=True)

    # Load existing (best-effort)
    try:
        servers = STATE.read()
    except Exception as e:
        warn(f"[servers] warning: could not read servers.json, resetting: {e}")
        servers = []

    # Normalize folder key for matching
    def _folder_of(s: dict) -> str | None:
        fld = s.get("folder")
        if isinstance(fld, str) and fld:
            return fld
        plat, ver, name = s.get("platform"), s.get("version"), s.get("name")
        if isinstance(plat, str) and isinstance(ver, str) and isinstance(name, str) and plat and ver and name:
            return f"{plat}-{ver}-{name}"
        return None

    by_folder: dict[str, dict] = {}
    for s in servers:
        if isinstance(s, dict):
            fld = _folder_of(s)
            if fld:
                s["folder"] = fld
                by_folder[fld] = s

    disk_folders = [d for d in os.listdir(servers_dir) if os.path.isdir(os.path.join(servers_dir, d))]

    changed = False
    removed_any = False
    new_servers: list[dict] = []

    disk_set = set(disk_folders)
    for fld, s in by_folder.items():
        if fld in disk_set:
            new_servers.append(s)
        else:
            changed = True
            removed_any = True

    # Add any folders missing from servers.json
    for fld in disk_folders:
        if fld in by_folder:
            continue

        parts = fld.split("-", 2)
        if len(parts) != 3:
            warn(f"[servers] skipping unrecognized folder name: {fld}")
            continue

        platform, version, name = parts
        new_servers.append(
            {
                "server_id": str(uuid.uuid4()),
                "edition": "java",  # safe default (can't reliably infer)
                "platform": platform,
                "version": version,
                "name": name,
                "folder": fld,
                "ram": 2048,
                "eula": False,
                "sticky_address": True,
                "tunneling": True,
            }
        )
        changed = True

    if changed:
        STATE.write(new_servers)

    # Run migrations/normalization (voice ports, etc.)
    try:
        read_servers_file()
    except Exception as e:
        warn(f"[servers] warning: post-reconcile migration failed: {e}")

    # If servers were removed because folders disappeared, sync so edge can deallocate sticky ports.
    if removed_any:
        try:
            sync_desired_sticky_servers()
        except Exception as e:
            warn(f"[tunnel] warning: could not sync reservations after reconcile: {e}")


def read_servers_file() -> list:
    servers = STATE.read()

    changed = False

    # Pre-compute used UDP ports (voice + bedrock) so we can safely allocate new voice ports.
    used_udp_ports: set[int] = set()
    used_tcp_ports: set[int] = set()

    for s in servers:
        ed = str(s.get("edition") or "")
        p = s.get("port")
        if isinstance(p, int):
            if ed in ("java", "both"):
                used_tcp_ports.add(int(p))
            if ed in ("bedrock", "both"):
                used_udp_ports.add(int(p))

        vp = s.get("voice_port")
        if isinstance(vp, int):
            used_udp_ports.add(int(vp))

    reserved_udp: List[Tuple[int, int]] = []
    try:
        reserved_udp = get_reserved_ports("udp")
    except Exception:
        reserved_udp = []

    def _alloc_voice_port() -> int:
        return _alloc_free_udp_port(used_udp=used_udp_ports, reserved_udp=reserved_udp, start=20000, end=65535)

    for s in servers:
        if not s.get("server_id"):
            s["server_id"] = str(uuid.uuid4())
            changed = True
        if "sticky_address" not in s:
            s["sticky_address"] = True
            changed = True
        if "tunneling" not in s:
            s["tunneling"] = True
            changed = True

        if not s.get("folder") and s.get("platform") and s.get("version") and s.get("name"):
            s["folder"] = f"{s['platform']}-{s['version']}-{s['name']}"
            changed = True

        if not s.get("edition"):
            s["edition"] = "java"
            changed = True

        ed = str(s.get("edition") or "")
        if ed in ("java", "both"):
            vp = s.get("voice_port")
            if not isinstance(vp, int) or not (1 <= int(vp) <= 65535) or _is_reserved(int(vp), reserved_udp):
                s["voice_port"] = _alloc_voice_port()
                changed = True

    if changed:
        STATE.write(servers)

    return servers


def sync_desired_sticky_servers() -> None:
    """Best-effort: tell the edge which sticky servers still exist locally (folder exists).

    Also tells the edge which services each server should reserve ports for.
    """
    servers = read_servers_file()
    desired: list[dict] = []

    for s in servers:
        if not s.get("sticky_address", True):
            continue
        folder = s.get("folder")
        if not folder:
            continue
        server_dir = os.path.join("servers", folder)
        if not os.path.isdir(server_dir):
            continue

        sid = str(s["server_id"])
        ed = str(s.get("edition") or "java")

        services: list[dict] = []
        if ed in ("java", "both"):
            services.append({"svc": "mc", "proto": "tcp"})
            services.append({"svc": "voice", "proto": "udp"})
        if ed in ("bedrock", "both"):
            services.append({"svc": "bedrock", "proto": "udp"})

        desired.append({"server_id": sid, "services": services})

    # de-dupe while preserving order
    seen = set()
    desired_unique = []
    for item in desired:
        sid = item["server_id"]
        if sid in seen:
            continue
        seen.add(sid)
        desired_unique.append(item)

    TUNNEL.sync_desired(desired=desired_unique)


def get_per_server_config(platform: str, version: str, name: str) -> dict:
    servers = read_servers_file()
    for server in servers:
        if server.get("platform") == platform and server.get("version") == version and server.get("name") == name:
            return server
    raise ValueError(f"No configuration found for server: {platform}-{version}-{name}")


# ---------------- Properties helpers ----------------


def read_properties(path: str) -> Dict[str, str]:
    """Reads Minecraft-style key=value files (ignores comments and blanks)."""
    props: Dict[str, str] = {}
    if not os.path.exists(path):
        return props
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    return props


def write_properties_preserve(path: str, updates: Dict[str, str]) -> None:
    """Update (or create) a .properties file while preserving existing comments/unknown keys."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines: List[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

    out: List[str] = []
    seen: set[str] = set()

    for line in lines:
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            out.append(line)
            continue
        k, _v = raw.split("=", 1)
        k = k.strip()
        if k in updates:
            out.append(f"{k}={updates[k]}\n")
            seen.add(k)
        else:
            out.append(line)

    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}\n")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(out)
    os.replace(tmp, path)


# ---------------- Minecraft readiness helpers ----------------


def wait_tcp_open(host: str, port: int, timeout_s: float = 30.0) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def is_tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


# ---- Bedrock UDP readiness (RakNet unconnected ping) ----
_RAKNET_MAGIC = b"\x00\xff\xff\x00\xfe\xfe\xfe\xfe\xfd\xfd\xfd\xfd\x12\x34\x56\x78"


def bedrock_udp_ping_once(host: str, port: int, timeout_s: float = 0.8) -> bool:
    """Sends a RakNet Unconnected Ping (0x01) and expects Unconnected Pong (0x1c)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout_s)

        ping_id = int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF
        client_guid = int.from_bytes(os.urandom(8), "big", signed=False)

        pkt = b"\x01" + struct.pack(">Q", ping_id) + _RAKNET_MAGIC + struct.pack(">Q", client_guid)
        s.sendto(pkt, (host, port))

        data, _addr = s.recvfrom(2048)
        if not data:
            return False
        if data[0] != 0x1C:
            return False
        if _RAKNET_MAGIC not in data:
            return False
        return True
    except (OSError, socket.timeout):
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def wait_bedrock_udp_ready(host: str, port: int, timeout_s: float = 30.0) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if bedrock_udp_ping_once(host, port, timeout_s=0.8):
            return True
        time.sleep(0.25)
    return False


# ---------------- Simple Voice Chat config helpers ----------------

_PLUGIN_PLATFORMS = {
    "paper",
    "spigot",
    "purpur",
    "pufferfish",
    "folia",
    "bukkit",
}


def _voicechat_config_path(server_dir: str, platform: str) -> str:
    """Return the most likely voicechat-server.properties location."""
    mod_path = os.path.join(server_dir, "config", "voicechat", "voicechat-server.properties")
    plugin_path = os.path.join(server_dir, "plugins", "voicechat", "voicechat-server.properties")

    if os.path.exists(plugin_path):
        return plugin_path
    if os.path.exists(mod_path):
        return mod_path

    if platform.lower() in _PLUGIN_PLATFORMS:
        return plugin_path
    return mod_path


def _read_voice_port_from_voicechat_config(path: str) -> Optional[int]:
    props = read_properties(path)
    raw = props.get("port")
    if raw is None:
        return None
    try:
        p = int(raw)
        if 1 <= p <= 65535:
            return p
        return None
    except Exception:
        return None


def _ensure_voicechat_config(*, server_dir: str, platform: str, voice_local_port: int, public_host: Optional[str]) -> None:
    """Create/update voicechat-server.properties for Simple Voice Chat."""
    cfg_path = _voicechat_config_path(server_dir, platform)
    updates: Dict[str, str] = {"port": str(int(voice_local_port))}
    if public_host:
        updates["voice_host"] = public_host
    write_properties_preserve(cfg_path, updates)


# ---------------- Geyser helpers ----------------


def _read_geyser_bedrock_port(server_dir: str) -> Optional[int]:
    cfg = Path(server_dir) / "plugins" / "Geyser-Spigot" / "config.yml"
    if not cfg.exists():
        return None

    for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("port:") and line.startswith("  "):
            try:
                return int(stripped.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _write_geyser_bedrock_port(server_dir: str, new_port: int) -> None:
    cfg = Path(server_dir) / "plugins" / "Geyser-Spigot" / "config.yml"
    if not cfg.exists():
        return

    lines = cfg.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[str] = []
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("port:") and line.startswith("  "):
            out.append(f"  port: {int(new_port)}")
            changed = True
        else:
            out.append(line)

    if not changed:
        out.append("bedrock:")
        out.append(f"  port: {int(new_port)}")

    cfg.write_text("\n".join(out) + "\n", encoding="utf-8")






# ---------------- Port validation + auto-repair ----------------


def _collect_used_ports(servers: list[dict]) -> tuple[set[int], set[int]]:
    """Return (used_tcp_ports, used_udp_ports) from servers.json."""
    used_tcp: set[int] = set()
    used_udp: set[int] = set()

    for s in servers:
        ed = str(s.get("edition") or "")
        p = s.get("port")
        if isinstance(p, int):
            if ed in ("java", "both"):
                used_tcp.add(int(p))
            if ed in ("bedrock", "both"):
                used_udp.add(int(p))

        vp = s.get("voice_port")
        if isinstance(vp, int):
            used_udp.add(int(vp))

    return used_tcp, used_udp


def _update_server_record(server_id: str, mutate_fn) -> dict:
    """Mutate a server record by server_id under the servers.json lock."""

    def _mut(servers: list[dict]) -> list[dict]:
        for s in servers:
            if str(s.get("server_id")) == str(server_id):
                mutate_fn(s)
        return servers

    servers = STATE.mutate(_mut)
    for s in servers:
        if str(s.get("server_id")) == str(server_id):
            return s
    raise ValueError(f"Server {server_id} not found")


def ensure_ports(*, server_config: dict, server_dir: str) -> tuple[int, int, Optional[int]]:
    """Ensure configured ports are usable; auto-fix when needed.

    Returns (java_port, bedrock_port, voice_port)
    """
    server_id = str(server_config.get("server_id") or "")
    edition = str(server_config.get("edition") or "java")
    platform = str(server_config.get("platform") or "")

    # Reserved ranges
    reserved_tcp: List[Tuple[int, int]] = []
    reserved_udp: List[Tuple[int, int]] = []
    try:
        reserved_tcp = get_reserved_ports("tcp")
    except Exception:
        reserved_tcp = []
    try:
        reserved_udp = get_reserved_ports("udp")
    except Exception:
        reserved_udp = []

    servers = read_servers_file()
    used_tcp, used_udp = _collect_used_ports(servers)

    # Remove our own existing ports from "used" so we can keep them if valid
    own_port = server_config.get("port")
    if isinstance(own_port, int):
        used_tcp.discard(int(own_port))
        used_udp.discard(int(own_port))
    own_vp = server_config.get("voice_port")
    if isinstance(own_vp, int):
        used_udp.discard(int(own_vp))

    # --- Base server port ---
    props_path = os.path.join(server_dir, "server.properties")
    props = read_properties(props_path)

    # Determine configured ports from files when possible
    file_java_port: Optional[int] = None
    file_bedrock_port: Optional[int] = None

    if edition in ("java", "both"):
        raw = props.get("server-port")
        if raw:
            try:
                file_java_port = int(raw)
            except Exception:
                file_java_port = None

    if edition in ("bedrock",):
        raw = props.get("server-port")
        if raw:
            try:
                file_bedrock_port = int(raw)
            except Exception:
                file_bedrock_port = None

    if edition in ("both",):
        gp = _read_geyser_bedrock_port(server_dir)
        if gp is not None:
            file_bedrock_port = int(gp)

    # Choose a starting candidate port
    candidate_port: int
    if file_java_port is not None:
        candidate_port = int(file_java_port)
    elif file_bedrock_port is not None:
        candidate_port = int(file_bedrock_port)
    else:
        p = server_config.get("port")
        candidate_port = int(p) if isinstance(p, int) else (25565 if edition in ("java", "both") else 19132)

    need_tcp = edition in ("java", "both")
    need_udp = edition in ("bedrock", "both")

    def _port_ok(p: int) -> bool:
        if not (1 <= int(p) <= 65535):
            return False
        if need_tcp:
            if p in used_tcp or _is_reserved(p, reserved_tcp) or not _can_bind_tcp(p):
                return False
        if need_udp:
            if p in used_udp or _is_reserved(p, reserved_udp) or not _can_bind_udp(p):
                return False
        return True

    if not _port_ok(candidate_port):
        new_port = _alloc_free_port(
            need_tcp=need_tcp,
            need_udp=need_udp,
            used_tcp=used_tcp,
            used_udp=used_udp,
            reserved_tcp=reserved_tcp,
            reserved_udp=reserved_udp,
            start=25565,
            end=65535,
        )
        warn(f"[ports] Port {candidate_port} unavailable; reassigning to {new_port}")
        candidate_port = int(new_port)

        # Update files
        if edition in ("java", "both"):
            write_properties_preserve(props_path, {"server-port": str(candidate_port)})
        if edition == "bedrock":
            write_properties_preserve(props_path, {"server-port": str(candidate_port), "server-portv6": str(candidate_port)})
        if edition == "both":
            _write_geyser_bedrock_port(server_dir, candidate_port)

        # Update servers.json
        _update_server_record(server_id, lambda s: s.__setitem__("port", int(candidate_port)))
        server_config["port"] = int(candidate_port)

    else:
        # If file differs from servers.json, keep them consistent (respect "messed with" configs).
        if isinstance(server_config.get("port"), int) and int(server_config["port"]) != int(candidate_port):
            _update_server_record(server_id, lambda s: s.__setitem__("port", int(candidate_port)))
            server_config["port"] = int(candidate_port)

        # Ensure files match servers.json
        if edition in ("java", "both"):
            write_properties_preserve(props_path, {"server-port": str(candidate_port)})
        if edition == "bedrock":
            write_properties_preserve(props_path, {"server-port": str(candidate_port), "server-portv6": str(candidate_port)})
        if edition == "both":
            _write_geyser_bedrock_port(server_dir, candidate_port)

    java_port = int(candidate_port) if edition in ("java", "both") else 0
    bedrock_port = int(candidate_port) if edition in ("bedrock", "both") else 0

    # --- Voice port ---
    voice_local_port: Optional[int] = None
    if edition in ("java", "both"):
        cfg_path = _voicechat_config_path(server_dir, platform)
        voice_local_port = _read_voice_port_from_voicechat_config(cfg_path)
        if voice_local_port is None:
            vp = server_config.get("voice_port")
            if isinstance(vp, int):
                voice_local_port = int(vp)
            else:
                voice_local_port = 24454

        # Validate voice UDP port
        need_voice = True
        if need_voice:
            # Avoid conflicts with other UDP services (bedrock, other voice ports)
            used_udp_voice = set(used_udp)
            used_udp_voice.add(int(candidate_port))  # bedrock uses UDP on candidate_port for both/bedrock

            def _voice_ok(p: int) -> bool:
                if not (1 <= int(p) <= 65535):
                    return False
                if p in used_udp_voice:
                    return False
                if _is_reserved(p, reserved_udp):
                    return False
                if not _can_bind_udp(p):
                    return False
                return True

            if not _voice_ok(int(voice_local_port)):
                new_vp = _alloc_free_udp_port(used_udp=used_udp_voice, reserved_udp=reserved_udp, start=20000, end=65535)
                warn(f"[ports] Voice UDP port {voice_local_port} unavailable; reassigning to {new_vp}")
                voice_local_port = int(new_vp)
                _update_server_record(server_id, lambda s: s.__setitem__("voice_port", int(voice_local_port)))
                server_config["voice_port"] = int(voice_local_port)

            # Ensure config file is updated (voice_host set later when tunnel starts)
            try:
                _ensure_voicechat_config(server_dir=server_dir, platform=platform, voice_local_port=int(voice_local_port), public_host=None)
            except Exception:
                pass

    return java_port, bedrock_port, voice_local_port


# ---------------- Process / IO piping ----------------


def _make_popen_kwargs() -> dict:
    kw: dict = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name == "nt":
        # Allow CTRL_BREAK_EVENT to target the process group if needed
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    return kw


def _pump_stdout(proc: subprocess.Popen, *, server_id: str, recorder: RuntimeRecorder, stop_evt: threading.Event) -> None:
    try:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            if stop_evt.is_set():
                break
            if line == "":
                break
            clean = line.rstrip("\n").rstrip("\r")
            if clean == "":
                continue
            # Emit to UI
            _emit_console(server_id=server_id, line=clean)
            # Persist for reattach
            recorder.write_console(clean)
    except Exception as e:
        warn(f"[server:{server_id}] output pump error: {e}")


def _write_to_stdin(proc: subprocess.Popen, line: str) -> None:
    if proc.stdin is None:
        return
    try:
        proc.stdin.write(line)
        if not line.endswith("\n"):
            proc.stdin.write("\n")
        proc.stdin.flush()
    except Exception:
        pass


def _pump_stdin_from_parent(proc: subprocess.Popen, *, stop_evt: threading.Event) -> None:
    """Forward our own stdin -> child stdin (for UI/terminal input)."""
    try:
        while not stop_evt.is_set():
            line = sys.stdin.readline()
            if line == "":
                break
            _write_to_stdin(proc, line.rstrip("\n"))
    except Exception:
        pass


def _pump_control_file(proc: subprocess.Popen, *, control_path: Path, stop_evt: threading.Event) -> None:
    """Poll runtime/control.ndjson for commands from other CLI invocations."""
    pos = 0
    while not stop_evt.is_set():
        try:
            if not control_path.exists():
                time.sleep(0.25)
                continue

            size = control_path.stat().st_size
            if size < pos:
                pos = 0

            with open(control_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(pos)
                while not stop_evt.is_set():
                    line = f.readline()
                    if not line:
                        break
                    pos = f.tell()
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    t = obj.get("t")
                    if t == "stdin":
                        payload = obj.get("line")
                        if isinstance(payload, str):
                            _write_to_stdin(proc, payload)
                    elif t == "stop":
                        _write_to_stdin(proc, "stop")
                        # also try terminate as fallback
                        try:
                            proc.terminate()
                        except Exception:
                            pass
        except Exception:
            pass

        time.sleep(0.25)


# ---------------- Stop commands (D1-friendly) ----------------


def stop_server(*, server_id: str, timeout_s: float = 15.0) -> bool:
    """Stop a running server by server_id using runtime state/control files."""
    sid = str(server_id)
    st_path = runtime_state_path(sid)
    ctl_path = runtime_control_path(sid)

    if not st_path.exists():
        return False

    try:
        state = json.loads(st_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}

    pid = int(state.get("server_pid") or 0)
    mgr_pid = int(state.get("manager_pid") or 0)
    detached = bool(state.get("detached_process"))
    java_port = int(state.get("java_port") or 0)

    if pid <= 0 and detached and java_port > 0:
        pid = _pid_listening_on_tcp_port(java_port)

    # Ask manager to stop gracefully if it exists
    try:
        ctl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ctl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": "stop", "timestamp": time.time()}, ensure_ascii=False) + "\n")
    except Exception:
        pass

    end = time.time() + timeout_s
    while time.time() < end:
        # Detached launchers may not expose a stable PID in state, so keep re-resolving.
        if not pid and detached and java_port > 0:
            pid = _pid_listening_on_tcp_port(java_port)
        if pid and not _pid_exists(pid):
            _mark_runtime_stopped(sid, reason="pid_exited")
            return True
        if detached and java_port > 0 and not is_tcp_open("127.0.0.1", java_port):
            _mark_runtime_stopped(sid, reason="port_closed")
            return True
        # if manager died, we still may need to kill pid
        time.sleep(0.25)

    # Fallback: kill server pid
    if not pid and detached and java_port > 0:
        pid = _pid_listening_on_tcp_port(java_port)

    if pid:
        _terminate_pid(pid, timeout_s=8.0)

    # As a last resort, kill manager too
    if mgr_pid and _pid_exists(mgr_pid):
        _terminate_pid(mgr_pid, timeout_s=4.0)

    # Confirm
    if pid:
        stopped = not _pid_exists(pid)
        if stopped:
            _mark_runtime_stopped(sid, reason="pid_terminated")
        return stopped

    if detached and java_port > 0:
        stopped = not is_tcp_open("127.0.0.1", java_port)
        if stopped:
            _mark_runtime_stopped(sid, reason="detached_port_closed")
        return stopped

    _mark_runtime_stopped(sid, reason="no_active_process")
    return True


def stop_all(timeout_s: float = 15.0) -> List[str]:
    """Stop all servers that have runtime state files. Returns list of server_ids stopped."""
    stopped: List[str] = []
    base = runtime_dir()
    try:
        if not base.exists():
            return []
        for child in base.iterdir():
            if not child.is_dir():
                continue
            sid = child.name
            if stop_server(server_id=sid, timeout_s=timeout_s):
                stopped.append(sid)
    except Exception:
        return stopped
    return stopped


# ---------------- Main runner ----------------


def _find_java_cmd(server_dir: str) -> str:
    jdk_dir = Path(server_dir) / "jdk"
    suffix = ".exe" if os.name == "nt" else ""

    direct = jdk_dir / "bin" / f"java{suffix}"
    if direct.exists():
        return str(direct)

    if jdk_dir.exists():
        for subdir in jdk_dir.iterdir():
            if not subdir.is_dir():
                continue
            candidate = subdir / "bin" / f"java{suffix}"
            if candidate.exists():
                return str(candidate)

    raise RuntimeError(f"Java executable not found in {jdk_dir}")


def run_server(edition: str, platform: str, version: str, name: str):
    server_config = get_per_server_config(platform, version, name)

    # Prefer the edition recorded in servers.json (CLI arg is still required for now)
    edition = str(server_config.get("edition") or edition)

    ram = server_config.get("ram")
    eula = server_config.get("eula")
    folder = server_config.get("folder")

    server_id = str(server_config.get("server_id") or "")
    sticky_address = bool(server_config.get("sticky_address", True))
    tunneling = bool(server_config.get("tunneling", True))

    if not server_id:
        server_id = str(uuid.uuid4())
        server_config["server_id"] = server_id

    recorder = RuntimeRecorder(server_id)

    # Keep edge reservations in sync before opening (best-effort)
    try:
        sync_desired_sticky_servers()
    except Exception as e:
        warn(f"[tunnel] warning: could not sync reservations: {e}")

    info(f"Running {edition} server: {platform}-{version}-{name} with {ram}MB RAM and EULA accepted: {eula}")

    server_dir = os.path.join("servers", str(folder))

    if not os.path.isdir(server_dir):
        error(f"Server folder missing: {server_dir}")
        return

    # Ensure ports are valid and configs are consistent
    try:
        java_port, bedrock_port, voice_local_port = ensure_ports(server_config=server_config, server_dir=server_dir)
    except Exception as e:
        error(f"Port validation failed: {e}")
        return

    # Process handles
    proc: Optional[subprocess.Popen] = None

    # Runtime state
    state: Dict[str, Any] = {
        "server_id": server_id,
        "platform": platform,
        "version": version,
        "name": name,
        "folder": folder,
        "edition": edition,
        "state": "starting",
        "manager_pid": os.getpid(),
        "server_pid": None,
        "java_port": java_port,
        "bedrock_port": bedrock_port,
        "voice_port": voice_local_port,
        "tunneling": tunneling,
        "sticky_address": sticky_address,
        "started_at": time.time(),
    }
    recorder.write_state(state)
    _emit_state(
        server_id=server_id,
        state="starting",
        **{k: v for k, v in state.items() if k not in ("state", "server_id")},
    )


    stop_evt = threading.Event()

    tunnel_started = False
    tunnel_info = None

    # Track readiness
    tcp_ready_once = False
    udp_ready_once = False

    try:
        # ---- Start tunnel first for Java/both (so voice_host can be written before load) ----
        if tunneling and edition in ("java", "both"):
            services: List[Dict[str, Any]] = [{"svc": "mc", "proto": "tcp", "local": int(java_port)}]

            if voice_local_port is not None:
                services.append({"svc": "voice", "proto": "udp", "local": int(voice_local_port)})

            if edition == "both":
                services.append({"svc": "bedrock", "proto": "udp", "local": int(bedrock_port)})

            try:
                tunnel_info = TUNNEL.start(server_id=server_id, sticky_address=sticky_address, services=services, share_game_port=edition == "both")
                tunnel_started = True

                # Configure Simple Voice Chat advertised host/port
                if voice_local_port is not None and tunnel_info:
                    voice_pub = tunnel_info.public_port("voice")
                    if voice_pub:
                        public_host = f"{tunnel_info.subdomain}.{tunnel_info.domain_suffix}:{voice_pub}"
                        try:
                            _ensure_voicechat_config(
                                server_dir=server_dir,
                                platform=platform,
                                voice_local_port=int(voice_local_port),
                                public_host=public_host,
                            )
                        except Exception as e:
                            warn(f"[voicechat] warning: could not write voice chat config: {e}")

            except Exception as e:
                warn(f"[tunnel] failed to start (continuing without tunnel): {e}")

        # ---- Start the server process ----
        popen_kw = _make_popen_kwargs()

        if edition in ("java", "both"):
            if platform in ["forge", "neoforge"]:
                run_script = "run.bat" if os.name == "nt" else "run.sh"
                run_script_path = os.path.join(server_dir, run_script)

                if os.path.exists(run_script_path):
                    info(f"Using {platform.capitalize()} {run_script} script...")

                    # Update user_jvm_args.txt with correct RAM settings (best-effort)
                    user_jvm_args = os.path.join(server_dir, "user_jvm_args.txt")
                    if os.path.exists(user_jvm_args) and isinstance(ram, int):
                        import re

                        with open(user_jvm_args, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        content = re.sub(r"-Xmx\d+[GMm]", f"-Xmx{ram}M", content)
                        content = re.sub(r"-Xms\d+[GMm]", f"-Xms{ram}M", content)

                        content = content.replace("# -Xmx", "-Xmx").replace("# -Xms", "-Xms")

                        with open(user_jvm_args, "w", encoding="utf-8") as f:
                            f.write(content)

                    if os.name == "nt":
                        proc = subprocess.Popen(["cmd", "/c", "run.bat", "nogui"], cwd=server_dir, **popen_kw)
                    else:
                        proc = subprocess.Popen(["sh", "run.sh", "nogui"], cwd=server_dir, **popen_kw)
                else:
                    warn(f"{run_script} not found, falling back to direct JAR execution...")
                    java_cmd = _find_java_cmd(server_dir)
                    jar = f"{platform}-{version}.jar"
                    proc = subprocess.Popen(
                        [java_cmd, f"-Xmx{ram}M", f"-Xms{ram}M", "-jar", jar, "nogui"],
                        cwd=server_dir,
                        **popen_kw,
                    )
            else:
                java_cmd = _find_java_cmd(server_dir)
                jar = f"{platform}-{version}.jar"
                proc = subprocess.Popen(
                    [
                        java_cmd,
                        f"-Xmx{ram}M",
                        f"-Xms{ram}M",
                        "-XX:+UseG1GC",
                        "-XX:+ParallelRefProcEnabled",
                        "-XX:MaxGCPauseMillis=200",
                        "-XX:+UnlockExperimentalVMOptions",
                        "-XX:+DisableExplicitGC",
                        "-XX:+AlwaysPreTouch",
                        "-XX:G1NewSizePercent=30",
                        "-XX:G1MaxNewSizePercent=40",
                        "-XX:G1HeapRegionSize=8M",
                        "-XX:G1ReservePercent=20",
                        "-XX:G1HeapWastePercent=5",
                        "-XX:G1MixedGCCountTarget=4",
                        "-XX:InitiatingHeapOccupancyPercent=15",
                        "-XX:G1MixedGCLiveThresholdPercent=90",
                        "-XX:G1RSetUpdatingPauseTimePercent=5",
                        "-XX:SurvivorRatio=32",
                        "-XX:+PerfDisableSharedMem",
                        "-XX:MaxTenuringThreshold=1",
                        "-Daikars.new.flags=true",
                        "-Dusing.aikars.flags=https://mcutils.com",
                        "-jar",
                        jar,
                        "--nogui",
                    ],
                    cwd=server_dir,
                    **popen_kw,
                )

        elif edition == "bedrock":
            exe = os.path.join(server_dir, "bedrock_server.exe")
            proc = subprocess.Popen([exe], cwd=server_dir, **popen_kw)

        else:
            raise ValueError("edition must be 'java', 'bedrock', or 'both'")

        assert proc is not None

        # Update runtime state with PIDs
        state["server_pid"] = int(proc.pid)
        state["state"] = "running"
        recorder.write_state(state)

        # Start piping
        threading.Thread(target=_pump_stdout, args=(proc,), kwargs={"server_id": server_id, "recorder": recorder, "stop_evt": stop_evt}, daemon=True).start()
        threading.Thread(target=_pump_stdin_from_parent, args=(proc,), kwargs={"stop_evt": stop_evt}, daemon=True).start()
        threading.Thread(target=_pump_control_file, args=(proc,), kwargs={"control_path": recorder.control_path, "stop_evt": stop_evt}, daemon=True).start()

        # ---- Readiness + tunnel (bedrock-only starts tunnel after readiness) ----
        if edition == "java":
            tcp_ready_once = wait_tcp_open("127.0.0.1", int(java_port), timeout_s=45.0)
            if not tcp_ready_once:
                warn(f"[tunnel] Server never opened TCP port {java_port}; tunnel may not work until it does.")
            if tunnel_started and tunnel_info and tcp_ready_once:
                info(f"[tunnel] Java join: {tunnel_info.public_tcp_address}")
                if tunnel_info.public_voice_address:
                    info(
                        f"[voicechat] Voice should auto-connect (voice_host set). Public voice: {tunnel_info.public_voice_address}"
                    )

        elif edition == "bedrock":
            udp_ready_once = wait_bedrock_udp_ready("127.0.0.1", int(bedrock_port), timeout_s=45.0)
            if udp_ready_once and tunneling:
                try:
                    tunnel_info = TUNNEL.start(
                        server_id=server_id,
                        sticky_address=sticky_address,
                        services=[{"svc": "bedrock", "proto": "udp", "local": int(bedrock_port)}],
                    )
                    tunnel_started = True
                    info(f"[tunnel] Bedrock join: {tunnel_info.public_udp_address}")
                except Exception as e:
                    warn(f"[tunnel] failed to start (continuing without tunnel): {e}")
            elif not udp_ready_once:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; not starting tunnel.")

        elif edition == "both":
            tcp_ready_once = wait_tcp_open("127.0.0.1", int(java_port), timeout_s=45.0)
            udp_ready_once = wait_bedrock_udp_ready("127.0.0.1", int(bedrock_port), timeout_s=45.0)

            if not tcp_ready_once:
                warn(f"[tunnel] Java never opened TCP port {java_port}; join may fail until it does.")
            if not udp_ready_once:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; Bedrock join may fail until it does.")

            if tunnel_started and tunnel_info and tcp_ready_once:
                info(f"[tunnel] Java join: {tunnel_info.public_tcp_address}")
            if tunnel_started and tunnel_info and udp_ready_once:
                info(f"[tunnel] Bedrock join: {tunnel_info.public_udp_address}")
            if tunnel_started and tunnel_info and tunnel_info.public_voice_address:
                info(
                    f"[voicechat] Voice should auto-connect (voice_host set). Public voice: {tunnel_info.public_voice_address}"
                )

        # Announce running state
        tunnel_payload = (
            {
                "subdomain": getattr(tunnel_info, "subdomain", None),
                "domain_suffix": getattr(tunnel_info, "domain_suffix", None),
                "public_tcp_address": getattr(tunnel_info, "public_tcp_address", None),
                "public_udp_address": getattr(tunnel_info, "public_udp_address", None),
                "public_voice_address": getattr(tunnel_info, "public_voice_address", None),
            }
            if tunnel_info
            else None
        )
        state["ready"] = {"tcp": bool(tcp_ready_once), "udp": bool(udp_ready_once)}
        state["tunnel"] = tunnel_payload
        recorder.write_state(state)

        _emit_state(
            server_id=server_id,
            state="running",
            java_port=java_port,
            bedrock_port=bedrock_port,
            voice_port=voice_local_port,
            tunnel=tunnel_payload,
        )

        # ---- Monitor: stop tunnel when server exits or java TCP port closes ----
        detached_server_detected = False
        while True:
            code = proc.poll()
            if code is not None:
                # Some launch scripts (notably certain forge/neoforge run scripts) can
                # spawn the real JVM process and then exit immediately. In that case the
                # wrapper process is gone but the server is still online.
                if edition in ("java", "both") and is_tcp_open("127.0.0.1", int(java_port)):
                    if not detached_server_detected:
                        detached_server_detected = True
                        state["server_pid"] = None
                        state["detached_process"] = True
                        state["state"] = "running"
                        recorder.write_state(state)
                        warn(
                            "[runtime] launcher process exited but server port is still open; "
                            "keeping state as running (detached server process detected)."
                        )
                    time.sleep(1.0)
                    continue
                break

            if tunnel_started and tcp_ready_once and edition in ("java", "both"):
                if not is_tcp_open("127.0.0.1", int(java_port)):
                    warn(f"[tunnel] Local TCP port {java_port} closed; stopping tunnel.")
                    TUNNEL.stop()
                    tunnel_started = False

            time.sleep(1.0)

        exit_code = proc.poll()
        state["state"] = "stopped"
        state["exit_code"] = exit_code
        recorder.write_state(state)
        _emit_state(server_id=server_id, state="stopped", exit_code=exit_code)

    finally:
        stop_evt.set()
        if tunnel_started:
            try:
                TUNNEL.stop()
            except Exception:
                pass

        if proc and proc.poll() is None:
            try:
                _write_to_stdin(proc, "stop")
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        recorder.close()
