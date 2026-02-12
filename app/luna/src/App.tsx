import { useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { DetailTab, ServerInfo } from "./lib/types";
import { GlobalReset } from "./components/GlobalReset";
import { styles } from "./styles/styles";
import { btn } from "./components/ui";
import { useLogs } from "./hooks/useLogs";
import { useServers } from "./hooks/useServers";
import { ServerCard } from "./components/ServerCard";
import { Overlay } from "./components/Overlay";
import { ServerModal } from "./components/ServerModal";
import { LogsBar } from "./components/LogsBar";
import { cli } from "./lib/cli";
import { isServerOnline, maxPlayersFor, playersOnline } from "./lib/serverRuntime";

export default function App() {
  const { logs, addLog, clearLogs, endRef } = useLogs();
  const { sortedServers, loading, refresh, setServers } = useServers(addLog);

  const [selected, setSelected] = useState<ServerInfo | null>(null);
  const [tab, setTab] = useState<DetailTab>("details");
  const [logsOpen, setLogsOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [actionServerId, setActionServerId] = useState<string | null>(null);

  function publicAddressFor(server: ServerInfo): string {
    const rt: any = server.runtime ?? {};
    const t: any = rt.tunnel ?? {};

    const tcp = typeof t.public_tcp_address === "string" ? t.public_tcp_address : null;
    const udp = typeof t.public_udp_address === "string" ? t.public_udp_address : null;

    // If both edition: show ONE host:port if they match
    if (server.edition === "both") {
      if (tcp && udp && tcp === udp) return tcp;
      // if your device side sets only one, still show it
      return tcp ?? udp ?? "";
    }

    if (server.edition === "bedrock") return udp ?? tcp ?? "";
    return tcp ?? udp ?? "";
  }

  function serverAddress(server: ServerInfo): string {
    const pub = publicAddressFor(server);
    return pub;
  }

  async function startServer(server: ServerInfo) {
    setErr(null);
    addLog("info", `Start requested for "${server.name}".`);
    setActionServerId(server.server_id);
    try {
      await invoke("pty_start", {
        serverId: server.server_id,
        cols: 120,
        rows: 30,
      });
      setServers((curr) =>
        curr.map((s) =>
          s.server_id === server.server_id
            ? {
                ...s,
                running: true,
                runtime: { ...(s.runtime ?? {}), state: "starting" },
              }
            : s,
        ),
      );
      addLog("info", `Waiting for server "${server.name}" to start…`);
      window.setTimeout(() => {
        void refresh({ silent: true });
      }, 350);
    } catch (e: any) {
      const msg = String(e);
      setErr(msg);
      addLog("err", `Start failed: ${msg}`);
    } finally {
      setActionServerId((curr) => (curr === server.server_id ? null : curr));
    }
  }

  async function stopServer(server: ServerInfo) {
    setErr(null);
    addLog("info", `Stop requested for "${server.name}".`);
    setActionServerId(server.server_id);
    try {
      const res = await cli<{ server_id: string; stopped: boolean }>("stop_server", server.server_id);
      const stopped = !!res?.data?.stopped;
      setServers((curr) =>
        curr.map((s) =>
          s.server_id === server.server_id
            ? {
                ...s,
                running: stopped ? false : s.running,
                runtime: {
                  ...(s.runtime ?? {}),
                  state: stopped ? "stopped" : "stopping",
                },
              }
            : s,
        ),
      );
      addLog(stopped ? "ok" : "warn", stopped ? `Stopped "${server.name}".` : `Stop requested for "${server.name}" but server may still be shutting down.`);
      void refresh({ silent: true });
    } catch (e: any) {
      const msg = String(e);
      setErr(msg);
      addLog("err", `Stop failed: ${msg}`);
    } finally {
      setActionServerId((curr) => (curr === server.server_id ? null : curr));
    }
  }


  async function renameServer(server: ServerInfo, name: string) {
    setErr(null);
    try {
      await cli("rename_server", server.server_id, name);
      addLog("ok", `Renamed server to "${name}".`);
      void refresh({ silent: true });
    } catch (e: any) {
      const msg = String(e);
      setErr(msg);
      addLog("err", `Rename failed: ${msg}`);
      throw e;
    }
  }


  async function deleteServer(server: ServerInfo) {
    setErr(null);
    addLog("warn", `Delete requested for "${server.name}".`);
    try {
      await cli("delete_server", server.platform, server.version, server.name);
      addLog("ok", `Deleted server "${server.name}".`);
      setSelected(null);
      void refresh({ silent: true });
    } catch (e: any) {
      const msg = String(e);
      setErr(msg);
      addLog("err", `Delete failed: ${msg}`);
      throw e;
    }
  }
  const selectedServer = useMemo(() => {
    if (!selected) return null;
    return sortedServers.find((s) => s.server_id === selected.server_id) ?? selected;
  }, [selected, sortedServers]);

  const content = useMemo(() => {
    return (
      <div style={styles.grid}>
        {sortedServers.length === 0 && !loading ? (
          <div style={styles.empty}>
            <div style={{ fontSize: 16, fontWeight: 900 }}>No servers</div>
            <div style={{ opacity: 0.75, marginTop: 6 }}>
              Create one with the CLI for now, then hit refresh.
            </div>
            <div style={{ marginTop: 12 }}>
              <button style={btn("primary")} onClick={() => refresh()}>
                Refresh
              </button>
            </div>
          </div>
        ) : (
          sortedServers.map((s) => (
            <ServerCard
              key={s.server_id}
              server={s}
              onOpen={() => {
                setSelected(s);
                setTab("details");
              }}
              onStart={() => startServer(s)}
              onStop={() => stopServer(s)}
              onlinePlayers={playersOnline(s)}
              maxPlayers={maxPlayersFor(s)}
              actionBusy={actionServerId === s.server_id}
              isOnline={isServerOnline(s)}
            />
          ))
        )}
      </div>
    );
  }, [actionServerId, sortedServers, loading, refresh]);

  return (
    <div style={styles.app}>
      <GlobalReset />

      <div style={styles.topChrome}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={styles.brandDot} />
          <div>
            <div style={styles.brandTitle}>Luna</div>
            <div style={styles.brandSub}>Minecraft server manager</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button style={btn("ghost")} onClick={() => setLogsOpen(true)}>
            Logs
          </button>
          <button style={btn("primary")} onClick={() => refresh()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {err && (
        <div style={styles.errorBox}>
          <div style={{ fontWeight: 900, marginBottom: 6 }}>Error</div>
          <div style={{ whiteSpace: "pre-wrap" }}>{err}</div>
        </div>
      )}

      {content}

      {selectedServer && (
        <Overlay onClose={() => setSelected(null)}>
          <ServerModal
            server={selectedServer}
            tab={tab}
            setTab={setTab}
            address={serverAddress(selectedServer)}
            onlinePlayers={playersOnline(selectedServer)}
            maxPlayers={maxPlayersFor(selectedServer)}
            onStart={() => startServer(selectedServer)}
            onStop={() => stopServer(selectedServer)}
            actionBusy={actionServerId === selectedServer.server_id}
            isOnline={isServerOnline(selectedServer)}
            onRequestClose={() => setSelected(null)}
            onRename={(name) => renameServer(selectedServer, name)}
            onDelete={() => deleteServer(selectedServer)}
            addLog={addLog}
          />
        </Overlay>
      )}

      <LogsBar
        open={logsOpen}
        onToggle={() => setLogsOpen((v) => !v)}
        onClear={clearLogs}
        logs={logs}
        endRef={endRef}
      />
    </div>
  );
}
