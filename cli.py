from pathlib import Path
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

from backend.utils.get_versions import *
from backend.utils.get_platforms import *
from backend.utils.get_reseved_ports import *
from backend.scripts.server_installer import *
from backend.scripts.run_server import *
from backend.scripts.delete_server import *
from backend.utils.paths import configure_data_root, servers_dir, runtime_state_path, servers_state_path
from backend.utils.state import STATE

# Modrinth support
from backend.utils.modrinth import *

# Logging/event emitter (supports human + JSON)
from backend.utils.emit import *


def _parse_bool(v: str) -> bool:
    return v.lower() in {"true", "1", "yes", "y"}


def _maybe_sync() -> None:
    """Best-effort: keep edge reservations in sync (doesn't block offline/local usage)."""
    try:
        sync_desired_sticky_servers()
    except Exception as e:
        warn(f"[tunnel] warning: could not sync reservations: {e}")


def _usage_install() -> None:
    error("Usage: cli.py install_server <edition> <platform> <version> <name> <RAM> <EULA> [sticky_address]")
    error("  sticky_address: true/false (default true)")


def _parse_int_arg(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Invalid integer for {name}: {raw}")


def _resolve_modrinth_download_dir(server_path: Path, project_type: str) -> Path:
    plugins_dir = server_path / "plugins"
    mods_dir = server_path / "mods"
    datapacks_dir = server_path / "world" / "datapacks"

    if project_type == "datapack":
        datapacks_dir.mkdir(parents=True, exist_ok=True)
        return datapacks_dir

    if project_type == "plugin":
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    if project_type == "mod":
        mods_dir.mkdir(parents=True, exist_ok=True)
        return mods_dir

    # Fallback behavior for other project types.
    if plugins_dir.exists():
        return plugins_dir
    if mods_dir.exists():
        return mods_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def _resolve_version_from_dependency(
    client: ModrinthClient,
    dep: Dict[str, str],
    loaders: List[str],
    game_versions: List[str],
) -> Optional[Tuple[str, Dict[str, object]]]:
    version_id = dep.get("version_id")
    if version_id:
        version = client.get_version(version_id)
        project_id = version.get("project_id")
        if isinstance(project_id, str):
            return project_id, version
        return None

    dep_project_id = dep.get("project_id")
    if not dep_project_id:
        return None

    versions = client.get_project_versions(
        dep_project_id,
        loaders=loaders if loaders else None,
        game_versions=game_versions if game_versions else None,
    )
    if not versions:
        return None
    return dep_project_id, versions[0]


def _download_with_required_dependencies(
    client: ModrinthClient,
    *,
    root_project_id: str,
    root_version: Dict[str, object],
    out_dir: Path,
    loaders: List[str],
    game_versions: List[str],
) -> List[Path]:
    downloaded: List[Path] = []
    visited_projects: Set[str] = set()
    queue: List[Tuple[str, Dict[str, object]]] = [(root_project_id, root_version)]

    while queue:
        project_id, version = queue.pop(0)
        if project_id in visited_projects:
            continue
        visited_projects.add(project_id)

        selection = client.pick_download_file(version)
        info(f"Downloading {project_id}: {selection.filename}...")
        downloaded.append(client.download_version_file(version, out_dir))

        dependencies = version.get("dependencies")
        if not isinstance(dependencies, list):
            continue

        for dep in dependencies:
            if not isinstance(dep, dict):
                continue
            if dep.get("dependency_type") != "required":
                continue

            try:
                resolved = _resolve_version_from_dependency(client, dep, loaders, game_versions)
            except ModrinthError as e:
                warn(f"Could not resolve required dependency for {project_id}: {e}")
                continue

            if not resolved:
                warn(f"Could not resolve required dependency for {project_id}: {dep}")
                continue

            dep_project_id, dep_version = resolved
            if dep_project_id in visited_projects:
                continue
            queue.append((dep_project_id, dep_version))

    return downloaded



def _safe_read_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _load_server_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    if not path.exists():
        return props
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    except Exception:
        return {}
    return props


def _enrich_servers_for_ui(servers: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    base_servers_dir = servers_dir()

    for s in servers:
        item = dict(s)
        folder = str(item.get("folder") or "")
        server_id = str(item.get("server_id") or "")

        if not folder:
            platform = str(item.get("platform") or "")
            version = str(item.get("version") or "")
            name = str(item.get("name") or "")
            if platform and version and name:
                inferred = f"{platform}-{version}-{name}"
                if (base_servers_dir / inferred).exists():
                    folder = inferred
                    item["folder"] = inferred

        server_dir = base_servers_dir / folder if folder else None
        if server_dir is not None and server_dir.exists():
            item["server_dir"] = str(server_dir)

            icon_candidates = [
                server_dir / "server-icon.png",
                server_dir / "icon.png",
                server_dir / "pack.png",
            ]
            for icon in icon_candidates:
                if icon.exists() and icon.is_file():
                    item["icon_path"] = str(icon)
                    break

            props = _load_server_properties(server_dir / "server.properties")
            raw_max_players = props.get("max-players")
            try:
                if raw_max_players is not None:
                    max_players = int(raw_max_players)
                    item["max_players"] = max_players
                    item["maxPlayers"] = max_players
            except Exception:
                pass

        if server_id:
            rt_path = runtime_state_path(server_id)
            runtime = _safe_read_json(rt_path)
            if runtime:
                item["runtime"] = runtime

            state = str((item.get("runtime") or {}).get("state") or "").lower()
            if state in {"running", "starting"}:
                item["running"] = True
            elif state in {"stopped", "stopping", "error", "crashed"}:
                item["running"] = False

            pid = (item.get("runtime") or {}).get("server_pid")
            if isinstance(pid, int):
                item["pid"] = pid

        enriched.append(item)

    return enriched


def _rename_server(server_id: str, new_name: str) -> dict:
    cleaned = new_name.strip()
    if not cleaned:
        raise ValueError("Server name cannot be empty")

    found: dict | None = None

    def _mut(servers: list[dict]) -> list[dict]:
        nonlocal found
        for s in servers:
            if str(s.get("server_id")) == str(server_id):
                s["name"] = cleaned
                found = dict(s)
                break
        return servers

    STATE.mutate(_mut)
    if not found:
        raise ValueError(f"Server {server_id} not found")
    return found


def _find_server_by_id(server_id: str) -> dict:
    sid = str(server_id)
    for server in STATE.read():
        if str(server.get("server_id") or "") == sid:
            return dict(server)
    raise ValueError(f"Server {server_id} not found")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _spawn_detached(args: list[str]) -> int:
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(args, **kwargs)
    return int(proc.pid)

def main(argv: List[str]) -> int:
    # Global flags
    if "--json" in argv:
        argv = [a for a in argv if a != "--json"]
        set_json_mode(True)
        install_output_capture()

    data_dir: Optional[str] = None
    portable = False
    cleaned: list[str] = [argv[0]]
    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--data-dir":
            if i + 1 >= len(argv):
                error("Usage: --data-dir <path>")
                return 1
            data_dir = argv[i + 1]
            i += 2
            continue
        if token.startswith("--data-dir="):
            data_dir = token.split("=", 1)[1]
            i += 1
            continue
        if token == "--portable":
            portable = True
            i += 1
            continue

        cleaned.append(token)
        i += 1
    argv = cleaned

    data_root = configure_data_root(data_dir=data_dir, portable=portable)
    STATE.set_path(servers_state_path())
    os.chdir(data_root)
            
    # Keep servers.json in sync with what's actually on disk
    try:
        reconcile_servers_with_disk()
    except Exception as e:
        warn(f"[servers] warning: could not reconcile servers.json: {e}")

    if len(argv) < 2:
        error("Usage: cli.py <command> [<args>...]")
        return 1

    cmd = argv[1]

    # Sync for commands that touch server state
    if cmd in {"install_server", "run_server", "delete_server"}:
        _maybe_sync()

    if cmd == "get_versions":
        if len(argv) < 3:
            error("Usage: cli.py get_versions <software>")
            return 1
        result("get_versions", list_versions(argv[2]))
        return 0

    if cmd == "get_platforms":
        result("get_platforms", list_platforms())
        return 0

    if cmd == "install_server":
        if len(argv) < 8:
            _usage_install()
            return 1

        edition, platform, version, name = argv[2], argv[3], argv[4], argv[5]
        try:
            ram = _parse_int_arg("RAM", argv[6])
        except ValueError as e:
            error(str(e))
            return 1
        eula = _parse_bool(argv[7])

        sticky_address = True
        if len(argv) >= 9:
            sticky_address = _parse_bool(argv[8])

        # Structured event (only emits in --json mode)
        event(
            "install_starting",
            edition=edition,
            platform=platform,
            version=version,
            name=name,
            ram=ram,
            eula=eula,
            sticky_address=sticky_address,
        )

        install_server(edition, platform, version, name, ram, eula, sticky_address=sticky_address)

        event(
            "install_finished",
            edition=edition,
            platform=platform,
            version=version,
            name=name,
        )

        # After install, sync again so the edge reserves ports immediately for sticky servers
        _maybe_sync()
        info(f"Installed: {platform}-{version}-{name}")
        return 0

    if cmd == "run_server":
        if len(argv) < 6:
            error("Usage: cli.py run_server <edition> <platform> <version> <name>")
            return 1

        edition, platform, version, name = argv[2], argv[3], argv[4], argv[5]
        event("run_starting", edition=edition, platform=platform, version=version, name=name)
        run_server(edition, platform, version, name)
        event("run_finished", edition=edition, platform=platform, version=version, name=name)
        return 0

    if cmd == "start_server":
        if len(argv) < 3:
            error("Usage: cli.py start_server <server_id>")
            return 1

        server_id = argv[2]
        try:
            server = _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        runtime = _safe_read_json(runtime_state_path(str(server_id)))
        server_pid = int(runtime.get("server_pid") or 0)
        if server_pid and _process_exists(server_pid):
            result("start_server", {"server_id": server_id, "status": "already_running", "server_pid": server_pid})
            return 0

        edition = str(server.get("edition") or "java")
        platform = str(server.get("platform") or "")
        version = str(server.get("version") or "")
        name = str(server.get("name") or "")
        if not platform or not version or not name:
            error(f"Server {server_id} is missing platform/version/name")
            return 1

        if Path(sys.argv[0]).suffix.lower() == ".py":
            child_args = [sys.executable, str(Path(__file__).resolve()), "run_server", edition, platform, version, name]
        else:
            child_args = [sys.executable, "run_server", edition, platform, version, name]

        manager_pid = _spawn_detached(child_args)
        result("start_server", {
            "server_id": server_id,
            "status": "starting",
            "manager_pid": manager_pid,
        })
        return 0

    if cmd == "stop_server":
        if len(argv) < 3:
            error("Usage: cli.py stop_server <server_id>")
            return 1

        server_id = argv[2]
        timeout_s = 15.0
        try:
            stopped = stop_server(server_id=server_id, timeout_s=timeout_s)
        except Exception as e:
            error(str(e))
            return 1

        # Structural resilience: detached launcher flows can race with status updates.
        # If backend stop returned false, verify directly from runtime/port before failing.
        if not stopped:
            rt = _safe_read_json(runtime_state_path(str(server_id)))
            state = str(rt.get("state") or "").lower()
            java_port = int(rt.get("java_port") or 0)
            detached = bool(rt.get("detached_process"))
            server_pid = int(rt.get("server_pid") or 0)

            definitely_stopped = False
            if server_pid > 0:
                definitely_stopped = not _process_exists(server_pid)
            elif detached and java_port > 0:
                try:
                    import socket

                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.3)
                    rc = sock.connect_ex(("127.0.0.1", java_port))
                    sock.close()
                    definitely_stopped = rc != 0
                except Exception:
                    definitely_stopped = state in {"stopped", "stopping", "offline", "down"}
            else:
                definitely_stopped = state in {"stopped", "stopping", "offline", "down"}

            if definitely_stopped:
                stopped = True

        result("stop_server", {"server_id": server_id, "stopped": bool(stopped)})
        return 0

    if cmd == "delete_server":
        if len(argv) < 5:
            error("Usage: cli.py delete_server <platform> <version> <name>")
            return 1

        platform, version, name = argv[2], argv[3], argv[4]
        folder = f"{platform}-{version}-{name}"
        event("delete_starting", platform=platform, version=version, name=name)
        delete_server(folder)
        event("delete_finished", platform=platform, version=version, name=name)

        # After delete, sync so the edge can immediately deallocate orphan sticky ports
        _maybe_sync()

        info(f"Deleted: {folder}")
        return 0
    
    if cmd == "get_reserved_ports":
        if len(argv) < 3:
            error("Usage: cli.py get_reserved_ports <protocol>")
            return 1
        
        protocol = argv[2]
        print(get_reserved_ports(protocol))
        return 0

    # ---- Modrinth CLI ----
    # Keep compatibility with the original CLI you wrote:
    #   modrinth_search <query> [--project_type=...] [--loader=...] [--game_version=...] [--category=...]
    #   modrinth_project <project_id>
    #   modrinth_download <server_folder> <project_id> [--loader=...] [--game_version=...]
    #
    # (Newer/extra commands can be added later, but these should remain stable.)

    if cmd == "modrinth_search":
        if len(argv) < 3:
            error("Usage: cli.py modrinth_search <query> [--project_type=mod|plugin|modpack|resourcepack|shader|datapack] [--loader=loader] [--game_version=version] [--category=category]")
            return 1

        query = argv[2]
        project_type = None
        loaders = []
        game_versions = []
        categories = []
        for arg in argv[3:]:
            if arg.startswith("--project_type="):
                project_type = arg.split("=", 1)[1]
            elif arg.startswith("--loader="):
                loaders.append(arg.split("=", 1)[1])
            elif arg.startswith("--game_version="):
                game_versions.append(arg.split("=", 1)[1])
            elif arg.startswith("--category="):
                categories.append(arg.split("=", 1)[1])
            else:
                error(f"Unknown argument: {arg}")
                return 1

        client = ModrinthClient()
        try:
            results = client.search_projects(
                query,
                project_type=project_type,
                loaders=loaders if loaders else None,
                game_versions=game_versions if game_versions else None,
                categories=categories if categories else None,
            )
        except ModrinthError as e:
            error(str(e))
            return 1

        print(results)
        return 0

    if cmd == "modrinth_project":
        if len(argv) < 3:
            error("Usage: cli.py modrinth_project <project_id>")
            return 1

        project_id = argv[2]
        client = ModrinthClient()
        try:
            project = client.get_project(project_id)
        except ModrinthError as e:
            error(str(e))
            return 1

        print(project)
        return 0

    if cmd == "modrinth_download":
        if len(argv) < 4:
            error("Usage: cli.py modrinth_download <server_folder> <project_id> [--project_type=plugin|mod|datapack] [--loader=loader] [--game_version=version]")
            return 1

        server_folder = argv[2]
        project_id = argv[3]
        project_type: Optional[str] = None
        loaders = []
        game_versions = []
        for arg in argv[4:]:
            if arg.startswith("--project_type="):
                project_type = arg.split("=", 1)[1]
            elif arg.startswith("--loader="):
                loaders.append(arg.split("=", 1)[1])
            elif arg.startswith("--game_version="):
                game_versions.append(arg.split("=", 1)[1])
            else:
                error(f"Unknown argument: {arg}")
                return 1

        client = ModrinthClient()
        try:
            project = client.get_project(project_id)
        except ModrinthError as e:
            error(str(e))
            return 1

        detected_project_type = project.get("project_type")
        if not project_type and isinstance(detected_project_type, str):
            project_type = detected_project_type

        # Resolve latest matching version
        try:
            versions = client.get_project_versions(
                project_id,
                loaders=loaders if loaders else None,
                game_versions=game_versions if game_versions else None,
            )
        except ModrinthError as e:
            error(str(e))
            return 1

        if not versions:
            error("No matching versions found for the specified criteria.")
            return 1

        latest_version = versions[0]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        out_dir = _resolve_modrinth_download_dir(server_path, project_type or "")

        try:
            downloaded = _download_with_required_dependencies(
                client,
                root_project_id=project_id,
                root_version=latest_version,
                out_dir=out_dir,
                loaders=loaders,
                game_versions=game_versions,
            )
        except (ModrinthError, Exception) as e:
            error(str(e))
            return 1

        for out_file in downloaded:
            info(f"Downloaded {out_file} successfully.")
        return 0
    
    if cmd == "rename_server":
        if len(argv) < 4:
            error("Usage: cli.py rename_server <server_id> <new_name>")
            return 1
        server_id = argv[2]
        new_name = " ".join(argv[3:])
        try:
            updated = _rename_server(server_id, new_name)
        except Exception as e:
            error(str(e))
            return 1
        result("rename_server", updated)
        return 0

    if cmd == "list_servers":
        servers = read_servers_file()
        result("list_servers", {"servers": _enrich_servers_for_ui(servers)})
        return 0

    if cmd == "help":
        info(
            "Available commands: get_versions, install_server, get_platforms, run_server, start_server, stop_server, delete_server, get_reserved_ports, "
            "modrinth_search, modrinth_project, modrinth_download, pty_start, pty_write, pty_poll, pty_resize, pty_status, pty_stop"
        )
        info("Add --json to output machine-readable JSON events")
        return 0

    error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
