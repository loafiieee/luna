# run_server.py
import json
import os
import subprocess
import sys
import time
import threading
import socket
import struct
from typing import Optional, Dict, Any, List, Tuple

import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import tunnel + emitter in a way that works whether this is executed as a script
# (imports like utils.*) or imported as a module (imports like backend.utils.*).
try:  # noqa: E402
    from utils.tunnel import TunnelRunner  # type: ignore
    from utils.emit import info, warn, error  # type: ignore
    from utils.get_reseved_ports import get_reserved_ports  # type: ignore
except Exception:  # pragma: no cover
    from backend.utils.tunnel import TunnelRunner  # type: ignore
    from backend.utils.emit import info, warn, error  # type: ignore
    from backend.utils.get_reseved_ports import get_reserved_ports  # type: ignore


TUNNEL = TunnelRunner(
    edge_url="wss://tunnel.loafiieee.com",
    domain_suffix="mc.loafiieee.com",
    on_status=lambda s: info(f"[tunnel] {s}"),
)

def _pump_process_output(proc, prefix):
    try:
        if not proc.stdout:
            return
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            info(f"[{prefix}] {line.rstrip()}")
    except Exception as e:
        warn(f"[{prefix}] output pump error: {e}")


# ---------------- Servers JSON helpers ----------------



def reconcile_servers_with_disk() -> None:
    """Reconcile servers/servers.json with the actual folders in servers/.

    - Removes entries whose server folder no longer exists.
    - Adds entries for server folders that exist but are missing from servers.json.

    This is intentionally conservative: it does not try to infer RAM/ports/EULA beyond safe defaults.
    Further migrations (server_id, voice_port, etc.) are handled by read_servers_file().
    """
    servers_dir = "servers"
    os.makedirs(servers_dir, exist_ok=True)

    path = os.path.join(servers_dir, "servers.json")

    # If servers.json doesn't exist yet, create it.
    if not os.path.exists(path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)
        os.replace(tmp, path)

    # Load existing (best-effort)
    try:
        with open(path, "r", encoding="utf-8") as f:
            servers = json.load(f)
        if not isinstance(servers, list):
            servers = []
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
                # ensure folder is stored (helps future reads)
                s["folder"] = fld
                by_folder[fld] = s

    # Gather actual folders on disk
    disk_folders = [
        d for d in os.listdir(servers_dir)
        if os.path.isdir(os.path.join(servers_dir, d))
    ]

    changed = False
    new_servers: list[dict] = []

    # Keep only entries that still exist on disk
    disk_set = set(disk_folders)
    for fld, s in by_folder.items():
        if fld in disk_set:
            new_servers.append(s)
        else:
            changed = True

    # Add any folders missing from servers.json
    for fld in disk_folders:
        if fld in by_folder:
            continue

        parts = fld.split("-", 2)
        if len(parts) != 3:
            warn(f"[servers] skipping unrecognized folder name: {fld}")
            continue

        platform, version, name = parts
        new_servers.append({
            "server_id": str(uuid.uuid4()),
            "edition": "java",  # safe default (can't reliably infer)
            "platform": platform,
            "version": version,
            "name": name,
            "folder": fld,
            "ram": 2048,
            "eula": False,
            "sticky_address": True,
        })
        changed = True

    if changed:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_servers, f, indent=4)
        os.replace(tmp, path)

    # Run migrations/normalization (voice ports, etc.)
    try:
        read_servers_file()
    except Exception as e:
        warn(f"[servers] warning: post-reconcile migration failed: {e}")


def read_servers_file() -> list:
    path = "servers/servers.json"
    with open(path, "r", encoding="utf-8") as f:
        servers = json.load(f)

    # Migration: ensure every server has server_id, sticky_address, folder, and voice_port (Java servers)
    changed = False

    # Pre-compute used UDP ports (voice + bedrock) so we can safely allocate new voice ports.
    used_udp_ports: set[int] = set()
    for s in servers:
        vp = s.get("voice_port")
        if isinstance(vp, int):
            used_udp_ports.add(int(vp))
        # Bedrock / "both" uses UDP on the server port (or a Geyser port)
        ed = str(s.get("edition") or "")
        if ed in ("bedrock", "both"):
            p = s.get("port")
            if isinstance(p, int):
                used_udp_ports.add(int(p))

    reserved_udp: List[Tuple[int, int]] = []
    try:
        reserved_udp = get_reserved_ports("udp")
    except Exception:
        reserved_udp = []

    def _is_reserved_udp(p: int) -> bool:
        for a, b in reserved_udp:
            if a <= p <= b:
                return True
        return False

    def _alloc_voice_port() -> int:
        # Simple Voice Chat default is 24454; we allocate per-server to allow multiple servers on one host.
        for _ in range(20000):
            cand = int.from_bytes(os.urandom(2), "big")  # 0-65535
            cand = 20000 + (cand % (65535 - 20000))
            if cand in used_udp_ports:
                continue
            if _is_reserved_udp(cand):
                continue
            used_udp_ports.add(cand)
            return cand
        # fallback: linear scan
        for cand in range(20000, 65536):
            if cand in used_udp_ports:
                continue
            if _is_reserved_udp(cand):
                continue
            used_udp_ports.add(cand)
            return cand
        raise RuntimeError("No free UDP ports left for voice chat")

    for s in servers:
        if not s.get("server_id"):
            s["server_id"] = str(uuid.uuid4())
            changed = True
        if "sticky_address" not in s:
            s["sticky_address"] = True
            changed = True
        # ensure folder field (older entries)
        if not s.get("folder") and s.get("platform") and s.get("version") and s.get("name"):
            s["folder"] = f"{s['platform']}-{s['version']}-{s['name']}"
            changed = True

        # Ensure edition exists (older servers.json may not have it)
        if not s.get("edition"):
            # Best guess: assume java
            s["edition"] = "java"
            changed = True

        # Allocate voice port for Java servers so multiple can run concurrently
        ed = str(s.get("edition") or "")
        if ed in ("java", "both"):
            vp = s.get("voice_port")
            if not isinstance(vp, int) or not (1 <= int(vp) <= 65535):
                s["voice_port"] = _alloc_voice_port()
                changed = True

    if changed:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(servers, f, indent=4)
        os.replace(tmp, path)

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

    # Always sync (even empty) so the edge can deallocate orphan sticky ports
    TUNNEL.sync_desired(desired=desired_unique)


def get_per_server_config(platform: str, version: str, name: str) -> dict:
    servers = read_servers_file()
    for server in servers:
        if server.get("platform") == platform and server.get("version") == version and server.get("name") == name:
            return server
    raise ValueError(f"No configuration found for server: {platform}-{version}-{name}")


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

    # append missing keys at end
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

        # 0x01 + ping_id (8) + magic (16) + client_guid (8)
        pkt = b"\x01" + struct.pack(">Q", ping_id) + _RAKNET_MAGIC + struct.pack(">Q", client_guid)
        s.sendto(pkt, (host, port))

        data, _addr = s.recvfrom(2048)
        if not data:
            return False
        # pong: 0x1c ...
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
    """Return the most likely voicechat-server.properties location.

    Mod loaders: config/voicechat/voicechat-server.properties
    Plugin servers: plugins/voicechat/voicechat-server.properties
    """
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


def _ensure_voicechat_config(
    *,
    server_dir: str,
    platform: str,
    voice_local_port: int,
    public_host: Optional[str],
) -> None:
    """Create/update voicechat-server.properties for Simple Voice Chat.

    - Sets port=<voice_local_port> (server bind)
    - Sets voice_host=<public_host> (client connect target)
      where public_host may include a port (recommended).
    """
    cfg_path = _voicechat_config_path(server_dir, platform)
    updates: Dict[str, str] = {"port": str(int(voice_local_port))}
    if public_host:
        updates["voice_host"] = public_host
    write_properties_preserve(cfg_path, updates)


# ---------------- Main runner ----------------


def run_server(edition: str, platform: str, version: str, name: str):
    server_config = get_per_server_config(platform, version, name)
    ram = server_config.get("ram")
    eula = server_config.get("eula")
    folder = server_config.get("folder")

    server_id = str(server_config.get("server_id") or "")
    sticky_address = bool(server_config.get("sticky_address", True))
    if not server_id:
        # should not happen due to migration, but keep safe
        server_id = str(uuid.uuid4())
        server_config["server_id"] = server_id

    # Keep edge reservations in sync before opening (best-effort)
    try:
        sync_desired_sticky_servers()
    except Exception as e:
        warn(f"[tunnel] warning: could not sync reservations: {e}")

    info(f"Running {edition} server: {platform}-{version}-{name} with {ram}MB RAM and EULA accepted: {eula}")

    server_dir = os.path.join("servers", folder)

    # Read server.properties to get ports
    props_path = os.path.join(server_dir, "server.properties")
    props = read_properties(props_path)

    # Java uses server-port
    java_port = int(props.get("server-port", "25565"))

    # Bedrock / Geyser generally uses a separate UDP port; older code reused server-port
    bedrock_port = int(props.get("server-port", "19132"))

    # Voice chat local UDP port (per-server so multiple servers can run)
    voice_local_port: Optional[int] = None
    if edition in ("java", "both"):
        # Prefer the existing voicechat config if present, else servers.json voice_port
        cfg_path = _voicechat_config_path(server_dir, platform)
        voice_local_port = _read_voice_port_from_voicechat_config(cfg_path)
        if voice_local_port is None:
            vp = server_config.get("voice_port")
            if isinstance(vp, int) and 1 <= int(vp) <= 65535:
                voice_local_port = int(vp)
            else:
                # Last-resort fallback (should be prevented by read_servers_file migration)
                voice_local_port = 24454

    proc: Optional[subprocess.Popen] = None
    tunnel_started = False
    tunnel_info = None

    # Track readiness to avoid stopping the tunnel during startup
    tcp_ready_once = False

    try:
        # ---- If Java (or both), open tunnel FIRST so we can write voice_host before the server loads config ----
        if edition in ("java", "both"):
            services: List[Dict[str, Any]] = [{"svc": "mc", "proto": "tcp", "local": int(java_port)}]

            if voice_local_port is not None:
                services.append({"svc": "voice", "proto": "udp", "local": int(voice_local_port)})

            if edition == "both":
                services.append({"svc": "bedrock", "proto": "udp", "local": int(bedrock_port)})

            try:
                tunnel_info = TUNNEL.start(server_id=server_id, sticky_address=sticky_address, services=services)
                tunnel_started = True

                # Configure Simple Voice Chat to advertise the tunnel address/port to clients
                if voice_local_port is not None:
                    voice_pub = tunnel_info.public_port("voice") if tunnel_info else None
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
        if edition in ("java", "both"):
            if platform in ["forge", "neoforge"]:
                run_bat = os.path.join(server_dir, "run.bat")
                if os.path.exists(run_bat):
                    info(f"Using {platform.capitalize()} run.bat script...")

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

                    proc = subprocess.Popen(["cmd", "/c", "run.bat", "nogui"], cwd=server_dir)
                else:
                    warn("run.bat not found, falling back to direct JAR execution...")
                    jdk_dir = os.path.join(server_dir, "jdk")
                    subdirs = [d for d in os.listdir(jdk_dir) if os.path.isdir(os.path.join(jdk_dir, d))]
                    if subdirs:
                        jdk_subdir = subdirs[0]
                        java_cmd = os.path.join(jdk_dir, jdk_subdir, "bin", "java.exe")
                    else:
                        java_cmd = os.path.join(jdk_dir, "bin", "java.exe")

                    jar = f"{platform}-{version}.jar"
                    proc = subprocess.Popen(
                        [java_cmd, f"-Xmx{ram}M", f"-Xms{ram}M", "-jar", jar, "nogui"],
                        cwd=server_dir,
                    )
            else:
                jdk_dir = os.path.join(server_dir, "jdk")
                subdirs = [d for d in os.listdir(jdk_dir) if os.path.isdir(os.path.join(jdk_dir, d))]
                if subdirs:
                    jdk_subdir = subdirs[0]
                    java_cmd = os.path.join(jdk_dir, jdk_subdir, "bin", "java.exe")
                else:
                    java_cmd = os.path.join(jdk_dir, "bin", "java.exe")

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
                )

        elif edition == "bedrock":
            exe = os.path.join(server_dir, "bedrock_server.exe")
            proc = subprocess.Popen([exe], cwd=server_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            threading.Thread(target=_pump_process_output, args=(proc, 'server'), daemon=True).start()

        else:
            raise ValueError("edition must be 'java', 'bedrock', or 'both'")

        assert proc is not None

        # ---- Readiness + tunnel (bedrock-only starts tunnel after readiness) ----
        if edition == "java":
            tcp_ready_once = wait_tcp_open("127.0.0.1", java_port, timeout_s=45.0)
            if not tcp_ready_once:
                warn(f"[tunnel] Server never opened TCP port {java_port}; tunnel may not work until it does.")
            if tunnel_started and tunnel_info and tcp_ready_once:
                info(f"[tunnel] Java join: {tunnel_info.public_tcp_address}")

                if tunnel_info.public_voice_address:
                    info(f"[voicechat] Voice should auto-connect (voice_host set). Public voice: {tunnel_info.public_voice_address}")

        elif edition == "bedrock":
            if wait_bedrock_udp_ready("127.0.0.1", bedrock_port, timeout_s=45.0):
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
            else:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; not starting tunnel.")

        elif edition == "both":
            # Wait for both interfaces to come up, but we may already have the tunnel up.
            tcp_ready_once = wait_tcp_open("127.0.0.1", java_port, timeout_s=45.0)
            udp_ready = wait_bedrock_udp_ready("127.0.0.1", bedrock_port, timeout_s=45.0)

            if not tcp_ready_once:
                warn(f"[tunnel] Java never opened TCP port {java_port}; join may fail until it does.")
            if not udp_ready:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; Bedrock join may fail until it does.")

            if tunnel_started and tunnel_info and tcp_ready_once:
                info(f"[tunnel] Java join: {tunnel_info.public_tcp_address}")
            if tunnel_started and tunnel_info and udp_ready:
                info(f"[tunnel] Bedrock join: {tunnel_info.public_udp_address}")
            if tunnel_started and tunnel_info and tunnel_info.public_voice_address:
                info(f"[voicechat] Voice should auto-connect (voice_host set). Public voice: {tunnel_info.public_voice_address}")

        # ---- Monitor: stop tunnel when server exits or java TCP port closes ----
        while True:
            code = proc.poll()
            if code is not None:
                break

            # Only stop the tunnel when the server had been ready at least once
            if tunnel_started and tcp_ready_once and edition in ("java", "both"):
                if not is_tcp_open("127.0.0.1", java_port):
                    warn(f"[tunnel] Local TCP port {java_port} closed; stopping tunnel.")
                    TUNNEL.stop()
                    tunnel_started = False

            time.sleep(1.0)

    finally:
        if tunnel_started:
            TUNNEL.stop()

        if proc and proc.poll() is None:
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
