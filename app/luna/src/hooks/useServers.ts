import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cli } from "../lib/cli";
import type { ServerInfo } from "../lib/types";
import { loadCachedServers, saveCachedServers } from "../lib/cache";

export function useServers(addLog: (lvl: any, msg: string) => void) {
  const [servers, setServers] = useState<ServerInfo[]>(() => {
    const cached = loadCachedServers();
    return cached?.servers ?? [];
  });
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef<Promise<void> | null>(null);

  const sortedServers = useMemo(() => {
    return [...servers].sort((a, b) => {
      const ar = a.running ? 0 : 1;
      const br = b.running ? 0 : 1;
      if (ar !== br) return ar - br;
      return a.name.localeCompare(b.name);
    });
  }, [servers]);

  const refresh = useCallback(async () => {
    if (inFlightRef.current) {
      return inFlightRef.current;
    }

    const run = (async () => {
      setLoading(true);
      addLog("info", "Refreshing server list…");
      await new Promise((resolve) => setTimeout(resolve, 0));

      try {
        const res = await cli<{ servers: ServerInfo[] }>("list_servers");
        const next = res.data.servers ?? [];
        setServers(next);
        saveCachedServers(next);
        addLog("ok", `Loaded ${next.length} server(s).`);
      } catch (e: any) {
        addLog("err", `Refresh failed: ${String(e)}`);
      } finally {
        setLoading(false);
        inFlightRef.current = null;
      }
    })();

    inFlightRef.current = run;
    return run;
  }, [addLog]);

  // Stale-while-revalidate on startup
  useEffect(() => {
    refresh();
  }, [refresh]);

  return { servers, sortedServers, loading, refresh, setServers };
}
