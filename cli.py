from pathlib import Path
import json
import base64
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from backend.utils.get_versions import *
from backend.utils.get_platforms import *
from backend.utils.get_reseved_ports import *
from backend.scripts.server_installer import *
from backend.scripts.run_server import *
from backend.scripts.delete_server import *
from backend.utils.paths import configure_data_root, get_data_root, servers_dir, runtime_state_path, servers_state_path
from backend.utils.state import STATE

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


def _parse_int_arg(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Invalid integer for {name}: {raw}")


def _resolve_modrinth_download_dir(server_path: Path, project_type: str) -> Path:
    plugins_dir = server_path / "plugins"
    mods_dir = server_path / "mods"
    datapacks_dir = server_path / "world" / "datapacks"

    if project_type == "datapack":
        datapacks_dir.mkdir(parents=True, exist_ok=True)
        return datapacks_dir

    if project_type == "plugin":
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    if project_type == "mod":
        mods_dir.mkdir(parents=True, exist_ok=True)
        return mods_dir

    # Fallback behavior for other project types.
    if plugins_dir.exists():
        return plugins_dir
    if mods_dir.exists():
        return mods_dir
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def _modrinth_manifest_path(server_path: Path) -> Path:
    return server_path / ".luna" / "modrinth_installed.json"


def _load_modrinth_manifest(server_path: Path) -> Dict[str, object]:
    path = _modrinth_manifest_path(server_path)
    if not path.exists():
        return {"project_types": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"project_types": {}}


def _save_modrinth_manifest(server_path: Path, data: Dict[str, object]) -> None:
    path = _modrinth_manifest_path(server_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _manifest_projects(manifest: Dict[str, object], project_type: str) -> Dict[str, object]:
    pt = manifest.setdefault("project_types", {})
    if not isinstance(pt, dict):
        manifest["project_types"] = {}
        pt = manifest["project_types"]
    bucket = pt.setdefault(project_type, {})
    if not isinstance(bucket, dict):
        pt[project_type] = {}
        bucket = pt[project_type]
    projects = bucket.setdefault("projects", {})
    if not isinstance(projects, dict):
        bucket["projects"] = {}
        projects = bucket["projects"]
    return projects


def _list_installed_entries(server_path: Path, project_type: str) -> List[Dict[str, object]]:
    base = _resolve_modrinth_download_dir(server_path, project_type)
    if not base.exists():
        return []
    entries: List[Dict[str, object]] = []
    for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if project_type in {"plugin", "mod"} and child.is_file() and child.suffix.lower() != ".jar":
            continue
        if project_type == "datapack":
            if child.is_file() and child.suffix.lower() != ".zip":
                continue
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": int(st.st_size),
                "modified": float(st.st_mtime),
            })
        except Exception:
            continue
    return entries

def _project_display_name(project: Dict[str, object], project_id: str) -> str:
    title = project.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    slug = project.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return project_id


def _safe_server_relative_path(server_path: Path, rel_path: str) -> Optional[Path]:
    rel = Path(rel_path)
    if rel.is_absolute():
        return None
    target = (server_path / rel).resolve()
    base = server_path.resolve()
    if base not in target.parents and target != base:
        return None
    return target


def _get_preferred_config_path(meta: Dict[str, object], server_path: Path) -> Optional[str]:
    pref = meta.get("preferred_config_path")
    if not isinstance(pref, str) or not pref.strip():
        return None
    target = _safe_server_relative_path(server_path, pref)
    if target is None or not target.exists() or not target.is_file():
        return None
    return pref


def _config_base_dir(server_path: Path, project_type: str) -> Path:
    if project_type == "plugin":
        return server_path / "plugins"
    if project_type == "mod":
        return server_path / "config"
    if project_type == "datapack":
        return server_path / "world" / "datapacks"
    return server_path / "config"


def _browse_config_files(server_path: Path, project_type: str) -> Dict[str, object]:
    base_dir = _config_base_dir(server_path, project_type)
    exts = {".yml", ".yaml", ".json", ".toml", ".cfg", ".conf", ".properties", ".txt", ".ini", ".mcmeta"}
    files: List[Dict[str, object]] = []

    if not base_dir.exists():
        return {"base_relative": str(base_dir.relative_to(server_path)), "files": []}

    count = 0
    for path in base_dir.rglob("*"):
        if count > 2500:
            break
        count += 1
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        try:
            rel = path.resolve().relative_to(server_path.resolve())
            files.append({"relative_path": str(rel)})
        except Exception:
            continue

    files.sort(key=lambda x: str(x.get("relative_path") or ""))
    return {"base_relative": str(base_dir.relative_to(server_path)), "files": files[:500]}


def _config_candidates_for_project(server_path: Path, project_type: str, meta: Dict[str, object]) -> List[Dict[str, object]]:
    project_id = str(meta.get("project_id") or "")
    slug = str(meta.get("slug") or "")
    title = str(meta.get("title") or "")
    files = meta.get("files") if isinstance(meta.get("files"), list) else []

    tokens = {t.lower() for t in [project_id, slug, title] if isinstance(t, str) and t.strip()}
    expanded_tokens = set(tokens)
    for t in list(tokens):
        expanded_tokens.add(re.sub(r"[^a-z0-9]+", "", t))
        expanded_tokens.add(t.replace("-", "").replace("_", ""))

    exts = {".yml", ".yaml", ".json", ".toml", ".cfg", ".conf", ".properties", ".txt", ".ini"}
    roots = [server_path / "config"]
    if project_type == "plugin":
        roots.append(server_path / "plugins")
    if project_type == "mod":
        roots.append(server_path / "mods")
    if project_type == "datapack":
        roots.append(server_path / "world" / "datapacks")

    hits: Dict[str, Dict[str, object]] = {}

    def add_hit(path: Path, reason: str, score: int) -> None:
        try:
            rel = path.resolve().relative_to(server_path.resolve())
        except Exception:
            return
        key = str(rel)
        cur = hits.get(key)
        row = {
            "relative_path": key,
            "reason": reason,
            "score": score,
        }
        if cur is None or int(cur.get("score") or 0) < score:
            hits[key] = row

    for r in roots:
        if not r.exists():
            continue
        count = 0
        for path in r.rglob("*"):
            if count > 1200:
                break
            count += 1
            if not path.is_file():
                continue
            if path.suffix.lower() not in exts:
                continue
            stem = path.stem.lower()
            name = path.name.lower()
            compact = re.sub(r"[^a-z0-9]+", "", stem)
            for t in expanded_tokens:
                if not t:
                    continue
                if t in stem or t in name or t == compact:
                    add_hit(path, "name_match", 90)
                    break

    for f in files:
        if not isinstance(f, str):
            continue
        base_name = Path(f).stem.lower()
        compact = re.sub(r"[^a-z0-9]+", "", base_name)
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in exts:
                    continue
                stem = path.stem.lower()
                st_compact = re.sub(r"[^a-z0-9]+", "", stem)
                if base_name and (base_name in stem or stem in base_name or (compact and compact == st_compact)):
                    add_hit(path, "artifact_match", 100)

    rows = sorted(hits.values(), key=lambda x: (-(int(x.get("score") or 0)), str(x.get("relative_path") or "")))
    preferred = _get_preferred_config_path(meta, server_path)
    if preferred:
        rows = [r for r in rows if str(r.get("relative_path") or "") != preferred]
        rows.insert(0, {"relative_path": preferred, "reason": "preferred", "score": 1000})
    return rows[:50]

def _backups_root_dir() -> Path:
    return get_data_root() / "backups"


def _backup_server_dir(server_id: str) -> Path:
    return _backups_root_dir() / str(server_id)


def _backup_meta_path(server_id: str, backup_id: str) -> Path:
    return _backup_server_dir(server_id) / f"{backup_id}.json"


def _backup_zip_path(server_id: str, backup_id: str) -> Path:
    return _backup_server_dir(server_id) / f"{backup_id}.zip"


def _backup_schedule_path(server_id: str) -> Path:
    return _backup_server_dir(server_id) / "schedule.json"


def _backup_schedule_defaults() -> Dict[str, object]:
    return {
        "enabled": False,
        "interval_minutes": 60,
        "keep_latest": 10,
        "label_prefix": "Scheduled",
        "next_run_at": None,
        "last_run_at": None,
        "last_backup_id": None,
        "last_error": None,
    }


def _normalize_backup_schedule(data: Dict[str, object]) -> Dict[str, object]:
    schedule = _backup_schedule_defaults()
    schedule["enabled"] = bool(data.get("enabled"))
    try:
        schedule["interval_minutes"] = max(5, int(data.get("interval_minutes") or 60))
    except Exception:
        schedule["interval_minutes"] = 60
    try:
        schedule["keep_latest"] = max(1, int(data.get("keep_latest") or 10))
    except Exception:
        schedule["keep_latest"] = 10

    prefix = data.get("label_prefix")
    schedule["label_prefix"] = str(prefix).strip() if isinstance(prefix, str) and str(prefix).strip() else "Scheduled"

    for key in ("next_run_at", "last_run_at", "last_backup_id", "last_error"):
        v = data.get(key)
        schedule[key] = v if isinstance(v, str) and v.strip() else None
    return schedule


def _load_backup_schedule(server_id: str) -> Dict[str, object]:
    spath = _backup_schedule_path(server_id)
    if not spath.exists():
        return _backup_schedule_defaults()
    try:
        raw = json.loads(spath.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return _normalize_backup_schedule(raw)
    except Exception:
        pass
    return _backup_schedule_defaults()


def _save_backup_schedule(server_id: str, schedule: Dict[str, object]) -> None:
    normalized = _normalize_backup_schedule(schedule)
    bdir = _backup_server_dir(server_id)
    bdir.mkdir(parents=True, exist_ok=True)
    _backup_schedule_path(server_id).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_schedule_time(interval_minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=max(5, interval_minutes))).isoformat()


def _list_backups(server_id: str) -> List[Dict[str, object]]:
    bdir = _backup_server_dir(server_id)
    if not bdir.exists():
        return []
    rows: List[Dict[str, object]] = []
    for z in sorted(bdir.glob("*.zip"), key=lambda p: p.name, reverse=True):
        backup_id = z.stem
        meta_path = _backup_meta_path(server_id, backup_id)
        meta: Dict[str, object] = {}
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(m, dict):
                    meta = m
            except Exception:
                meta = {}
        try:
            st = z.stat()
        except Exception:
            continue
        rows.append(
            {
                "backup_id": backup_id,
                "filename": z.name,
                "label": meta.get("label") if isinstance(meta.get("label"), str) else None,
                "created_at": meta.get("created_at") if isinstance(meta.get("created_at"), str) else None,
                "size_bytes": int(st.st_size),
                "file_count": int(meta.get("file_count") or 0),
            }
        )
    return rows


def _create_backup(server_id: str, *, label: Optional[str] = None) -> Dict[str, object]:
    server = _find_server_by_id(server_id)
    folder = str(server.get("folder") or "")
    if not folder:
        raise ValueError(f"Server {server_id} is missing folder")

    server_path = servers_dir() / folder
    if not server_path.exists() or not server_path.is_dir():
        raise ValueError(f"Server folder {server_path} does not exist")

    backup_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bdir = _backup_server_dir(server_id)
    bdir.mkdir(parents=True, exist_ok=True)
    zpath = _backup_zip_path(server_id, backup_id)

    file_count = 0
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in server_path.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(server_path)
            zf.write(path, arcname=str(rel))
            file_count += 1

    meta = {
        "backup_id": backup_id,
        "server_id": server_id,
        "server_name": server.get("name"),
        "folder": folder,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "file_count": file_count,
    }
    _backup_meta_path(server_id, backup_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "server_id": server_id,
        "backup_id": backup_id,
        "label": label,
        "file_count": file_count,
        "size_bytes": zpath.stat().st_size,
    }


def _apply_backup_retention(server_id: str, *, keep_latest: int) -> List[str]:
    removed: List[str] = []
    backups = _list_backups(server_id)
    if len(backups) <= keep_latest:
        return removed
    for row in backups[keep_latest:]:
        backup_id = str(row.get("backup_id") or "")
        if not backup_id:
            continue
        zpath = _backup_zip_path(server_id, backup_id)
        mpath = _backup_meta_path(server_id, backup_id)
        try:
            if zpath.exists():
                zpath.unlink()
            if mpath.exists():
                mpath.unlink()
            removed.append(backup_id)
        except Exception:
            continue
    return removed


def _run_due_scheduled_backup(server_id: str, now: Optional[datetime] = None) -> Dict[str, object]:
    schedule = _load_backup_schedule(server_id)
    if not bool(schedule.get("enabled")):
        return {"server_id": server_id, "ran": False, "reason": "disabled", "schedule": schedule}

    now_dt = now or datetime.now(timezone.utc)
    next_raw = schedule.get("next_run_at") if isinstance(schedule.get("next_run_at"), str) else None
    next_run_at: Optional[datetime] = None
    if next_raw:
        try:
            next_run_at = datetime.fromisoformat(next_raw)
        except Exception:
            next_run_at = None
    if next_run_at and next_run_at > now_dt:
        return {"server_id": server_id, "ran": False, "reason": "not_due", "schedule": schedule}

    interval_minutes = int(schedule.get("interval_minutes") or 60)
    keep_latest = int(schedule.get("keep_latest") or 10)
    label_prefix = str(schedule.get("label_prefix") or "Scheduled").strip() or "Scheduled"
    label = f"{label_prefix} {now_dt.astimezone().strftime('%Y-%m-%d %H:%M')}"

    try:
        created = _create_backup(server_id, label=label)
        removed = _apply_backup_retention(server_id, keep_latest=keep_latest)
        schedule["last_run_at"] = now_dt.isoformat()
        schedule["last_backup_id"] = created.get("backup_id")
        schedule["last_error"] = None
        schedule["next_run_at"] = _next_schedule_time(interval_minutes)
        _save_backup_schedule(server_id, schedule)
        return {
            "server_id": server_id,
            "ran": True,
            "created": created,
            "deleted_by_retention": removed,
            "schedule": schedule,
        }
    except Exception as e:
        schedule["last_run_at"] = now_dt.isoformat()
        schedule["last_error"] = str(e)
        schedule["next_run_at"] = _next_schedule_time(interval_minutes)
        _save_backup_schedule(server_id, schedule)
        return {
            "server_id": server_id,
            "ran": False,
            "reason": "error",
            "error": str(e),
            "schedule": schedule,
        }


def _run_due_scheduled_backups_for_all() -> None:
    """Best-effort scheduler tick for all servers; non-fatal if any server fails."""
    try:
        servers = read_servers_file()
    except Exception:
        return
    now = datetime.now(timezone.utc)
    for s in servers:
        server_id = str((s or {}).get("server_id") or "")
        if not server_id:
            continue
        try:
            _run_due_scheduled_backup(server_id, now=now)
        except Exception:
            continue


def _safe_extract_zip(zip_path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            name = member.filename
            if name.startswith("/"):
                raise ValueError("Invalid backup archive path")
            target = (out_dir / name).resolve()
            base = out_dir.resolve()
            if base not in target.parents and target != base:
                raise ValueError("Backup archive contains unsafe path")
        zf.extractall(out_dir)

def _resolve_version_from_dependency(
    client: ModrinthClient,
    dep: Dict[str, str],
    loaders: List[str],
    game_versions: List[str],
) -> Optional[Tuple[str, Dict[str, object]]]:
    version_id = dep.get("version_id")
    if version_id:
        version = client.get_version(version_id)
        project_id = version.get("project_id")
        if isinstance(project_id, str):
            return project_id, version
        return None

    dep_project_id = dep.get("project_id")
    if not dep_project_id:
        return None

    versions = client.get_project_versions(
        dep_project_id,
        loaders=loaders if loaders else None,
        game_versions=game_versions if game_versions else None,
    )
    if not versions:
        return None
    return dep_project_id, versions[0]


def _download_with_required_dependencies(
    client: ModrinthClient,
    *,
    root_project_id: str,
    root_version: Dict[str, object],
    out_dir: Path,
    loaders: List[str],
    game_versions: List[str],
) -> Tuple[List[Path], Dict[str, List[str]]]:
    downloaded: List[Path] = []
    downloaded_project_files: Dict[str, List[str]] = {}
    visited_projects: Set[str] = set()
    queue: List[Tuple[str, Dict[str, object]]] = [(root_project_id, root_version)]

    while queue:
        project_id, version = queue.pop(0)
        if project_id in visited_projects:
            continue
        visited_projects.add(project_id)

        selection = client.pick_download_file(version)
        info(f"Downloading {project_id}: {selection.filename}...")
        out_path = client.download_version_file(version, out_dir)
        downloaded.append(out_path)
        downloaded_project_files.setdefault(project_id, []).append(out_path.name)

        dependencies = version.get("dependencies")
        if not isinstance(dependencies, list):
            continue

        for dep in dependencies:
            if not isinstance(dep, dict):
                continue
            if dep.get("dependency_type") != "required":
                continue

            try:
                resolved = _resolve_version_from_dependency(client, dep, loaders, game_versions)
            except ModrinthError as e:
                warn(f"Could not resolve required dependency for {project_id}: {e}")
                continue

            if not resolved:
                warn(f"Could not resolve required dependency for {project_id}: {dep}")
                continue

            dep_project_id, dep_version = resolved
            if dep_project_id in visited_projects:
                continue
            queue.append((dep_project_id, dep_version))

    return downloaded, downloaded_project_files



def _safe_read_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _load_server_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    if not path.exists():
        return props
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    except Exception:
        return {}
    return props


def _enrich_servers_for_ui(servers: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    base_servers_dir = servers_dir()

    for s in servers:
        item = dict(s)
        folder = str(item.get("folder") or "")
        server_id = str(item.get("server_id") or "")

        if not folder:
            platform = str(item.get("platform") or "")
            version = str(item.get("version") or "")
            name = str(item.get("name") or "")
            if platform and version and name:
                inferred = f"{platform}-{version}-{name}"
                if (base_servers_dir / inferred).exists():
                    folder = inferred
                    item["folder"] = inferred

        server_dir = base_servers_dir / folder if folder else None
        if server_dir is not None and server_dir.exists():
            item["server_dir"] = str(server_dir)

            icon_candidates = [
                server_dir / "server-icon.png",
                server_dir / "icon.png",
                server_dir / "pack.png",
            ]
            for icon in icon_candidates:
                if icon.exists() and icon.is_file():
                    item["icon_path"] = str(icon)
                    break

            props = _load_server_properties(server_dir / "server.properties")
            raw_max_players = props.get("max-players")
            try:
                if raw_max_players is not None:
                    max_players = int(raw_max_players)
                    item["max_players"] = max_players
                    item["maxPlayers"] = max_players
            except Exception:
                pass

        if server_id:
            rt_path = runtime_state_path(server_id)
            runtime = _safe_read_json(rt_path)
            if runtime:
                item["runtime"] = runtime

            state = str((item.get("runtime") or {}).get("state") or "").lower()
            if state in {"running", "starting"}:
                item["running"] = True
            elif state in {"stopped", "stopping", "error", "crashed"}:
                item["running"] = False

            pid = (item.get("runtime") or {}).get("server_pid")
            if isinstance(pid, int):
                item["pid"] = pid

        enriched.append(item)

    return enriched


def _rename_server(server_id: str, new_name: str) -> dict:
    cleaned = new_name.strip()
    if not cleaned:
        raise ValueError("Server name cannot be empty")

    found: dict | None = None

    def _mut(servers: list[dict]) -> list[dict]:
        nonlocal found
        for s in servers:
            if str(s.get("server_id")) == str(server_id):
                s["name"] = cleaned
                found = dict(s)
                break
        return servers

    STATE.mutate(_mut)
    if not found:
        raise ValueError(f"Server {server_id} not found")
    return found




def _update_tunnel_config(server_id: str, *, tunneling: Optional[bool] = None, sticky_address: Optional[bool] = None) -> dict:
    found: dict | None = None

    def _mut(servers: list[dict]) -> list[dict]:
        nonlocal found
        for srv in servers:
            if str(srv.get("server_id") or "") != str(server_id):
                continue
            if tunneling is not None:
                srv["tunneling"] = bool(tunneling)
            if sticky_address is not None:
                srv["sticky_address"] = bool(sticky_address)
            found = dict(srv)
            break
        return servers

    STATE.mutate(_mut)
    if not found:
        raise ValueError(f"Server {server_id} not found")
    return found




def _open_in_file_manager(path: Path) -> None:
    target = str(path.resolve())
    if sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
        return
    subprocess.Popen(["xdg-open", target])


def _find_server_by_id(server_id: str) -> dict:
    sid = str(server_id)
    for server in STATE.read():
        if str(server.get("server_id") or "") == sid:
            return dict(server)
    raise ValueError(f"Server {server_id} not found")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _tcp_port_open(port: int) -> bool:
    if port <= 0:
        return False
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        rc = sock.connect_ex(("127.0.0.1", int(port)))
        sock.close()
        return rc == 0
    except Exception:
        return False




def _seed_runtime_starting(server_id: str, *, server: dict, manager_pid: int) -> None:
    """Write an immediate runtime 'starting' state to avoid UI start/stop flicker."""
    try:
        rt_path = runtime_state_path(str(server_id))
        rt_path.parent.mkdir(parents=True, exist_ok=True)

        current = _safe_read_json(rt_path)
        merged: dict = dict(current) if isinstance(current, dict) else {}

        merged.update({
            "server_id": str(server_id),
            "platform": str(server.get("platform") or ""),
            "version": str(server.get("version") or ""),
            "name": str(server.get("name") or ""),
            "folder": str(server.get("folder") or ""),
            "edition": str(server.get("edition") or "java"),
            "state": "starting",
            "manager_pid": int(manager_pid),
            "server_pid": None,
            "detached_process": False,
            "start_requested_at": time.time(),
        })

        rt_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort only: server manager process will write authoritative runtime state shortly.
        pass
def _spawn_detached(args: list[str]) -> int:
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(args, **kwargs)
    return int(proc.pid)

def main(argv: List[str]) -> int:
    # Global flags
    if "--json" in argv:
        argv = [a for a in argv if a != "--json"]
        set_json_mode(True)
        install_output_capture()

    data_dir: Optional[str] = None
    portable = False
    cleaned: list[str] = [argv[0]]
    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--data-dir":
            if i + 1 >= len(argv):
                error("Usage: --data-dir <path>")
                return 1
            data_dir = argv[i + 1]
            i += 2
            continue
        if token.startswith("--data-dir="):
            data_dir = token.split("=", 1)[1]
            i += 1
            continue
        if token == "--portable":
            portable = True
            i += 1
            continue

        cleaned.append(token)
        i += 1
    argv = cleaned

    data_root = configure_data_root(data_dir=data_dir, portable=portable)
    STATE.set_path(servers_state_path())
    os.chdir(data_root)
            
    # Keep servers.json in sync with what's actually on disk
    try:
        reconcile_servers_with_disk()
    except Exception as e:
        warn(f"[servers] warning: could not reconcile servers.json: {e}")

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
        result("get_versions", list_versions(argv[2]))
        return 0

    if cmd == "get_platforms":
        result("get_platforms", list_platforms())
        return 0

    if cmd == "install_server":
        if len(argv) < 8:
            _usage_install()
            return 1

        edition, platform, version, name = argv[2], argv[3], argv[4], argv[5]
        try:
            ram = _parse_int_arg("RAM", argv[6])
        except ValueError as e:
            error(str(e))
            return 1
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

    if cmd == "start_server":
        if len(argv) < 3:
            error("Usage: cli.py start_server <server_id>")
            return 1

        server_id = argv[2]
        try:
            server = _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        runtime = _safe_read_json(runtime_state_path(str(server_id)))
        runtime_state = str(runtime.get("state") or "").lower()
        server_pid = int(runtime.get("server_pid") or 0)

        # Detached launchers may clear server_pid while the JVM keeps running.
        detached = bool(runtime.get("detached_process"))
        java_port = int(runtime.get("java_port") or 0)
        manager_pid = int(runtime.get("manager_pid") or 0)

        if server_pid and _process_exists(server_pid):
            result("start_server", {"server_id": server_id, "status": "already_running", "server_pid": server_pid})
            return 0
        if detached and java_port > 0 and _tcp_port_open(java_port):
            result(
                "start_server",
                {"server_id": server_id, "status": "already_running", "reason": "detached_process", "java_port": java_port},
            )
            return 0
        if runtime_state == "starting" and manager_pid > 0 and _process_exists(manager_pid):
            result("start_server", {"server_id": server_id, "status": "already_starting", "manager_pid": manager_pid})
            return 0

        edition = str(server.get("edition") or "java")
        platform = str(server.get("platform") or "")
        version = str(server.get("version") or "")
        name = str(server.get("name") or "")
        if not platform or not version or not name:
            error(f"Server {server_id} is missing platform/version/name")
            return 1

        if Path(sys.argv[0]).suffix.lower() == ".py":
            child_args = [sys.executable, str(Path(__file__).resolve()), "run_server", edition, platform, version, name]
        else:
            child_args = [sys.executable, "run_server", edition, platform, version, name]

        manager_pid = _spawn_detached(child_args)
        _seed_runtime_starting(server_id, server=server, manager_pid=manager_pid)

        result("start_server", {
            "server_id": server_id,
            "status": "starting",
            "manager_pid": manager_pid,
        })
        return 0

    if cmd == "stop_server":
        if len(argv) < 3:
            error("Usage: cli.py stop_server <server_id>")
            return 1

        server_id = argv[2]
        timeout_s = 15.0
        try:
            stopped = stop_server(server_id=server_id, timeout_s=timeout_s)
        except Exception as e:
            error(str(e))
            return 1

        # Structural resilience: detached launcher flows can race with status updates.
        # If backend stop returned false, verify directly from runtime/port before failing.
        if not stopped:
            rt = _safe_read_json(runtime_state_path(str(server_id)))
            state = str(rt.get("state") or "").lower()
            java_port = int(rt.get("java_port") or 0)
            detached = bool(rt.get("detached_process"))
            server_pid = int(rt.get("server_pid") or 0)

            definitely_stopped = False
            if server_pid > 0:
                definitely_stopped = not _process_exists(server_pid)
            elif detached and java_port > 0:
                try:
                    import socket

                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.3)
                    rc = sock.connect_ex(("127.0.0.1", java_port))
                    sock.close()
                    definitely_stopped = rc != 0
                except Exception:
                    definitely_stopped = state in {"stopped", "stopping", "offline", "down"}
            else:
                definitely_stopped = state in {"stopped", "stopping", "offline", "down"}

            if definitely_stopped:
                stopped = True

        result("stop_server", {"server_id": server_id, "stopped": bool(stopped)})
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
            error("Usage: cli.py modrinth_search <query> [--project_type=mod|plugin|modpack|resourcepack|shader|datapack] [--loader=loader] [--game_version=version] [--category=category]")
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

        result("modrinth_search", results)
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

        result("modrinth_project", project)
        return 0

    if cmd == "modrinth_download":
        if len(argv) < 4:
            error("Usage: cli.py modrinth_download <server_folder> <project_id> [--project_type=plugin|mod|datapack] [--loader=loader] [--game_version=version]")
            return 1

        server_folder = argv[2]
        project_id = argv[3]
        project_type: Optional[str] = None
        loaders = []
        game_versions = []
        for arg in argv[4:]:
            if arg.startswith("--project_type="):
                project_type = arg.split("=", 1)[1]
            elif arg.startswith("--loader="):
                loaders.append(arg.split("=", 1)[1])
            elif arg.startswith("--game_version="):
                game_versions.append(arg.split("=", 1)[1])
            else:
                error(f"Unknown argument: {arg}")
                return 1

        client = ModrinthClient()
        try:
            project = client.get_project(project_id)
        except ModrinthError as e:
            error(str(e))
            return 1

        detected_project_type = project.get("project_type")
        if not project_type and isinstance(detected_project_type, str):
            project_type = detected_project_type

        # Resolve latest matching version
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

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        out_dir = _resolve_modrinth_download_dir(server_path, project_type or "")

        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type or "plugin")
        existing = projects.get(project_id)
        if isinstance(existing, dict):
            recorded_files = existing.get("files")
            if isinstance(recorded_files, list) and all((out_dir / str(f)).exists() for f in recorded_files if isinstance(f, str)):
                result(
                    "modrinth_download",
                    {
                        "project_id": project_id,
                        "project_type": project_type,
                        "downloaded_files": [],
                        "count": 0,
                        "already_installed": True,
                    },
                )
                return 0

        try:
            downloaded, downloaded_project_files = _download_with_required_dependencies(
                client,
                root_project_id=project_id,
                root_version=latest_version,
                out_dir=out_dir,
                loaders=loaders,
                game_versions=game_versions,
            )
        except (ModrinthError, Exception) as e:
            error(str(e))
            return 1

        downloaded_paths: List[str] = []
        for out_file in downloaded:
            info(f"Downloaded {out_file} successfully.")
            downloaded_paths.append(str(out_file))

        now_ts = time.time()
        for pid, files in downloaded_project_files.items():
            project_meta: Dict[str, object] = {}
            try:
                p_obj = project if pid == project_id else client.get_project(pid)
                if isinstance(p_obj, dict):
                    project_meta = p_obj
            except Exception:
                project_meta = {}

            projects[pid] = {
                "project_id": pid,
                "files": files,
                "installed_at": now_ts,
                "title": _project_display_name(project_meta, pid),
                "slug": project_meta.get("slug") if isinstance(project_meta.get("slug"), str) else None,
                "author": project_meta.get("author") if isinstance(project_meta.get("author"), str) else None,
                "icon_url": project_meta.get("icon_url") if isinstance(project_meta.get("icon_url"), str) else None,
                "description": project_meta.get("description") if isinstance(project_meta.get("description"), str) else None,
            }
        _save_modrinth_manifest(server_path, manifest)

        result(
            "modrinth_download",
            {
                "project_id": project_id,
                "project_type": project_type,
                "downloaded_files": downloaded_paths,
                "count": len(downloaded_paths),
                "already_installed": False,
            },
        )
        return 0
    
    if cmd == "modrinth_list_installed":
        if len(argv) < 3:
            error("Usage: cli.py modrinth_list_installed <server_folder> [--project_type=plugin|mod|datapack]")
            return 1

        server_folder = argv[2]
        project_type = "plugin"
        for arg in argv[3:]:
            if arg.startswith("--project_type="):
                project_type = arg.split("=", 1)[1]
            else:
                error(f"Unknown argument: {arg}")
                return 1

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        entries = _list_installed_entries(server_path, project_type)
        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type)
        project_rows: List[Dict[str, object]] = []
        client = ModrinthClient()
        dirty_manifest = False
        for pid, meta in projects.items():
            if not isinstance(pid, str):
                continue
            md = meta if isinstance(meta, dict) else {}
            files = md.get("files") if isinstance(md.get("files"), list) else []
            installed_at = md.get("installed_at") if isinstance(md.get("installed_at"), (int, float)) else None
            title = md.get("title") if isinstance(md.get("title"), str) and str(md.get("title")).strip() else None
            slug = md.get("slug") if isinstance(md.get("slug"), str) and str(md.get("slug")).strip() else None
            author = md.get("author") if isinstance(md.get("author"), str) and str(md.get("author")).strip() else None
            icon_url = md.get("icon_url") if isinstance(md.get("icon_url"), str) and str(md.get("icon_url")).strip() else None
            description = md.get("description") if isinstance(md.get("description"), str) and str(md.get("description")).strip() else None

            if not title or not icon_url:
                try:
                    p_obj = client.get_project(pid)
                    if isinstance(p_obj, dict):
                        title = _project_display_name(p_obj, pid)
                        slug = p_obj.get("slug") if isinstance(p_obj.get("slug"), str) else slug
                        author = p_obj.get("author") if isinstance(p_obj.get("author"), str) else author
                        icon_url = p_obj.get("icon_url") if isinstance(p_obj.get("icon_url"), str) else icon_url
                        description = p_obj.get("description") if isinstance(p_obj.get("description"), str) else description
                        projects[pid] = {
                            **md,
                            "project_id": pid,
                            "title": title,
                            "slug": slug,
                            "author": author,
                            "icon_url": icon_url,
                            "description": description,
                            "files": files,
                            "installed_at": installed_at,
                        }
                        dirty_manifest = True
                except Exception:
                    pass

            project_rows.append(
                {
                    "project_id": pid,
                    "project_type": project_type,
                    "files": files,
                    "installed_at": installed_at,
                    "title": title or pid,
                    "slug": slug,
                    "author": author,
                    "icon_url": icon_url,
                    "description": description,
                    "preferred_config_path": md.get("preferred_config_path") if isinstance(md.get("preferred_config_path"), str) else None,
                }
            )

        if dirty_manifest:
            _save_modrinth_manifest(server_path, manifest)

        result(
            "modrinth_list_installed",
            {
                "project_type": project_type,
                "entries": entries,
                "installed_project_ids": list(projects.keys()),
                "projects": project_rows,
            },
        )
        return 0

    if cmd == "modrinth_browse_config_files":
        if len(argv) < 4:
            error("Usage: cli.py modrinth_browse_config_files <server_folder> <project_type>")
            return 1

        server_folder = argv[2]
        project_type = argv[3]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        payload = _browse_config_files(server_path, project_type)
        result("modrinth_browse_config_files", payload)
        return 0

    if cmd == "modrinth_config_candidates":
        if len(argv) < 5:
            error("Usage: cli.py modrinth_config_candidates <server_folder> <project_type> <project_id>")
            return 1

        server_folder = argv[2]
        project_type = argv[3]
        project_id = argv[4]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type)
        meta = projects.get(project_id)
        if not isinstance(meta, dict):
            error(f"Project {project_id} is not installed")
            return 1

        merged_meta = {"project_id": project_id, **meta}
        candidates = _config_candidates_for_project(server_path, project_type, merged_meta)
        preferred = _get_preferred_config_path(merged_meta, server_path)
        result("modrinth_config_candidates", {"project_id": project_id, "project_type": project_type, "preferred_config_path": preferred, "candidates": candidates})
        return 0

    if cmd == "modrinth_set_preferred_config":
        if len(argv) < 6:
            error("Usage: cli.py modrinth_set_preferred_config <server_folder> <project_type> <project_id> <relative_path>")
            return 1

        server_folder = argv[2]
        project_type = argv[3]
        project_id = argv[4]
        rel_path = argv[5]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        target = _safe_server_relative_path(server_path, rel_path)
        if target is None or not target.exists() or not target.is_file():
            error("Invalid config file path")
            return 1

        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type)
        meta = projects.get(project_id)
        if not isinstance(meta, dict):
            error(f"Project {project_id} is not installed")
            return 1

        projects[project_id] = {**meta, "preferred_config_path": rel_path}
        _save_modrinth_manifest(server_path, manifest)
        result("modrinth_set_preferred_config", {"project_id": project_id, "project_type": project_type, "preferred_config_path": rel_path})
        return 0

    if cmd == "read_server_text_file":
        if len(argv) < 4:
            error("Usage: cli.py read_server_text_file <server_folder> <relative_path>")
            return 1

        server_folder = argv[2]
        rel_path = argv[3]
        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        target = _safe_server_relative_path(server_path, rel_path)
        if target is None or not target.exists() or not target.is_file():
            error("Invalid file path")
            return 1

        try:
            content = target.read_text(encoding="utf-8")
        except Exception:
            content = target.read_text(encoding="utf-8", errors="replace")

        result("read_server_text_file", {"relative_path": rel_path, "content": content})
        return 0

    if cmd == "write_server_text_file":
        if len(argv) < 5:
            error("Usage: cli.py write_server_text_file <server_folder> <relative_path> <base64_content>")
            return 1

        server_folder = argv[2]
        rel_path = argv[3]
        encoded = argv[4]
        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        target = _safe_server_relative_path(server_path, rel_path)
        if target is None:
            error("Invalid file path")
            return 1
        if not target.exists() or not target.is_file():
            error("File does not exist")
            return 1

        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
            content = raw.decode("utf-8")
        except Exception:
            error("Invalid base64 content")
            return 1

        target.write_text(content, encoding="utf-8")
        result("write_server_text_file", {"relative_path": rel_path, "bytes": len(raw)})
        return 0

    if cmd == "modrinth_uninstall_project":
        if len(argv) < 5:
            error("Usage: cli.py modrinth_uninstall_project <server_folder> <project_type> <project_id>")
            return 1

        server_folder = argv[2]
        project_type = argv[3]
        project_id = argv[4]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type)
        meta = projects.get(project_id)
        if not isinstance(meta, dict):
            error(f"Project {project_id} is not installed")
            return 1

        out_dir = _resolve_modrinth_download_dir(server_path, project_type)
        removed_files: List[str] = []
        files = meta.get("files")
        if isinstance(files, list):
            for f in files:
                if not isinstance(f, str):
                    continue
                target = (out_dir / f).resolve()
                base = out_dir.resolve()
                if base not in target.parents and target != base:
                    continue
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    removed_files.append(f)

        projects.pop(project_id, None)
        _save_modrinth_manifest(server_path, manifest)

        result(
            "modrinth_uninstall_project",
            {
                "project_id": project_id,
                "project_type": project_type,
                "removed_files": removed_files,
                "count": len(removed_files),
            },
        )
        return 0

    if cmd == "modrinth_remove_installed":
        if len(argv) < 5:
            error("Usage: cli.py modrinth_remove_installed <server_folder> <project_type> <name>")
            return 1

        server_folder = argv[2]
        project_type = argv[3]
        name = argv[4]

        server_path = Path("servers") / server_folder
        if not server_path.exists():
            error(f"Server folder {server_path} does not exist.")
            return 1

        base = _resolve_modrinth_download_dir(server_path, project_type)
        target = (base / name).resolve()
        base_resolved = base.resolve()
        if base_resolved not in target.parents and target != base_resolved:
            error("Invalid content path")
            return 1
        if not target.exists():
            error(f"Content item {name} does not exist")
            return 1

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

        manifest = _load_modrinth_manifest(server_path)
        projects = _manifest_projects(manifest, project_type)
        to_delete = []
        for pid, meta in projects.items():
            if not isinstance(meta, dict):
                continue
            files = meta.get("files")
            if isinstance(files, list) and any(str(f) == name for f in files):
                to_delete.append(pid)
        for pid in to_delete:
            projects.pop(pid, None)
        _save_modrinth_manifest(server_path, manifest)

        result("modrinth_remove_installed", {"removed": name, "project_type": project_type})
        return 0

    if cmd == "backup_create":
        if len(argv) < 3:
            error("Usage: cli.py backup_create <server_id> [--label=label]")
            return 1

        server_id = argv[2]
        label: Optional[str] = None
        for arg in argv[3:]:
            if arg.startswith("--label="):
                label = arg.split("=", 1)[1].strip() or None
            else:
                error(f"Unknown argument: {arg}")
                return 1

        try:
            created = _create_backup(server_id, label=label)
        except Exception as e:
            error(str(e))
            return 1

        result("backup_create", created)
        return 0

    if cmd == "backup_schedule_get":
        if len(argv) < 3:
            error("Usage: cli.py backup_schedule_get <server_id>")
            return 1

        server_id = argv[2]
        try:
            _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        schedule = _load_backup_schedule(server_id)
        result("backup_schedule_get", {"server_id": server_id, "schedule": schedule})
        return 0

    if cmd == "backup_schedule_set":
        if len(argv) < 3:
            error("Usage: cli.py backup_schedule_set <server_id> [--enabled=true|false] [--interval-minutes=N] [--keep-latest=N] [--label-prefix=text]")
            return 1

        server_id = argv[2]
        try:
            _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        schedule = _load_backup_schedule(server_id)
        changed = False
        for arg in argv[3:]:
            if arg.startswith("--enabled="):
                schedule["enabled"] = _parse_bool(arg.split("=", 1)[1])
                changed = True
            elif arg.startswith("--interval-minutes="):
                schedule["interval_minutes"] = max(5, _parse_int_arg("interval_minutes", arg.split("=", 1)[1]))
                changed = True
            elif arg.startswith("--keep-latest="):
                schedule["keep_latest"] = max(1, _parse_int_arg("keep_latest", arg.split("=", 1)[1]))
                changed = True
            elif arg.startswith("--label-prefix="):
                schedule["label_prefix"] = arg.split("=", 1)[1].strip() or "Scheduled"
                changed = True
            else:
                error(f"Unknown argument: {arg}")
                return 1

        if not changed:
            error("No schedule settings provided")
            return 1

        interval_minutes = int(schedule.get("interval_minutes") or 60)
        if bool(schedule.get("enabled")):
            schedule["next_run_at"] = _next_schedule_time(interval_minutes)
            schedule["last_error"] = None
        else:
            schedule["next_run_at"] = None

        _save_backup_schedule(server_id, schedule)
        result("backup_schedule_set", {"server_id": server_id, "schedule": _load_backup_schedule(server_id)})
        return 0

    if cmd == "backup_schedule_run":
        if len(argv) < 3:
            error("Usage: cli.py backup_schedule_run <server_id>")
            return 1

        server_id = argv[2]
        try:
            _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        run = _run_due_scheduled_backup(server_id)
        if run.get("reason") == "error":
            error(str(run.get("error") or "Scheduled backup failed"))
            return 1
        result("backup_schedule_run", run)
        return 0

    if cmd == "backup_list":
        if len(argv) < 3:
            error("Usage: cli.py backup_list <server_id>")
            return 1

        server_id = argv[2]
        try:
            _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        rows = _list_backups(server_id)
        result("backup_list", {"server_id": server_id, "backups": rows})
        return 0

    if cmd == "backup_delete":
        if len(argv) < 4:
            error("Usage: cli.py backup_delete <server_id> <backup_id>")
            return 1

        server_id = argv[2]
        backup_id = argv[3]
        zpath = _backup_zip_path(server_id, backup_id)
        mpath = _backup_meta_path(server_id, backup_id)

        if not zpath.exists():
            error(f"Backup {backup_id} does not exist")
            return 1

        zpath.unlink()
        if mpath.exists():
            mpath.unlink()

        result("backup_delete", {"server_id": server_id, "backup_id": backup_id, "deleted": True})
        return 0

    if cmd == "backup_restore":
        if len(argv) < 4:
            error("Usage: cli.py backup_restore <server_id> <backup_id>")
            return 1

        server_id = argv[2]
        backup_id = argv[3]

        try:
            server = _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        rt = _safe_read_json(runtime_state_path(str(server_id)))
        state = str((rt or {}).get("state") or "").lower()
        auto_stopped = False
        if state in {"running", "starting"}:
            info(f"Server {server_id} is {state}; attempting graceful stop before restore…")
            try:
                auto_stopped = bool(stop_server(server_id=server_id, timeout_s=30.0))
            except Exception as e:
                error(f"Failed stopping server before restore: {e}")
                return 1

            rt_after = _safe_read_json(runtime_state_path(str(server_id)))
            state_after = str((rt_after or {}).get("state") or "").lower()
            if state_after in {"running", "starting"}:
                error("Server is still running; restore aborted")
                return 1

        folder = str(server.get("folder") or "")
        if not folder:
            error(f"Server {server_id} is missing folder")
            return 1

        zpath = _backup_zip_path(server_id, backup_id)
        if not zpath.exists():
            error(f"Backup {backup_id} does not exist")
            return 1

        server_path = servers_dir() / folder
        server_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="luna-restore-") as td:
            temp_root = Path(td)
            extracted = temp_root / "server"
            extracted.mkdir(parents=True, exist_ok=True)
            try:
                _safe_extract_zip(zpath, extracted)
            except Exception as e:
                error(f"Backup extract failed: {e}")
                return 1

            rollback_path = temp_root / "rollback"
            try:
                if server_path.exists():
                    server_path.rename(rollback_path)
                extracted.rename(server_path)
            except Exception as e:
                # best effort rollback
                if not server_path.exists() and rollback_path.exists():
                    rollback_path.rename(server_path)
                error(f"Restore failed: {e}")
                return 1

        result("backup_restore", {"server_id": server_id, "backup_id": backup_id, "restored": True, "auto_stopped": auto_stopped})
        return 0


    if cmd == "set_tunnel_config":
        if len(argv) < 3:
            error("Usage: cli.py set_tunnel_config <server_id> [--tunneling=true|false] [--sticky-address=true|false]")
            return 1

        server_id = argv[2]
        tunneling: Optional[bool] = None
        sticky_address: Optional[bool] = None

        for arg in argv[3:]:
            if arg.startswith("--tunneling="):
                tunneling = _parse_bool(arg.split("=", 1)[1])
            elif arg.startswith("--sticky-address="):
                sticky_address = _parse_bool(arg.split("=", 1)[1])
            else:
                error(f"Unknown argument: {arg}")
                return 1

        if tunneling is None and sticky_address is None:
            error("No tunnel settings provided")
            return 1

        try:
            updated = _update_tunnel_config(server_id, tunneling=tunneling, sticky_address=sticky_address)
        except Exception as e:
            error(str(e))
            return 1

        _maybe_sync()
        result("set_tunnel_config", {"server": updated})
        return 0

    if cmd == "sync_tunnels":
        _maybe_sync()
        result("sync_tunnels", {"synced": True})
        return 0


    if cmd == "open_server_folder":
        if len(argv) < 3:
            error("Usage: cli.py open_server_folder <server_id>")
            return 1

        server_id = argv[2]
        try:
            server = _find_server_by_id(server_id)
        except Exception as e:
            error(str(e))
            return 1

        folder = str(server.get("folder") or "")
        if not folder:
            error(f"Server {server_id} is missing folder")
            return 1

        server_path = servers_dir() / folder
        if not server_path.exists() or not server_path.is_dir():
            error(f"Server folder {server_path} does not exist")
            return 1

        try:
            _open_in_file_manager(server_path)
        except Exception as e:
            error(f"Failed to open server folder: {e}")
            return 1

        result("open_server_folder", {"server_id": server_id, "path": str(server_path), "opened": True})
        return 0

    if cmd == "rename_server":
        if len(argv) < 4:
            error("Usage: cli.py rename_server <server_id> <new_name>")
            return 1
        server_id = argv[2]
        new_name = " ".join(argv[3:])
        try:
            updated = _rename_server(server_id, new_name)
        except Exception as e:
            error(str(e))
            return 1
        result("rename_server", updated)
        return 0

    if cmd == "list_servers":
        _run_due_scheduled_backups_for_all()
        servers = read_servers_file()
        result("list_servers", {"servers": _enrich_servers_for_ui(servers)})
        return 0

    if cmd == "help":
        info(
            "Available commands: get_versions, install_server, get_platforms, run_server, start_server, stop_server, delete_server, get_reserved_ports, "
            "modrinth_search, modrinth_project, modrinth_download, modrinth_list_installed, modrinth_browse_config_files, modrinth_config_candidates, modrinth_set_preferred_config, read_server_text_file, write_server_text_file, modrinth_uninstall_project, modrinth_remove_installed, backup_create, backup_list, backup_delete, backup_restore, backup_schedule_get, backup_schedule_set, backup_schedule_run, set_tunnel_config, sync_tunnels, open_server_folder, pty_start, pty_write, pty_poll, pty_resize, pty_status, pty_stop"
        )
        info("Add --json to output machine-readable JSON events")
        return 0

    error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
