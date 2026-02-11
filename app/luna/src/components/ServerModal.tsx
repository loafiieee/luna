import { useMemo, useState } from "react";
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

  const players: Array<{ name: string; head_url?: string }> = useMemo(() => {
    const rt = server.runtime ?? {};
    const list =
      rt.players_list ??
      rt.players ??
      rt.online_players_list ??
      rt.onlinePlayers ??
      rt.online_players ??
      [];
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
            <div style={styles.modalSubtitle}>
              {server.edition} · {server.platform} · {server.version}
            </div>
          </div>
        </div>

        <div style={styles.modalTopRight}>
          <div style={styles.topSeparator} />
          <button
            style={btn(isOnline ? "danger" : "primary")}
            onClick={() => {
              addLog("info", `${isOnline ? "Stop" : "Start"} clicked for "${server.name}".`);
              isOnline ? onStop() : onStart();
            }}
          >
            {isOnline ? "Stop" : "Start"}
          </button>

          <div style={styles.topSeparator} />

          <div style={styles.addrWrap}>
            <div style={styles.addrLabel}>Public Address</div>
            <div style={styles.addrValue} title={address}>
              {address || "(none)"}
            </div>
          </div>

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
          {tab === "details" && <DetailsPane server={server} address={address} maxPlayers={maxPlayers} />}
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
            <div style={{ opacity: 0.7 }}>
              {(isOnline && typeof onlinePlayers === "number" ? onlinePlayers : 0)}/{maxPlayers}
            </div>
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

function DetailsPane({ server, address, maxPlayers }: { server: ServerInfo; address: string; maxPlayers: string }) {
  const rt: any = server.runtime ?? {};
  const t: any = rt.tunnel ?? {};

  const pid: number | null =
    (typeof server.pid === "number" ? server.pid : null) ??
    (typeof rt.server_pid === "number" ? rt.server_pid : null);

  const javaPort = typeof rt.java_port === "number" ? rt.java_port : 0;
  const bedrockPort = typeof rt.bedrock_port === "number" ? rt.bedrock_port : 0;

  const tcp = typeof t.public_tcp_address === "string" ? t.public_tcp_address : null;
  const udp = typeof t.public_udp_address === "string" ? t.public_udp_address : null;
  const voice = typeof t.public_voice_address === "string" ? t.public_voice_address : null;

  // started_at is an epoch seconds float in your runtime
  const startedAtSec = typeof rt.started_at === "number" ? rt.started_at : null;
  const uptime = startedAtSec ? Math.max(0, Math.floor(Date.now() / 1000 - startedAtSec)) : null;

  function fmtUptime(sec: number | null) {
    if (sec == null) return "—";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return `${h}h ${m}m`;
  }

  const state = typeof rt.state === "string" ? rt.state : server.running ? "running" : "stopped";

  return (
    <div>
      <div style={styles.paneTitle}>Details</div>

      <div style={{ marginTop: 12 }}>
        <div style={{ opacity: 0.75, fontWeight: 800, fontSize: 12 }}>Live Stats</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12, marginTop: 10 }}>
          <KV k="State" v={state} />
          <KV k="PID" v={pid != null ? String(pid) : "—"} mono />
          <KV k="Uptime" v={fmtUptime(uptime)} />
          <KV k="Java Port" v={javaPort ? String(javaPort) : "—"} />
          <KV k="Bedrock Port" v={bedrockPort ? String(bedrockPort) : "—"} />
          <KV k="Players" v={`${(server.running && typeof rt.players_online === "number" ? rt.players_online : 0)}/${maxPlayers}`} />
          <KV k="Public TCP" v={tcp ?? "—"} mono />
          <KV k="Public UDP" v={udp ?? "—"} mono />
          <KV k="Voice" v={voice ?? "—"} mono />
        </div>
      </div>

      <div style={styles.kvGrid}>
        <KV k="Name" v={server.name} />
        <KV k="Edition" v={server.edition} />
        <KV k="Platform" v={server.platform} />
        <KV k="Version" v={server.version} />
        <KV k="Folder" v={server.folder} mono />
        <KV k="Tunneling" v={server.tunneling ? "Enabled" : "Disabled"} />
        <KV k="Sticky address" v={server.sticky_address ? "Yes" : "No"} />
        <KV k="Address (primary)" v={address || "—"} mono />
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>Server directory</div>
        <div style={styles.monoBox}>{server.server_dir ?? "(unknown)"}</div>
      </div>
    </div>
  );
}

function TunnelsPane({ server }: { server: ServerInfo }) {
  const rt: any = server.runtime ?? {};
  const t: any = rt.tunnel ?? {};

  const tcp = typeof t.public_tcp_address === "string" ? t.public_tcp_address : null;
  const udp = typeof t.public_udp_address === "string" ? t.public_udp_address : null;
  const voice = typeof t.public_voice_address === "string" ? t.public_voice_address : null;

  const subdomain = typeof t.subdomain === "string" ? t.subdomain : null;
  const suffix = typeof t.domain_suffix === "string" ? t.domain_suffix : null;

  const primary =
    (server.edition === "bedrock" ? udp ?? tcp : tcp ?? udp) ?? "(none)";

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
