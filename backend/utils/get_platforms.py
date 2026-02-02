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

def list_platforms() -> list[str]:
    # returns list like: ["paper", "spigot", ...]
    data = http_get_json(BASE)
    assert isinstance(data, list)
    return [item["key"] for item in data]