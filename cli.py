from backend.scripts import run_server
from backend.scripts.server_installer import *
from backend.scripts.run_server import *
from backend.utils.get_versions import *
from backend.utils.get_platforms import *
from backend.utils.download_file import *
from backend.scripts.delete_server import *
from sys import argv
if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: cli.py <command> [<args>...]")
        sys.exit(1)
    if argv[1] == "get_versions":
        if len(argv) < 3:
            print("Usage: cli.py get_versions <software>")
            sys.exit(1)
        print(list_versions(argv[2]))
    elif argv[1] == "install_server":
        if len(argv) < 8:
            print("Usage: cli.py install_server <edition> <platform> <version> <name> <RAM> <EULA>")
            sys.exit(1)
        install_server(argv[2], argv[3], argv[4], argv[5], int(argv[6]), argv[7].lower())
    elif argv[1] == "get_platforms":
        print(list_platforms())
    #run_server edition platform version name
    elif argv[1] == "run_server":
        if len(argv) < 6:
            print("Usage: cli.py run_server <edition> <platform> <version> <name>")
            sys.exit(1)
        run_server(argv[2], argv[3], argv[4], argv[5])
    elif argv[1] == "delete_server":
        if len(argv) < 5:
            print("Usage: cli.py delete_server <platform> <version> <name>")
            sys.exit(1)
        delete_server(f"{argv[2]}-{argv[3]}-{argv[4]}")

    elif argv[1] == "help":
        print("Available commands: get_versions, install_server, get_platforms, run_server, delete_server")
    
    else:
        print("Unknown command")


