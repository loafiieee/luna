import sys
from sys import argv

from backend.utils.get_versions import list_versions
from backend.utils.get_platforms import list_platforms
from backend.scripts.server_installer import install_server
from backend.scripts.run_server import run_server, sync_desired_sticky_servers
from backend.scripts.delete_server import delete_server


def _maybe_sync():
    # Best-effort: keep edge reservations in sync (doesn't block offline/local usage)
    try:
        sync_desired_sticky_servers()
    except Exception as e:
        print(f"[tunnel] warning: could not sync reservations: {e}")


if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: cli.py <command> [<args>...]")
        sys.exit(1)

    cmd = argv[1]

    # Sync for commands that touch server state
    if cmd in {"install_server", "run_server", "delete_server"}:
        _maybe_sync()

    if cmd == "get_versions":
        if len(argv) < 3:
            print("Usage: cli.py get_versions <software>")
            sys.exit(1)
        print(list_versions(argv[2]))

    elif cmd == "install_server":
        if len(argv) < 8:
            print("Usage: cli.py install_server <edition> <platform> <version> <name> <RAM> <EULA> [sticky_address]")
            print("  sticky_address: true/false (default true)")
            sys.exit(1)

        edition, platform, version, name = argv[2], argv[3], argv[4], argv[5]
        ram = int(argv[6])
        eula = argv[7].lower() in {"true", "1", "yes", "y"}

        sticky_address = True
        if len(argv) >= 9:
            sticky_address = argv[8].lower() in {"true", "1", "yes", "y"}

        install_server(edition, platform, version, name, ram, eula, sticky_address=sticky_address)

        # After install, sync again so the edge reserves ports immediately for sticky servers
        _maybe_sync()

    elif cmd == "get_platforms":
        print(list_platforms())

    elif cmd == "run_server":
        if len(argv) < 6:
            print("Usage: cli.py run_server <edition> <platform> <version> <name>")
            sys.exit(1)
        run_server(argv[2], argv[3], argv[4], argv[5])

    elif cmd == "delete_server":
        if len(argv) < 5:
            print("Usage: cli.py delete_server <platform> <version> <name>")
            sys.exit(1)
        delete_server(f"{argv[2]}-{argv[3]}-{argv[4]}")

        # After delete, sync so the edge can immediately deallocate orphan sticky ports
        _maybe_sync()

    elif cmd == "help":
        print("Available commands: get_versions, install_server, get_platforms, run_server, delete_server")

    else:
        print("Unknown command")
