import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cli } from "../lib/cli";
import type { ServerInfo } from "../lib/types";
import { loadCachedServers, saveCachedServers } from "../lib/cache";
import { isServerOnline } from "../lib/serverRuntime";

export function useServers(addLog: (lvl: any, msg: string) => void) {
  const [servers, setServers] = useState<ServerInfo[]>(() => {
    const cached = loadCachedServers();
    return cached?.servers ?? [];
  });
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef<Promise<void> | null>(null);

  const sortedServers = useMemo(() => {
    return [...servers].sort((a, b) => {
      const ar = isServerOnline(a) ? 0 : 1;
      const br = isServerOnline(b) ? 0 : 1;
      if (ar !== br) return ar - br;
      return a.name.localeCompare(b.name);
    });
  }, [servers]);

  const refresh = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (inFlightRef.current) {
        return inFlightRef.current;
      }

      const run = (async () => {
        if (!silent) {
          setLoading(true);
          addLog("info", "Refreshing server list…");
          await new Promise((resolve) => setTimeout(resolve, 0));
        }

        try {
          const res = await cli<{ servers: ServerInfo[] }>("list_servers");
          const next = res.data.servers ?? [];
          setServers(next);
          saveCachedServers(next);
          if (!silent) {
            addLog("ok", `Loaded ${next.length} server(s).`);
          }
        } catch (e: any) {
          if (!silent) {
            addLog("err", `Refresh failed: ${String(e)}`);
          }
        } finally {
          setLoading(false);
          inFlightRef.current = null;
        }
      })();

      inFlightRef.current = run;
      return run;
    },
    [addLog],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const id = window.setInterval(() => {
      refresh({ silent: true });
    }, 10000);
    return () => window.clearInterval(id);
  }, [refresh]);

  return { servers, sortedServers, loading, refresh, setServers };
}
