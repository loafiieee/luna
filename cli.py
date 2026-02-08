import sys
from typing import List

from backend.utils.get_versions import list_versions
from backend.utils.get_platforms import list_platforms
from backend.utils.get_reseved_ports import get_reserved_ports
from backend.scripts.server_installer import install_server
from backend.scripts.run_server import run_server, sync_desired_sticky_servers
from backend.scripts.delete_server import delete_server

# Logging/event emitter (supports human + JSON)
from backend.utils.emit import set_json_mode, info, warn, error, event


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

    if cmd == "help":
        info("Available commands: get_versions, install_server, get_platforms, run_server, delete_server, get_reserved_ports")
        info("Add --json to output machine-readable JSON events")
        return 0

    error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
