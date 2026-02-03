# run_server.py
import json
import os
import subprocess
import sys
import time
import socket
import struct
from typing import Optional, Dict

import uuid
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import tunnel + emitter in a way that works whether this is executed as a script
# (imports like utils.*) or imported as a module (imports like backend.utils.*).
try:  # noqa: E402
    from utils.tunnel import TunnelRunner  # type: ignore
    from utils.emit import info, warn, error  # type: ignore
except Exception:  # pragma: no cover
    from backend.utils.tunnel import TunnelRunner  # type: ignore
    from backend.utils.emit import info, warn, error  # type: ignore


TUNNEL = TunnelRunner(
    edge_url="wss://tunnel.loafiieee.com",
    domain_suffix="mc.loafiieee.com",
    on_status=lambda s: info(f"[tunnel] {s}"),
)


def read_servers_file() -> list:
    path = "servers/servers.json"
    with open(path, "r", encoding="utf-8") as f:
        servers = json.load(f)

    # Migration: ensure every server has server_id and sticky_address
    changed = False
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

    if changed:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(servers, f, indent=4)
        os.replace(tmp, path)

    return servers


def sync_desired_sticky_servers() -> None:
    """Best-effort: tell the edge which sticky servers still exist locally (folder exists)."""
    servers = read_servers_file()
    desired: list[str] = []
    for s in servers:
        if not s.get("sticky_address", True):
            continue
        folder = s.get("folder")
        if not folder:
            continue
        server_dir = os.path.join("servers", folder)
        if os.path.isdir(server_dir):
            desired.append(str(s["server_id"]))

    # de-dupe while preserving order
    seen = set()
    desired_unique = []
    for sid in desired:
        if sid in seen:
            continue
        seen.add(sid)
        desired_unique.append(sid)

    if desired_unique:
        TUNNEL.sync_desired(desired_server_ids=desired_unique)
    else:
        # still sync empty to allow edge to drop all reservations if user deleted everything
        TUNNEL.sync_desired(desired_server_ids=[])


def get_per_server_config(platform: str, version: str, name: str) -> dict:
    servers = read_servers_file()
    for server in servers:
        if (
            server["platform"] == platform
            and server["version"] == version
            and server["name"] == name
        ):
            return server
    raise ValueError(f"No configuration found for server: {platform}-{version}-{name}")


def read_properties(path: str) -> Dict[str, str]:
    """
    Reads Minecraft-style key=value files (ignores comments and blanks).
    """
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
    """
    Sends a RakNet Unconnected Ping (0x01) and expects Unconnected Pong (0x1c).
    This is the standard way to detect a Bedrock server on UDP.
    """
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

    # Bedrock server.properties also usually uses server-port, but if yours differs, update here.
    bedrock_port = int(props.get("server-port", "19132"))

    proc: Optional[subprocess.Popen] = None
    tunnel_started = False

    try:
        # ---- Start the server process first ----
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
            proc = subprocess.Popen([exe], cwd=server_dir)

        else:
            raise ValueError("edition must be 'java', 'bedrock', or 'both'")

        assert proc is not None

        # ---- Wait for readiness, THEN start tunnel ----
        if edition == "java":
            if wait_tcp_open("127.0.0.1", java_port, timeout_s=45.0):
                try:
                    info_t = TUNNEL.start(server_id=server_id, sticky_address=sticky_address, tcp_local=java_port)
                    tunnel_started = True
                    info(f"[tunnel] Java join: {info_t.public_tcp_address}")
                except Exception as e:
                    warn(f"[tunnel] failed to start (continuing without tunnel): {e}")
            else:
                warn(f"[tunnel] Server never opened TCP port {java_port}; not starting tunnel.")

        elif edition == "bedrock":
            if wait_bedrock_udp_ready("127.0.0.1", bedrock_port, timeout_s=45.0):
                try:
                    info_t = TUNNEL.start(server_id=server_id, sticky_address=sticky_address, udp_local=bedrock_port)
                    tunnel_started = True
                    info(f"[tunnel] Bedrock join: {info_t.public_udp_address}")
                except Exception as e:
                    warn(f"[tunnel] failed to start (continuing without tunnel): {e}")
            else:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; not starting tunnel.")

        elif edition == "both":
            ok_tcp = wait_tcp_open("127.0.0.1", java_port, timeout_s=45.0)
            ok_udp = wait_bedrock_udp_ready("127.0.0.1", bedrock_port, timeout_s=45.0)

            if not ok_tcp:
                warn(f"[tunnel] Java never opened TCP port {java_port}; not starting tunnel (both).")
            elif not ok_udp:
                warn(f"[tunnel] Bedrock never answered UDP ping on {bedrock_port}; not starting tunnel (both).")
            else:
                try:
                    info_t = TUNNEL.start(server_id=server_id, sticky_address=sticky_address, tcp_local=java_port, udp_local=bedrock_port)
                    tunnel_started = True
                    info(f"[tunnel] Java join: {info_t.public_tcp_address}")
                    info(f"[tunnel] Bedrock join: {info_t.public_udp_address}")
                except Exception as e:
                    warn(f"[tunnel] failed to start (continuing without tunnel): {e}")

        # ---- Monitor: stop tunnel when server exits or java TCP port closes ----
        while True:
            code = proc.poll()
            if code is not None:
                break

            if tunnel_started and edition in ("java", "both"):
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
