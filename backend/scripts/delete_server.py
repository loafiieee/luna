def delete_server(folder: str):
    import shutil
    from pathlib import Path
    from backend.utils.state import STATE

    server_folder = Path("servers") / folder

    if not server_folder.exists() or not server_folder.is_dir():
        raise ValueError(f"Server folder {server_folder} does not exist.")

    # Remove the server folder
    shutil.rmtree(server_folder)

    # Remove from servers.json (locked + atomic)
    def _mutate(servers):
        return [s for s in servers if s.get("folder") != folder]

    STATE.mutate(_mutate)
