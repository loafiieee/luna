from __future__ import annotations
import json
from pathlib import Path
import urllib.request

def http_get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def download_file(url: str, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, out.open("wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)

    return out





