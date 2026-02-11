import { useEffect, useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import type { DetailTab, ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";

export function ServerModal({
  server,
  tab,
  setTab,
  address,
  onlinePlayers,
  maxPlayers,
  onStart,
  onStop,
  onRequestClose,
  addLog,
}: {
  server: ServerInfo;
  tab: DetailTab;
  setTab: (t: DetailTab) => void;
  address: string;
  onlinePlayers: number | null;
  maxPlayers: string;
  onStart: () => void;
  onStop: () => void;
  onRequestClose: () => void;
  addLog: (level: "info" | "ok" | "warn" | "err", msg: string) => void;
}) {
  const isOnline = !!server.running;
  const icon = server.icon_path ? convertFileSrc(server.icon_path) : null;

  const [playerSearch, setPlayerSearch] = useState("");
  const [copiedAddress, setCopiedAddress] = useState(false);

  const players: Array<{ name: string; head_url?: string }> = useMemo(() => {
    const rt = server.runtime ?? {};
    const list = rt.players_list ?? rt.players ?? rt.online_players_list ?? rt.onlinePlayers ?? rt.online_players ?? [];
    if (!Array.isArray(list)) return [];
    return list
      .map((p: any) => {
        if (typeof p === "string") return { name: p };
        if (p && typeof p.name === "string") return { name: p.name, head_url: p.head_url };
        if (p && typeof p.username === "string") return { name: p.username, head_url: p.head_url };
        return null;
      })
      .filter(Boolean) as Array<{ name: string; head_url?: string }>;
  }, [server.runtime]);

  const filteredPlayers = useMemo(() => {
    const q = playerSearch.trim().toLowerCase();
    if (!q) return players;
    return players.filter((p) => p.name.toLowerCase().includes(q));
  }, [players, playerSearch]);

  useEffect(() => {
    if (!copiedAddress) return;
    const t = window.setTimeout(() => setCopiedAddress(false), 1600);
    return () => window.clearTimeout(t);
  }, [copiedAddress]);

  async function copyAddress() {
    if (!address) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(address);
      } else {
        throw new Error("clipboard unavailable");
      }
      setCopiedAddress(true);
      addLog("ok", `Copied public address for \"${server.name}\".`);
    } catch {
      addLog("warn", "Could not copy to clipboard automatically.");
    }
  }

  return (
    <div style={styles.modal}>
      <div style={styles.modalTopBar}>
        <div style={styles.modalTopLeft}>
          <div style={styles.modalIcon}>
            {icon ? (
              <img
                src={icon}
                alt="server icon"
                style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated" }}
              />
            ) : (
              <div style={styles.modalIconPlaceholder}>?</div>
            )}
          </div>

          <div style={{ minWidth: 0 }}>
            <div style={styles.modalTitleRow}>
              <div style={styles.modalName}>{server.name}</div>
              <div style={{ marginLeft: 10 }}>{isOnline ? pill("Online", "ok") : pill("Offline", "muted")}</div>
            </div>
          </div>
        </div>

        <div style={styles.modalTopRight}>
          <button
            style={btn(isOnline ? "danger" : "primary")}
            onClick={() => {
              addLog("info", `${isOnline ? "Stop" : "Start"} clicked for "${server.name}".`);
              isOnline ? onStop() : onStart();
            }}
          >
            {isOnline ? "Stop" : "Start"}
          </button>

          <button
            type="button"
            style={{ ...styles.addrButton, ...(copiedAddress ? styles.addrButtonCopied : {}) }}
            onClick={copyAddress}
            title={address ? "Click to copy" : "No public address yet"}
            disabled={!address}
          >
            <div style={styles.addrLabel}>Public Address</div>
            <div style={styles.addrValue} title={address}>{address || "(pending tunnel)"}</div>
            <div style={styles.addrHint}>{copiedAddress ? "Copied" : "Click to copy"}</div>
          </button>

          <button style={btn("ghost")} onClick={onRequestClose} title="Close">
            ✕
          </button>
        </div>
      </div>

      <div style={styles.modalBody}>
        <div style={styles.leftNav}>
          <NavItem label="Details" active={tab === "details"} onClick={() => setTab("details")} />
          <NavItem label="Console" active={tab === "console"} onClick={() => setTab("console")} />
          <NavItem label="Content" active={tab === "content"} onClick={() => setTab("content")} />
          <NavItem label="Backups" active={tab === "backups"} onClick={() => setTab("backups")} />
          <NavItem label="Tunnels" active={tab === "tunnels"} onClick={() => setTab("tunnels")} />
          <NavItem label="Settings" active={tab === "settings"} onClick={() => setTab("settings")} />
          <NavItem label="Server Folder" active={tab === "server_folder"} onClick={() => setTab("server_folder")} />
        </div>

        <div style={styles.centerPane}>
          {tab === "details" && <DetailsPane server={server} />}
          {tab === "console" && <PlaceholderPane title="Console" desc="Coming next (PTY + xterm)." />}
          {tab === "content" && (
            <PlaceholderPane title="Content" desc="Plugins / Mods / Datapacks UI scaffold (Modrinth later)." />
          )}
          {tab === "backups" && <PlaceholderPane title="Backups" desc="Hook to backup commands later." />}
          {tab === "tunnels" && <TunnelsPane server={server} />}
          {tab === "settings" && <PlaceholderPane title="Settings" desc="server.properties editor + RAM/port, etc." />}
          {tab === "server_folder" && <PlaceholderPane title="Server Folder" desc="Open folder, open logs, etc." />}
        </div>

        <div style={styles.rightPane}>
          <div style={styles.playersHeader}>
            <div style={{ fontWeight: 900 }}>Online Players</div>
            <div style={{ opacity: 0.7 }}>{(isOnline && typeof onlinePlayers === "number" ? onlinePlayers : 0)}/{maxPlayers}</div>
          </div>

          <input
            style={styles.search}
            placeholder="Search players…"
            value={playerSearch}
            onChange={(e) => setPlayerSearch(e.target.value)}
            disabled={!isOnline}
          />

          <div style={styles.playersList}>
            {!isOnline ? (
              <div style={styles.playersEmpty}>Server is offline.</div>
            ) : filteredPlayers.length === 0 ? (
              <div style={styles.playersEmpty}>No players found.</div>
            ) : (
              filteredPlayers.map((p) => <PlayerRow key={p.name} name={p.name} headUrl={p.head_url} />)
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function NavItem({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,.08)",
        background: active ? "rgba(255,255,255,.10)" : "transparent",
        color: "rgba(255,255,255,.92)",
        fontWeight: active ? 900 : 700,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

function PlayerRow({ name, headUrl }: { name: string; headUrl?: string }) {
  return (
    <div style={styles.playerRow}>
      <div style={styles.playerHead}>
        {headUrl ? (
          <img src={headUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ fontSize: 12, opacity: 0.8 }}>{name.slice(0, 2).toUpperCase()}</div>
        )}
      </div>
      <div style={{ fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
    </div>
  );
}

function DetailsPane({ server }: { server: ServerInfo }) {
  const rt: any = server.runtime ?? {};
  const isOnline = !!server.running;
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!isOnline) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isOnline]);

  const cpuPercent = pickNumber(rt, ["cpu_percent", "cpu_usage", "cpu", "process_cpu_percent"]);
  const ramMb = pickNumber(rt, ["ram_mb", "ram_usage_mb", "memory_mb", "rss_mb", "memory"]);

  const startedAtSec = typeof rt.started_at === "number" ? rt.started_at : null;
  const uptimeSeconds = isOnline && startedAtSec ? Math.max(0, Math.floor(nowMs / 1000 - startedAtSec)) : null;

  const perfSamples = buildPerfSamples(rt);

  return (
    <div>
      <div style={styles.paneTitle}>Details</div>

      <div style={styles.detailsMetricsGrid}>
        <KV k="CPU usage" v={cpuPercent != null ? `${cpuPercent.toFixed(1)}%` : "—"} />
        <KV k="RAM usage" v={ramMb != null ? `${ramMb.toFixed(0)} MB` : "—"} />
        <KV k="Server uptime" v={formatUptime(uptimeSeconds)} mono />
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>Performance graph</div>
        <div style={styles.perfGraph}>
          {perfSamples.map((sample, idx) => (
            <div key={idx} style={styles.perfBarWrap}>
              <div style={{ ...styles.perfBar, height: `${Math.max(4, Math.min(100, sample))}%` }} />
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>Server directory</div>
        <div style={styles.monoBox}>{server.server_dir ?? "(unknown)"}</div>
      </div>
    </div>
  );
}

function pickNumber(source: any, keys: string[]): number | null {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function buildPerfSamples(rt: any): number[] {
  const candidates = [rt?.cpu_history, rt?.metrics?.cpu, rt?.performance?.cpu, rt?.history?.cpu];
  for (const c of candidates) {
    if (!Array.isArray(c)) continue;
    const nums = c.filter((n: any) => typeof n === "number" && Number.isFinite(n)).slice(-24);
    if (nums.length > 0) return nums.map((n: number) => Math.max(0, Math.min(100, n)));
  }
  return new Array(24).fill(0);
}

function formatUptime(sec: number | null) {
  if (sec == null) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function TunnelsPane({ server }: { server: ServerInfo }) {
  const rt: any = server.runtime ?? {};
  const t: any = rt.tunnel ?? {};

  const tcp = typeof t.public_tcp_address === "string" ? t.public_tcp_address : null;
  const udp = typeof t.public_udp_address === "string" ? t.public_udp_address : null;
  const voice = typeof t.public_voice_address === "string" ? t.public_voice_address : null;

  const subdomain = typeof t.subdomain === "string" ? t.subdomain : null;
  const suffix = typeof t.domain_suffix === "string" ? t.domain_suffix : null;

  const primary = (server.edition === "bedrock" ? udp ?? tcp : tcp ?? udp) ?? "(none)";

  return (
    <div>
      <div style={styles.paneTitle}>Tunnels</div>
      <div style={{ opacity: 0.75, marginTop: 6 }}>
        Public endpoints from runtime. (Java uses TCP; Bedrock uses UDP.)
      </div>

      <div style={styles.kvGrid}>
        <KV k="Tunneling enabled" v={server.tunneling ? "Yes" : "No"} />
        <KV k="Sticky address" v={server.sticky_address ? "Yes" : "No"} />
        <KV k="Subdomain" v={subdomain ?? "—"} mono />
        <KV k="Domain suffix" v={suffix ?? "—"} mono />
        <KV k="Primary public address" v={primary} mono />
        <KV k="Public TCP (Java)" v={tcp ?? "—"} mono />
        <KV k="Public UDP (Bedrock)" v={udp ?? "—"} mono />
        <KV k="Public Voice" v={voice ?? "—"} mono />
      </div>
    </div>
  );
}

function PlaceholderPane({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <div style={styles.paneTitle}>{title}</div>
      <div style={{ opacity: 0.75, marginTop: 6, lineHeight: 1.5 }}>{desc}</div>
      <div
        style={{
          marginTop: 14,
          padding: 14,
          borderRadius: 16,
          border: "1px dashed rgba(255,255,255,.14)",
          opacity: 0.8,
        }}
      >
        UI scaffold is ready — we’ll hook this to real commands next.
      </div>
    </div>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div style={styles.kv}>
      <div style={styles.k}>{k}</div>
      <div
        style={{
          ...styles.v,
          ...(mono ? { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" } : {}),
        }}
      >
        {v}
      </div>
    </div>
  );
}
