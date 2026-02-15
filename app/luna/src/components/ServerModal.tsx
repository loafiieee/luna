import { Dispatch, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { invoke } from "@tauri-apps/api/core";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import type { DetailTab, ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";
import { isServerOnline, playersList } from "../lib/serverRuntime";

export type ServerModalProps = {
  server: ServerInfo;
  tab: DetailTab;
  setTab: Dispatch<SetStateAction<DetailTab>>;
  address: string;
  onlinePlayers: number | null;
  maxPlayers: string;
  onStart: () => void;
  onStop: () => void;
  onRequestClose: () => void;
  onRename: (name: string) => Promise<void>;
  actionBusy: boolean;
  isOnline: boolean;
  onDelete: () => Promise<void>;
  onLiveRefresh: () => void;
  addLog: (level: "info" | "ok" | "warn" | "err", msg: string) => void;
};

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
  onRename,
  onDelete,
  onLiveRefresh,
  addLog,
  isOnline,
  actionBusy,
}: ServerModalProps) {
  const derivedIconPath =
    server.icon_path ||
    (server.server_dir ? `${server.server_dir}/server-icon.png` : null) ||
    (server.server_dir ? `${server.server_dir}/icon.png` : null);
  const icon = derivedIconPath ? convertFileSrc(derivedIconPath) : null;
  const defaultIcon = new URL("/default-server-icon.png", window.location.origin).toString();

  const [playerSearch, setPlayerSearch] = useState("");
  const [copiedAddress, setCopiedAddress] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(server.name);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [playerActionMenu, setPlayerActionMenu] = useState<{ name: string; x: number; y: number } | null>(null);
  const [confirmPlayerAction, setConfirmPlayerAction] = useState<{ action: "ban" | "op" | "deop" | "kick"; name: string } | null>(null);
  const [playerActionBusy, setPlayerActionBusy] = useState(false);
  const [banManagerOpen, setBanManagerOpen] = useState(false);
  const [banManagerLoading, setBanManagerLoading] = useState(false);
  const [bannedPlayers, setBannedPlayers] = useState<string[]>([]);
  const [bannedIps, setBannedIps] = useState<string[]>([]);
  const [banSearch, setBanSearch] = useState("");

  const players: Array<{ name: string; head_url?: string }> = useMemo(() => playersList(server), [server]);

  const filteredPlayers = useMemo(() => {
    const q = playerSearch.trim().toLowerCase();
    if (!q) return players;
    return players.filter((p) => p.name.toLowerCase().includes(q));
  }, [players, playerSearch]);

  useEffect(() => {
    setNameDraft(server.name);
  }, [server.name]);

  useEffect(() => {
    setBanManagerOpen(false);
    setBanSearch("");
    setBannedPlayers([]);
    setBannedIps([]);
  }, [server.server_id]);

  useEffect(() => {
    const id = window.setInterval(() => {
      onLiveRefresh();
    }, 1200);
    return () => window.clearInterval(id);
  }, [onLiveRefresh]);

  async function submitRename() {
    const next = nameDraft.trim();
    if (!next || next === server.name) {
      setEditingName(false);
      setNameDraft(server.name);
      return;
    }
    try {
      setRenaming(true);
      await onRename(next);
      setEditingName(false);
    } finally {
      setRenaming(false);
    }
  }

  function deleteCurrentServer() {
    setConfirmDeleteOpen(true);
  }

  async function confirmDeleteServer() {
    try {
      setDeleting(true);
      await onDelete();
      setConfirmDeleteOpen(false);
    } finally {
      setDeleting(false);
    }
  }

  
async function runPlayerCommand(action: "ban" | "op" | "deop" | "kick" | "copy", name: string) {
  if (!name) return;

  if (action === "copy") {
    try {
      await navigator.clipboard.writeText(name);
      addLog("ok", `Copied username "${name}".`);
    } catch {
      addLog("warn", "Could not copy to clipboard automatically.");
    }
    setPlayerActionMenu(null);
    return;
  }

  const cmd =
    action === "kick" ? `kick ${name}` :
    action === "ban" ? `ban ${name}` :
    action === "op" ? `op ${name}` :
    `deop ${name}`;

  try {
    setPlayerActionBusy(true);
    await invoke("send_server_console_command", { serverId: server.server_id, command: cmd });
    addLog("ok", `Sent "${cmd}".`);
  } catch (e: any) {
    addLog("err", `Failed to send "${cmd}": ${String(e)}`);
  } finally {
    setPlayerActionBusy(false);
    setPlayerActionMenu(null);
  }
}

async function refreshBans() {
    if (!server.server_dir) {
      setBannedPlayers([]);
      setBannedIps([]);
      return;
    }
    try {
      setBanManagerLoading(true);
      const res = await invoke<{ banned_players: string[]; banned_ips: string[] }>("read_server_bans", {
        serverDir: server.server_dir,
      });
      setBannedPlayers(Array.isArray(res?.banned_players) ? res.banned_players : []);
      setBannedIps(Array.isArray(res?.banned_ips) ? res.banned_ips : []);
    } catch (e: any) {
      addLog("err", `Could not load ban lists: ${String(e)}`);
    } finally {
      setBanManagerLoading(false);
    }
}

async function unbanEntry(kind: "player" | "ip", value: string) {
    const cmd = kind === "player" ? `pardon ${value}` : `pardon-ip ${value}`;
    try {
      setPlayerActionBusy(true);
      await invoke("send_server_console_command", { serverId: server.server_id, command: cmd });
      addLog("ok", `Sent "${cmd}".`);
      await refreshBans();
    } catch (e: any) {
      addLog("err", `Failed to send "${cmd}": ${String(e)}`);
    } finally {
      setPlayerActionBusy(false);
    }
}

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
            <img
              src={icon ?? defaultIcon}
              alt="server icon"
              style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated" }}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).src = defaultIcon;
              }}
            />
          </div>

          <div style={{ minWidth: 0 }}>
            <div style={styles.modalTitleRow}>
              {editingName ? (
                <input
                  autoFocus
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      submitRename();
                    }
                    if (e.key === "Escape") {
                      e.preventDefault();
                      setEditingName(false);
                      setNameDraft(server.name);
                    }
                  }}
                  onBlur={submitRename}
                  disabled={renaming}
                  style={styles.modalNameInput}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setEditingName(true)}
                  title="Click to rename"
                  style={styles.modalNameButton}
                >
                  {server.name}
                </button>
              )}
              <div style={{ marginLeft: 10 }}>{isOnline ? pill("Online", "ok") : pill("Offline", "muted")}</div>
            </div>
          </div>
        </div>

        <div style={styles.modalTopRight}>
          <button
            style={btn(isOnline ? "danger" : "primary")}
            onClick={() => {
              addLog("info", `${actionBusy ? (isOnline ? "Stopping…" : "Starting…") : (isOnline ? "Stop" : "Start")} clicked for "${server.name}".`);
              isOnline ? onStop() : onStart();
            }}
            disabled={actionBusy}
          >
            {actionBusy ? (isOnline ? "Stopping…" : "Starting…") : (isOnline ? "Stop" : "Start")}
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

          <div style={styles.leftNavFooter}>
            <button
              type="button"
              style={styles.deleteServerBtn}
              onClick={deleteCurrentServer}
              disabled={deleting}
              title="Delete server"
            >
              {deleting ? "Deleting…" : "Delete Server"}
            </button>
          </div>
        </div>

        <div style={styles.centerPane}>
          {tab === "details" && <DetailsPane server={server} />}
          {tab === "console" && <ConsolePane server={server} addLog={addLog} isOnline={isOnline} actionBusy={actionBusy} />}
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
            <div style={{ opacity: 0.7 }}>{(typeof onlinePlayers === "number" ? onlinePlayers : 0)}/{maxPlayers}</div>
          </div>

          <input
            style={styles.search}
            placeholder="Search players…"
            value={playerSearch}
            onChange={(e) => setPlayerSearch(e.target.value)}
            disabled={!isOnline}
          />

          <div style={styles.playersList}>
            {banManagerOpen ? (
              <div style={styles.banManagerWrap}>
                <div style={styles.banManagerHead}>
                  <div style={{ fontWeight: 900 }}>Ban Manager</div>
                  <button
                    type="button"
                    style={btn("ghost")}
                    onClick={() => setBanManagerOpen(false)}
                    title="Close ban manager"
                  >
                    Close
                  </button>
                </div>

                <input
                  style={styles.search}
                  placeholder="Search banned players or IPs…"
                  value={banSearch}
                  onChange={(e) => setBanSearch(e.target.value)}
                />

                <button
                  type="button"
                  style={btn("ghost")}
                  onClick={refreshBans}
                  disabled={banManagerLoading || playerActionBusy}
                >
                  {banManagerLoading ? "Refreshing…" : "Refresh bans"}
                </button>

                <BanSection
                  title="Banned players"
                  emptyLabel="No banned players."
                  entries={bannedPlayers.filter((x) => x.toLowerCase().includes(banSearch.trim().toLowerCase()))}
                  actionLabel="Unban"
                  disabled={playerActionBusy}
                  onAction={(entry) => unbanEntry("player", entry)}
                />

                <BanSection
                  title="Banned IPs"
                  emptyLabel="No banned IPs."
                  entries={bannedIps.filter((x) => x.toLowerCase().includes(banSearch.trim().toLowerCase()))}
                  actionLabel="Unban IP"
                  disabled={playerActionBusy}
                  onAction={(entry) => unbanEntry("ip", entry)}
                />
              </div>
            ) : !isOnline ? (
              <div style={styles.playersEmpty}>Server is offline.</div>
            ) : filteredPlayers.length === 0 ? (
              typeof onlinePlayers === "number" && onlinePlayers > 0 ? (
                <div style={styles.playersEmpty}>{onlinePlayers} player(s) online (runtime did not provide names).</div>
              ) : (
                <div style={styles.playersEmpty}>No players found.</div>
              )
            ) : (
              filteredPlayers.map((p) => (
                <PlayerRow
                  key={p.name}
                  name={p.name}
                  headUrl={p.head_url}
                  onOpenMenu={(name, evt) => {
                    const rect = (evt.currentTarget as HTMLDivElement).getBoundingClientRect();
                    setPlayerActionMenu({ name, x: rect.right - 10, y: rect.top + rect.height });
                  }}
                />
              ))
            )}
          </div>

          <button
            type="button"
            style={styles.banManagerToggle}
            onClick={() => {
              const next = !banManagerOpen;
              setBanManagerOpen(next);
              if (next) void refreshBans();
            }}
          >
            {banManagerOpen ? "Hide Ban Manager" : "Open Ban Manager"}
          </button>
        </div>
      </div>

      {playerActionMenu && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 65,
          }}
          onClick={() => setPlayerActionMenu(null)}
        >
          <div
            style={{
              position: "fixed",
              left: Math.max(8, playerActionMenu.x - 180),
              top: Math.max(8, playerActionMenu.y + 8),
              width: 180,
              padding: 8,
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,.12)",
              background: "rgba(7,12,24,.98)",
              boxShadow: "0 12px 30px rgba(0,0,0,.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: "4px 8px", opacity: 0.65, fontSize: 12, fontWeight: 800 }}>
              {playerActionMenu.name}
            </div>
            <MenuItem label="Copy username" onClick={() => runPlayerCommand("copy", playerActionMenu.name)} disabled={playerActionBusy} />
            <MenuItem label="Kick" onClick={() => setConfirmPlayerAction({ action: "kick", name: playerActionMenu.name })} disabled={playerActionBusy} />
            <MenuItem label="Ban" onClick={() => setConfirmPlayerAction({ action: "ban", name: playerActionMenu.name })} disabled={playerActionBusy} />
            <MenuItem label="Op" onClick={() => runPlayerCommand("op", playerActionMenu.name)} disabled={playerActionBusy} />
            <MenuItem label="Deop" onClick={() => runPlayerCommand("deop", playerActionMenu.name)} disabled={playerActionBusy} />
          </div>
        </div>
      )}

      {confirmPlayerAction && (
        <div style={styles.confirmOverlay}>
          <div style={styles.confirmCard}>
            <div style={{ fontWeight: 900, fontSize: 16 }}>Confirm {confirmPlayerAction.action}</div>
            <div style={{ marginTop: 8, opacity: 0.78, lineHeight: 1.4 }}>
              {confirmPlayerAction.action === "ban" ? "Ban" : "Kick"} <b>{confirmPlayerAction.name}</b>?
            </div>
            <div style={styles.confirmActions}>
              <button type="button" style={btn("ghost")} onClick={() => setConfirmPlayerAction(null)} disabled={playerActionBusy}>
                Cancel
              </button>
              <button
                type="button"
                style={btn(confirmPlayerAction.action === "ban" ? "danger" : "primary")}
                onClick={async () => {
                  const { action, name } = confirmPlayerAction;
                  setConfirmPlayerAction(null);
                  await runPlayerCommand(action, name);
                  if (action === "ban" && banManagerOpen) {
                    await refreshBans();
                  }
                }}
                disabled={playerActionBusy}
              >
                {playerActionBusy ? "Sending…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDeleteOpen && (
        <div style={styles.confirmOverlay}>
          <div style={styles.confirmCard}>
            <div style={{ fontWeight: 900, fontSize: 16 }}>Delete server?</div>
            <div style={{ marginTop: 8, opacity: 0.78, lineHeight: 1.4 }}>
              This removes <b>{server.name}</b> and its server files. This cannot be undone.
            </div>
            <div style={styles.confirmActions}>
              <button
                type="button"
                style={btn("ghost")}
                onClick={() => setConfirmDeleteOpen(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                style={btn("danger")}
                onClick={confirmDeleteServer}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Delete server"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BanSection({
  title,
  entries,
  emptyLabel,
  actionLabel,
  disabled,
  onAction,
}: {
  title: string;
  entries: string[];
  emptyLabel: string;
  actionLabel: string;
  disabled: boolean;
  onAction: (entry: string) => void;
}) {
  return (
    <div style={styles.banSection}>
      <div style={styles.banSectionTitle}>{title}</div>
      {entries.length === 0 ? (
        <div style={styles.playersEmpty}>{emptyLabel}</div>
      ) : (
        entries.map((entry) => (
          <div key={`${title}-${entry}`} style={styles.banRow}>
            <div style={{ fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis" }}>{entry}</div>
            <button type="button" style={btn("ghost")} onClick={() => onAction(entry)} disabled={disabled}>
              {actionLabel}
            </button>
          </div>
        ))
      )}
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

function MenuItem({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "8px 10px",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,.06)",
        background: "rgba(255,255,255,.04)",
        color: "rgba(255,255,255,.92)",
        fontWeight: 900,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.45 : 1,
        marginBottom: 6,
      }}
    >
      {label}
    </button>
  );
}

function PlayerRow({
  name,
  headUrl,
  onOpenMenu,
}: {
  name: string;
  headUrl?: string;
  onOpenMenu: (name: string, evt: import("react").MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      style={{ ...styles.playerRow, cursor: "pointer" }}
      onClick={(e) => onOpenMenu(name, e)}
      title="Click for actions"
    >
      <div style={styles.playerHead}>
        {headUrl ? (
          <img src={headUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ fontSize: 12, opacity: 0.8 }}>{name.slice(0, 2).toUpperCase()}</div>
        )}
      </div>
      <div style={{ fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{name}</div>
      <div style={{ opacity: 0.65, fontWeight: 900 }}>⋯</div>
    </div>
  );
}


function ConsolePane({
  server,
  addLog,
  isOnline,
  actionBusy,
}: {
  server: ServerInfo;
  addLog: (level: "info" | "ok" | "warn" | "err", msg: string) => void;
  isOnline: boolean;
  actionBusy: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const pollerRef = useRef<number | null>(null);
  const offsetRef = useRef<number>(0);
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const [pollErr, setPollErr] = useState<string | null>(null);

  useEffect(() => {
    offsetRef.current = 0;
    setPollErr(null);
    terminalRef.current?.clear();
  }, [server.server_id]);

  useEffect(() => {
    if (isOnline) return;

    terminalRef.current?.clear();
    setCommand("");

    void (async () => {
      try {
        const res = await invoke<{ lines: string[]; offset: number }>("read_server_console", {
          serverId: server.server_id,
          offset: 0,
          maxLines: 0,
        });
        offsetRef.current = res.offset;
      } catch {
        // ignore
      }
    })();
  }, [isOnline, server.server_id]);

  useEffect(() => {
    const term = new Terminal({
      convertEol: true,
      fontSize: 12,
      cursorBlink: true,
      theme: {
        background: "#020617",
      },
      scrollback: 5000,
      disableStdin: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    terminalRef.current = term;
    fitRef.current = fit;

    if (containerRef.current) {
      term.open(containerRef.current);
      fit.fit();
    }

    const poll = async () => {
      try {
        const res = await invoke<{ lines: string[]; offset: number }>("read_server_console", {
          serverId: server.server_id,
          offset: offsetRef.current,
          maxLines: 200,
        });
        offsetRef.current = res.offset;
        if (res.lines.length > 0) {
          for (const line of res.lines) {
            term.writeln(line);
          }
        }
        setPollErr(null);
      } catch (e: any) {
        setPollErr(String(e));
      }
    };

    poll();
    // Don't hammer the backend; 2–3 polls/sec is plenty and avoids huge log backlogs.
    pollerRef.current = window.setInterval(poll, 500);

    let observer: ResizeObserver | null = null;
    if (containerRef.current && "ResizeObserver" in window) {
      observer = new ResizeObserver(() => {
        try {
          fit.fit();
        } catch {
          // ignore
        }
      });
      observer.observe(containerRef.current);
    }

    return () => {
      if (pollerRef.current) {
        window.clearInterval(pollerRef.current);
        pollerRef.current = null;
      }
      observer?.disconnect();
      term.dispose();
      terminalRef.current = null;
      fitRef.current = null;
    };
  }, [server.server_id]);

  async function sendCommand() {
    if (!command.trim()) return;
    const out = command.trim();
    setSending(true);
    try {
      await invoke("send_server_console_command", { serverId: server.server_id, command: out });
      addLog("ok", `Console command sent to "${server.name}": ${out}`);
      setCommand("");
    } catch (e: any) {
      const msg = String(e);
      addLog("err", `Console command failed for "${server.name}": ${msg}`);
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <div style={styles.paneTitle}>Console</div>
      <div style={styles.consoleHint}>Live output from runtime console. Type commands below to send to server stdin.</div>
      {!isOnline && <div style={{ marginTop: 8, opacity: 0.8 }}>Waiting for server start…</div>}

      <div style={styles.consoleView} ref={containerRef} />

      <div style={styles.consoleInputRow}>
        <input
          style={styles.consoleInput}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder={isOnline ? "say hello" : actionBusy ? "Waiting for server to start…" : "Start server to use console commands"}
          disabled={(!isOnline && !actionBusy) || sending}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              sendCommand();
            }
          }}
        />
        <button type="button" style={btn("primary")} onClick={sendCommand} disabled={(!isOnline && !actionBusy) || sending || !command.trim()}>
          {sending ? "Sending…" : "Send"}
        </button>
      </div>

      {pollErr && <div style={styles.consoleError}>Console read error: {pollErr}</div>}
    </div>
  );
}

function DetailsPane({ server }: { server: ServerInfo }) {
  const isOnline = isServerOnline(server);
  // When offline, don't show stale perf stats from the previous run.
  const rt: any = isOnline ? (server.runtime ?? {}) : {};
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!isOnline) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isOnline]);

  const cpuPercent = pickCpuPercent(rt);
  const ramUsedMb = pickRamUsedMb(rt);
  const ramMaxMb = pickRamMaxMb(rt);

  const startedAtSec = typeof rt.started_at === "number" ? rt.started_at : null;
  const uptimeSeconds = isOnline && startedAtSec ? Math.max(0, Math.floor(nowMs / 1000 - startedAtSec)) : null;

  const perfSamples = buildPerfSamples(rt);
  const graphMaxMb =
    ramMaxMb != null && ramMaxMb > 0
      ? ramMaxMb
      : Math.max(512, ...perfSamples, ramUsedMb != null ? ramUsedMb : 0);

  return (
    <div>
      <div style={styles.paneTitle}>Details</div>

      <div style={styles.detailsMetricsGrid}>
        <KV k="CPU usage" v={cpuPercent != null ? `${cpuPercent.toFixed(1)}%` : "—"} />
        <KV k="RAM usage" v={ramUsedMb != null ? `${ramUsedMb.toFixed(0)}${ramMaxMb != null ? `/${ramMaxMb.toFixed(0)}` : ""} MB` : "—"} />
        <KV k="Server uptime" v={formatUptime(uptimeSeconds)} mono />
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>RAM usage (MB)</div>
        <div style={styles.perfGraphWrap}>
          <div style={styles.perfYAxis}>
            <div>{Math.round(graphMaxMb)}</div>
            <div>{Math.round(graphMaxMb * 0.75)}</div>
            <div>{Math.round(graphMaxMb * 0.5)}</div>
            <div>{Math.round(graphMaxMb * 0.25)}</div>
            <div>0</div>
          </div>
          <div style={styles.perfGraph}>
            {[25, 50, 75].map((level) => (
              <div key={level} style={{ ...styles.perfGuide, top: `${100 - level}%` }} />
            ))}
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={styles.perfLineSvg}>
            <defs>
              <linearGradient id="perf-line" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="rgba(56,189,248,0.95)" />
                <stop offset="100%" stopColor="rgba(192,132,252,0.95)" />
              </linearGradient>
            </defs>
            <polyline
              points={perfSamples
                .map((sample, idx) => {
                  const x = (idx / Math.max(1, perfSamples.length - 1)) * 100;
                  const y = 100 - Math.max(0, Math.min(100, (sample / graphMaxMb) * 100));
                  return `${x},${y}`;
                })
                .join(" ")}
              fill="none"
              stroke="url(#perf-line)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            </svg>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>Server directory</div>
        <div style={styles.monoBox}>{server.server_dir ?? "(unknown)"}</div>
      </div>
    </div>
  );
}

function parseLooseNumber(value: any): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const cleaned = value.trim().replace(/,/g, "");
    const direct = Number(cleaned);
    if (Number.isFinite(direct)) return direct;

    const match = cleaned.match(/-?\d+(?:\.\d+)?/);
    if (match) {
      const parsed = Number(match[0]);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function parseMemoryToMb(value: any): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) return value;
  if (typeof value !== "string") return null;

  const text = value.trim().toLowerCase().replace(/,/g, "");
  const m = text.match(/(-?\d+(?:\.\d+)?)\s*(b|bytes?|kb|kib|mb|mib|gb|gib|tb|tib)?/i);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n < 0) return null;
  const unit = (m[2] || "mb").toLowerCase();

  if (unit === "b" || unit === "byte" || unit === "bytes") return n / (1024 * 1024);
  if (unit === "kb" || unit === "kib") return n / 1024;
  if (unit === "mb" || unit === "mib") return n;
  if (unit === "gb" || unit === "gib") return n * 1024;
  if (unit === "tb" || unit === "tib") return n * 1024 * 1024;
  return null;
}

function pickCpuPercent(rt: any): number | null {
  const candidates = [
    rt?.cpu_percent,
    rt?.cpu_usage,
    rt?.cpu,
    rt?.process_cpu_percent,
    rt?.metrics?.cpu_percent,
    rt?.metrics?.cpu,
    rt?.performance?.cpu_percent,
    rt?.performance?.cpu,
    rt?.stats?.cpu,
  ];

  for (const value of candidates) {
    const parsed = parseLooseNumber(value);
    if (parsed == null) continue;
    return Math.max(0, Math.min(100, parsed));
  }

  const hist = [rt?.cpu_history, rt?.metrics?.cpu, rt?.performance?.cpu, rt?.history?.cpu].find((x) => Array.isArray(x));
  if (Array.isArray(hist) && hist.length > 0) {
    const last = [...hist].reverse().find((n: any) => typeof n === "number" && Number.isFinite(n));
    if (typeof last === "number") return Math.max(0, Math.min(100, last));
  }

  return null;
}

function pickRamMb(rt: any): number | null {
  const directMbCandidates = [
    rt?.ram_mb,
    rt?.ram_usage_mb,
    rt?.memory_mb,
    rt?.rss_mb,
    rt?.metrics?.ram_mb,
    rt?.metrics?.memory_mb,
    rt?.stats?.memory_mb,
  ];

  for (const value of directMbCandidates) {
    const parsed = parseMemoryToMb(value);
    if (parsed != null && parsed >= 16) return parsed;
    if (parsed != null && parsed >= 0 && parsed < 16 && !rt?.state) return parsed;
  }

  const bytesCandidates = [rt?.memory_bytes, rt?.rss_bytes, rt?.metrics?.memory_bytes, rt?.metrics?.rss_bytes];
  for (const value of bytesCandidates) {
    const parsed = parseLooseNumber(value);
    if (parsed == null || parsed < 0) continue;

    const asMb = parsed / (1024 * 1024);
    const asKbToMb = parsed / 1024;

    if (asMb >= 16) return asMb;
    if (asKbToMb >= 16) return asKbToMb;
  }

  const stringCandidates = [rt?.memory, rt?.mem, rt?.rss, rt?.metrics?.memory, rt?.stats?.memory];
  for (const value of stringCandidates) {
    const parsed = parseMemoryToMb(value);
    if (parsed != null && parsed >= 16) return parsed;
  }

  return null;
}

function pickRamUsedMb(rt: any): number | null {
  const candidates = [
    rt?.ram_used_mb,
    rt?.heap_used_mb,
    rt?.metrics?.ram_used_mb,
    rt?.metrics?.heap_used_mb,
    rt?.stats?.ram_used_mb,
  ];
  for (const v of candidates) {
    const parsed = parseMemoryToMb(v);
    if (parsed != null && parsed >= 0) return parsed;
  }
  // fallback to process/legacy RAM value
  return pickRamMb(rt);
}

function pickRamMaxMb(rt: any): number | null {
  const candidates = [
    rt?.ram_max_mb,
    rt?.heap_max_mb,
    rt?.metrics?.ram_max_mb,
    rt?.metrics?.heap_max_mb,
    rt?.stats?.ram_max_mb,
  ];
  for (const v of candidates) {
    const parsed = parseMemoryToMb(v);
    if (parsed != null && parsed > 0) return parsed;
  }
  return null;
}


function buildPerfSamples(rt: any): number[] {
  const candidates = [
    rt?.ram_used_history,
    rt?.memory_history,
    rt?.metrics?.ram_used,
    rt?.metrics?.memory_used,
    rt?.history?.ram_used_mb,
  ];
  for (const c of candidates) {
    if (!Array.isArray(c)) continue;
    const nums = c
      .map((n: any) => parseMemoryToMb(n))
      .filter((n): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0)
      .slice(-24);
    if (nums.length > 0) return nums;
  }
  const current = parseMemoryToMb(rt?.ram_used_mb) ?? parseMemoryToMb(rt?.memory_mb) ?? parseMemoryToMb(rt?.ram_process_mb) ?? 0;
  return new Array(24).fill(Math.max(0, current));
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
