from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from backend.utils.download_file import download_file

MODRINTH_API = "https://api.modrinth.com/v2"


class ModrinthError(RuntimeError):
    pass


def _http_get_json(url: str, user_agent: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        raise ModrinthError(f"HTTP {e.code} for {url}: {body[:300]}") from e
    except Exception as e:
        raise ModrinthError(f"Request failed for {url}: {e}") from e


def _qs(params: Dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if v is not None}
    return urllib.parse.urlencode(clean, doseq=True)


def _facets(
    *,
    project_type: Optional[str] = None,   # mod/plugin/modpack/resourcepack/shader
    loaders: Optional[Sequence[str]] = None,
    game_versions: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
) -> Optional[str]:
    # Modrinth expects JSON "array of arrays" for facets
    groups: List[List[str]] = []
    if project_type:
        groups.append([f"project_type:{project_type}"])
    if loaders:
        groups.append([f"categories:{l}" for l in loaders])
    if game_versions:
        groups.append([f"versions:{v}" for v in game_versions])
    if categories:
        groups.append([f"categories:{c}" for c in categories])

    if not groups:
        return None
    return json.dumps(groups, separators=(",", ":"))


@dataclass(frozen=True)
class DownloadSelection:
    url: str
    filename: str
    primary: bool
    size: Optional[int] = None


class ModrinthClient:
    def __init__(self, *, user_agent: str = "mc-host/0.1.0 (modrinth client)"):
        self.user_agent = user_agent

    def search_projects(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        index: str = "relevance",
        project_type: Optional[str] = None,
        loaders: Optional[Sequence[str]] = None,
        game_versions: Optional[Sequence[str]] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        facets = _facets(
            project_type=project_type,
            loaders=loaders,
            game_versions=game_versions,
            categories=categories,
        )
        url = f"{MODRINTH_API}/search?{_qs({'query': query, 'limit': limit, 'offset': offset, 'index': index, 'facets': facets})}"
        return _http_get_json(url, self.user_agent)

    def get_project(self, slug_or_id: str) -> Dict[str, Any]:
        url = f"{MODRINTH_API}/project/{urllib.parse.quote(slug_or_id)}"
        return _http_get_json(url, self.user_agent)

    def get_project_versions(
        self,
        slug_or_id: str,
        *,
        loaders: Optional[Sequence[str]] = None,
        game_versions: Optional[Sequence[str]] = None,
        featured: Optional[bool] = None,
        include_changelog: bool = False,
    ) -> List[Dict[str, Any]]:
        params = {
            "loaders": json.dumps(list(loaders)) if loaders else None,
            "game_versions": json.dumps(list(game_versions)) if game_versions else None,
            "featured": "true" if featured is True else ("false" if featured is False else None),
            "include_changelog": "true" if include_changelog else "false",
        }
        url = f"{MODRINTH_API}/project/{urllib.parse.quote(slug_or_id)}/version?{_qs(params)}"
        return _http_get_json(url, self.user_agent)

    def get_version(self, version_id: str) -> Dict[str, Any]:
        url = f"{MODRINTH_API}/version/{urllib.parse.quote(version_id)}"
        return _http_get_json(url, self.user_agent)

    @staticmethod
    def pick_download_file(version_obj: Dict[str, Any]) -> DownloadSelection:
        files = version_obj.get("files") or []
        if not files:
            raise ModrinthError("Version has no downloadable files")

        primary = next((f for f in files if f.get("primary")), None)
        chosen = primary or files[0]

        return DownloadSelection(
            url=chosen["url"],
            filename=chosen["filename"],
            primary=bool(chosen.get("primary")),
            size=chosen.get("size"),
        )

    def download_version_file(
        self,
        version_obj: Dict[str, Any],
        out_dir: Union[str, Path],
        *,
        filename: Optional[str] = None,
    ) -> Path:
        sel = self.pick_download_file(version_obj)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (filename or sel.filename)
        return download_file(sel.url, out_path)
