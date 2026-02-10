from pathlib import Path
import sys
from typing import Dict, List, Optional, Set, Tuple

from backend.utils.get_versions import *
from backend.utils.get_platforms import *
from backend.utils.get_reseved_ports import *
from backend.scripts.server_installer import *
from backend.scripts.run_server import *
from backend.scripts.delete_server import *
from backend.utils.process_manager import MANAGER

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


def main(argv: List[str]) -> int:
    # Global flags
    if "--json" in argv:
        argv = [a for a in argv if a != "--json"]
        set_json_mode(True)
        install_output_capture()
            
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
        print(list_versions(argv[2]))
        return 0

    if cmd == "get_platforms":
        print(list_platforms())
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
    
    if cmd == "list_servers":
        servers = read_servers_file()
        info(servers)
        return 0

    if cmd == "help":
        info(
            "Available commands: get_versions, install_server, get_platforms, run_server, delete_server, get_reserved_ports, "
            "modrinth_search, modrinth_project, modrinth_download, pty_start, pty_write, pty_poll, pty_resize, pty_status, pty_stop"
        )
        info("Add --json to output machine-readable JSON events")
        return 0

    if cmd == "pty_start":
        if len(argv) < 3:
            error("Usage: cli.py pty_start <program> [args...]")
            return 1
        program = argv[2]
        args = argv[3:]
        session_id = MANAGER.start([program, *args], cwd=str(Path.cwd()))
        event("pty_started", session_id=session_id)
        info(session_id)
        return 0

    if cmd == "pty_write":
        if len(argv) < 4:
            error("Usage: cli.py pty_write <session_id> <data>")
            return 1
        session_id = argv[2]
        data = argv[3]
        MANAGER.write(session_id, data)
        event("pty_written", session_id=session_id, size=len(data))
        return 0

    if cmd == "pty_poll":
        if len(argv) < 3:
            error("Usage: cli.py pty_poll <session_id>")
            return 1
        session_id = argv[2]
        lines = MANAGER.poll_output(session_id)
        event("pty_output", session_id=session_id, lines=lines)
        print(lines)
        return 0

    if cmd == "pty_resize":
        if len(argv) < 5:
            error("Usage: cli.py pty_resize <session_id> <cols> <rows>")
            return 1
        session_id = argv[2]
        cols = _parse_int_arg("cols", argv[3])
        rows = _parse_int_arg("rows", argv[4])
        MANAGER.resize(session_id, cols, rows)
        event("pty_resized", session_id=session_id, cols=cols, rows=rows)
        return 0

    if cmd == "pty_status":
        if len(argv) < 3:
            error("Usage: cli.py pty_status <session_id>")
            return 1
        session_id = argv[2]
        status = MANAGER.status(session_id)
        print(status)
        return 0

    if cmd == "pty_stop":
        if len(argv) < 3:
            error("Usage: cli.py pty_stop <session_id>")
            return 1
        session_id = argv[2]
        MANAGER.stop(session_id)
        event("pty_stopped", session_id=session_id)
        return 0

    error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
