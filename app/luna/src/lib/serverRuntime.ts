import { convertFileSrc } from "@tauri-apps/api/core";
import type { ServerInfo } from "./types";

const PLAYER_LIST_KEYS = [
  "players_list",
  "players",
  "online_players_list",
  "onlinePlayers",
  "online_players",
  "player_list",
];

export function isServerOnline(server: ServerInfo): boolean {
  if (typeof server.running === "boolean") return server.running;

  const rt: any = server.runtime ?? {};
  const state = String(rt.state ?? rt.status ?? "").toLowerCase();
  if (["running", "starting", "online", "up"].includes(state)) return true;
  if (["stopped", "stopping", "offline", "down", "error", "crashed"].includes(state)) return false;

  return typeof server.pid === "number" && server.pid > 0;
}

export function serverIconUrl(server: ServerInfo): string | null {
  const derivedIconPath =
    server.icon_path ||
    (server.server_dir ? `${server.server_dir}/server-icon.png` : null) ||
    (server.server_dir ? `${server.server_dir}/icon.png` : null) ||
    (server.server_dir ? `${server.server_dir}/pack.png` : null);

  return derivedIconPath ? convertFileSrc(derivedIconPath) : null;
}

export function playersOnline(server: ServerInfo): number | null {
  const rt: any = server.runtime ?? {};
  const numericCandidates = [
    rt.players_online,
    rt.online_players,
    rt.playersOnline,
    rt.player_count,
    rt.current_players,
    rt.num_players,
    rt.online,
    rt?.players?.online,
    rt?.status?.players,
  ];

  for (const value of numericCandidates) {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      return value;
    }
    if (typeof value === "string") {
      const parsed = Number(value);
      if (Number.isFinite(parsed) && parsed >= 0) {
        return parsed;
      }
    }
  }

  const list = playersList(server);
  return list.length > 0 ? list.length : null;
}

export function maxPlayersFor(server: ServerInfo): string {
  const rt: any = server.runtime ?? {};
  const candidates = [
    rt.maxPlayers,
    rt.max_players,
    rt.maxplayers,
    rt.players_max,
    rt.player_limit,
    rt?.players?.max,
    rt?.status?.max_players,
    (server as any).max_players,
    (server as any).player_limit,
  ];

  for (const value of candidates) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return String(value);
    }
    if (typeof value === "string") {
      const parsed = Number(value);
      if (Number.isFinite(parsed) && parsed > 0) return String(parsed);
    }
  }

  return "?";
}

export function playersList(server: ServerInfo): Array<{ name: string; head_url?: string }> {
  const rt: any = server.runtime ?? {};
  const raw = PLAYER_LIST_KEYS.map((k) => rt[k]).find((value) => Array.isArray(value));

  if (!Array.isArray(raw)) return [];

  return raw
    .map((p: any) => {
      if (typeof p === "string") return { name: p };
      if (p && typeof p.name === "string") return { name: p.name, head_url: p.head_url };
      if (p && typeof p.username === "string") return { name: p.username, head_url: p.head_url };
      return null;
    })
    .filter(Boolean) as Array<{ name: string; head_url?: string }>;
}
