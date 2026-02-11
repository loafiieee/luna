import type { ServerInfo } from "./types";

const KEY = "luna.serverCache.v1";

type CacheShape = { servers: ServerInfo[]; cachedAt: number };

export function loadCachedServers(): CacheShape | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as CacheShape;
  } catch {
    return null;
  }
}

export function saveCachedServers(servers: ServerInfo[]) {
  try {
    const payload: CacheShape = { servers, cachedAt: Date.now() };
    localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    // ignore
  }
}
