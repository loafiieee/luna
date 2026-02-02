def delete_server(folder: str):
    import shutil
    import os
    from pathlib import Path
    import json

    server_folder = Path("servers") / folder

    if not server_folder.exists() or not server_folder.is_dir():
        raise ValueError(f"Server folder {server_folder} does not exist.")

    # Remove the server folder
    shutil.rmtree(server_folder)

    # Remove from servers.json
    servers_file = Path("servers") / "servers.json"
    if servers_file.exists():
        with open(servers_file, "r") as f:
            servers_data = json.load(f)
        servers_data = [s for s in servers_data if s.get("folder") != folder]
        with open(servers_file, "w") as f:
            json.dump(servers_data, f, indent=4)