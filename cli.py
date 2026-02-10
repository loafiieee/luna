from pathlib import Path
import sys
from typing import List

from backend.utils.get_versions import *
from backend.utils.get_platforms import *
from backend.utils.get_reseved_ports import *
from backend.scripts.server_installer import *
from backend.scripts.run_server import *
from backend.scripts.delete_server import *

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


def main(argv: List[str]) -> int:
    # Global flags
    if "--json" in argv:
        argv = [a for a in argv if a != "--json"]
        set_json_mode(True)

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
        ram = int(argv[6])
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
            error("Usage: cli.py modrinth_search <query> [--project_type=mod|plugin|modpack|resourcepack|shader] [--loader=loader] [--game_version=version] [--category=category]")
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
            error("Usage: cli.py modrinth_download <server_folder> <project_id> [--loader=loader] [--game_version=version]")
            return 1

        server_folder = argv[2]
        project_id = argv[3]
        loaders = []
        game_versions = []
        for arg in argv[4:]:
            if arg.startswith("--loader="):
                loaders.append(arg.split("=", 1)[1])
            elif arg.startswith("--game_version="):
                game_versions.append(arg.split("=", 1)[1])
            else:
                error(f"Unknown argument: {arg}")
                return 1

        # Resolve latest matching version
        client = ModrinthClient()
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
        files = latest_version.get("files", []) or []
        if not files:
            error("No downloadable files found for the latest version.")
            return 1

        # Prefer primary file if present, else first
        chosen = next((f for f in files if f.get("primary")), None) or files[0]
        download_url = chosen.get("url")
        filename = chosen.get("filename")
        if not download_url or not filename:
            error("No download URL/filename found for the selected file.")
            return 1

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        # Original behavior installed into plugins/. If plugins/ doesn't exist, fall back to mods/.
        plugins_dir = server_path / "plugins"
        mods_dir = server_path / "mods"
        if plugins_dir.exists():
            out_dir = plugins_dir
        elif mods_dir.exists():
            out_dir = mods_dir
        else:
            # Default to plugins to preserve the original intent.
            out_dir = plugins_dir
            out_dir.mkdir(parents=True, exist_ok=True)

        info(f"Downloading from {download_url}...")
        try:
            out_file = download_file(download_url, out_dir / filename)
        except Exception as e:
            error(str(e))
            return 1

        if out_file:
            info(f"Downloaded {out_file} successfully.")
        return 0
    if cmd == "help":
        info(
            "Available commands: get_versions, install_server, get_platforms, run_server, delete_server, get_reserved_ports, "
            "modrinth_search, modrinth_project, modrinth_download"
        )
        info("Add --json to output machine-readable JSON events")
        return 0

    error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
