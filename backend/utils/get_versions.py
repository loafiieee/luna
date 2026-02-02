from __future__ import annotations
import json
from pathlib import Path
import urllib.request


BASE = "https://mcutils.com/api/server-jars"
DATA_DIR = Path("data")  # later you can move this to AppData

def http_get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))
    
def list_versions(software: str) -> list[str]:
    if software in ["spigot", "craftbukkit"]:
        # BuildTools supported versions (exact matches only)
        return ["1.20.4", "1.20.2", "1.20.1", "1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19", "1.18.2", "1.18.1", "1.18", "1.17.1", "1.17", "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1", "1.15.2", "1.15.1", "1.15", "1.14.4", "1.14.3", "1.14.2", "1.14.1", "1.14", "1.13.2", "1.13.1", "1.13", "1.12.2", "1.12.1", "1.12", "1.11.2", "1.11.1", "1.11", "1.10.2", "1.10", "1.9.4", "1.9.2", "1.9", "1.8.8", "1.8.7", "1.8.6", "1.8.5", "1.8.4", "1.8.3", "1.8"]
    elif software == "quilt":
        # Quilt supports similar Minecraft versions to Fabric
        # Use Fabric's versions as proxy
        data = http_get_json(f"{BASE}/fabric")
        versions: list[str] = []
        for item in data:
            if isinstance(item, dict) and "version" in item:
                versions.append(str(item["version"]))
        return versions
    
    data = http_get_json(f"{BASE}/{software}")
    assert isinstance(data, list)
    versions: list[str] = []
    for item in data:
        if isinstance(item, dict) and "version" in item:
            versions.append(str(item["version"]))
    return versions