import { Dispatch, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { invoke } from "@tauri-apps/api/core";
import { openPath } from "@tauri-apps/plugin-opener";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import type { DetailTab, ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";
import { isServerOnline, playersList } from "../lib/serverRuntime";
import { cli } from "../lib/cli";

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

  useEffect(() => {
    if (!copiedAddress) return;
    const id = window.setTimeout(() => setCopiedAddress(false), 1800);
    return () => window.clearTimeout(id);
  }, [copiedAddress]);

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
          {tab === "content" && <ContentPane server={server} addLog={addLog} />}
          {tab === "backups" && <BackupsPane server={server} addLog={addLog} />}
          {tab === "tunnels" && <TunnelsPane server={server} addLog={addLog} onLiveRefresh={onLiveRefresh} />}
          {tab === "settings" && <SettingsPane server={server} addLog={addLog} />}
          {tab === "server_folder" && <ServerFolderPane server={server} addLog={addLog} />}
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
  // Keep a stable Y-axis so historical bars don't all resize every update.
  const configuredRamMb = typeof server.ram === "number" && Number.isFinite(server.ram) && server.ram > 0 ? server.ram : null;
  const graphMaxMb = Math.max(512, ramMaxMb ?? configuredRamMb ?? 0);

  return (
    <div>
      <div style={styles.paneTitle}>Details</div>

      <div style={styles.detailsMetricsGrid}>
        <KV k="CPU usage" v={cpuPercent != null ? `${cpuPercent.toFixed(1)}%` : "—"} />
        <KV k="RAM usage" v={ramUsedMb != null ? `${ramUsedMb.toFixed(0)}${ramMaxMb != null ? `/${ramMaxMb.toFixed(0)}` : ""} MB` : "—"} />
        <KV k="Server uptime" v={formatUptime(uptimeSeconds)} mono />
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={styles.smallLabel}>RAM usage over past minute (MB)</div>
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
            <div style={styles.perfBars}>
              {perfSamples.map((sample, idx) => {
                const h = Math.max(2, Math.min(100, (sample / graphMaxMb) * 100));
                const isLatest = idx === perfSamples.length - 1;
                return (
                  <div
                    key={idx}
                    style={{
                      ...styles.perfBar,
                      height: `${h}%`,
                      ...(isLatest ? styles.perfBarLatest : {}),
                    }}
                    title={`${sample.toFixed(0)} MB`}
                  />
                );
              })}
            </div>
          </div>
        </div>
        <div style={styles.perfMeta}>
          <span>60s ago</span>
          <span>Now</span>
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
      .slice(-30);
    if (nums.length > 0) return nums;
  }
  const current = parseMemoryToMb(rt?.ram_used_mb) ?? parseMemoryToMb(rt?.memory_mb) ?? parseMemoryToMb(rt?.ram_process_mb) ?? 0;
  return new Array(30).fill(Math.max(0, current));
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

function TunnelsPane({ server, addLog, onLiveRefresh }: { server: ServerInfo; addLog: ServerModalProps["addLog"]; onLiveRefresh: ServerModalProps["onLiveRefresh"] }) {
  const rt: any = server.runtime ?? {};
  const t: any = rt.tunnel ?? {};
  const [tunnelingEnabled, setTunnelingEnabled] = useState(Boolean(server.tunneling));
  const [stickyEnabled, setStickyEnabled] = useState(Boolean(server.sticky_address));
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    setTunnelingEnabled(Boolean(server.tunneling));
    setStickyEnabled(Boolean(server.sticky_address));
  }, [server.server_id, server.tunneling, server.sticky_address]);

  const tcp = typeof t.public_tcp_address === "string" ? t.public_tcp_address : null;
  const udp = typeof t.public_udp_address === "string" ? t.public_udp_address : null;
  const voice = typeof t.public_voice_address === "string" ? t.public_voice_address : null;

  const subdomain = typeof t.subdomain === "string" ? t.subdomain : null;
  const suffix = typeof t.domain_suffix === "string" ? t.domain_suffix : null;

  const primary = (server.edition === "bedrock" ? udp ?? tcp : tcp ?? udp) ?? "(none)";

  async function saveTunnelConfig() {
    try {
      setSaving(true);
      await cli(
        "set_tunnel_config",
        server.server_id,
        `--tunneling=${tunnelingEnabled ? "true" : "false"}`,
        `--sticky-address=${stickyEnabled ? "true" : "false"}`,
      );
      addLog("ok", `Tunnel settings saved for ${server.name}.`);
      if (server.running) {
        addLog("warn", "Server is running; settings will be fully applied on next start.");
      }
      onLiveRefresh();
    } catch (e: any) {
      addLog("err", `Failed to save tunnel settings: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  async function syncTunnelsNow() {
    try {
      setSyncing(true);
      await cli("sync_tunnels");
      addLog("ok", "Tunnel reservations synced.");
      onLiveRefresh();
    } catch (e: any) {
      addLog("err", `Failed to sync tunnel reservations: ${String(e)}`);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div>
      <div style={styles.paneTitle}>Tunnels</div>
      <div style={{ opacity: 0.75, marginTop: 6 }}>
        Public endpoints from runtime plus editable tunnel controls.
      </div>

      <div style={{ ...styles.contentItem, marginTop: 12, marginBottom: 10 }}>
        <div style={{ minWidth: 0, flex: 1, display: "grid", gap: 8 }}>
          <div style={styles.contentItemTitle}>Controls</div>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={tunnelingEnabled} onChange={(e) => setTunnelingEnabled(e.target.checked)} />
            <span>Enable tunneling</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={stickyEnabled} onChange={(e) => setStickyEnabled(e.target.checked)} />
            <span>Prefer sticky public address</span>
          </label>
        </div>
        <div style={{ display: "grid", gap: 6 }}>
          <button type="button" style={btn("primary")} disabled={saving} onClick={() => void saveTunnelConfig()}>{saving ? "Saving…" : "Save Tunnel Settings"}</button>
          <button type="button" style={btn("ghost")} disabled={syncing} onClick={() => void syncTunnelsNow()}>{syncing ? "Syncing…" : "Sync Reservations"}</button>
        </div>
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

type ContentTabKey = "primary" | "datapack" | "installed";

type ModrinthHit = {
  project_id: string;
  slug?: string;
  title?: string;
  description?: string;
  author?: string;
  versions?: string[];
  categories?: string[];
  display_categories?: string[];
  downloads?: number;
  icon_url?: string;
  client_side?: string;
  server_side?: string;
  project_type?: string;
};

function primaryContentTypeForServer(server: ServerInfo): "plugin" | "mod" {
  const platform = String(server.platform ?? "").toLowerCase();
  const modLoaders = ["fabric", "forge", "neoforge", "quilt"];
  if (modLoaders.some((loader) => platform.includes(loader))) return "mod";
  return "plugin";
}

function modrinthLoaderForServer(server: ServerInfo, projectType: "plugin" | "mod" | "datapack"): string | null {
  if (projectType === "datapack") return null;
  const platform = String(server.platform ?? "").toLowerCase();

  if (projectType === "mod") {
    if (platform.includes("neoforge")) return "neoforge";
    if (platform.includes("forge")) return "forge";
    if (platform.includes("quilt")) return "quilt";
    if (platform.includes("fabric")) return "fabric";
    return null;
  }

  if (platform.includes("paper") || platform.includes("purpur") || platform.includes("pufferfish")) return "paper";
  if (platform.includes("spigot")) return "spigot";
  if (platform.includes("bukkit")) return "bukkit";
  return null;
}

const MODRINTH_LOADER_TAGS = new Set([
  "paper",
  "folia",
  "spigot",
  "bukkit",
  "purpur",
  "pufferfish",
  "sponge",
  "velocity",
  "bungeecord",
  "waterfall",
  "fabric",
  "quilt",
  "forge",
  "neoforge",
]);

function normalizeCategories(hit: ModrinthHit): string[] {
  const preferred = Array.isArray(hit.display_categories) && hit.display_categories.length > 0 ? hit.display_categories : hit.categories;
  const cats = Array.isArray(preferred) ? preferred : [];
  return cats
    .filter((c): c is string => typeof c === "string" && c.trim().length > 0)
    .map((c) => c.trim())
    .filter((c) => !MODRINTH_LOADER_TAGS.has(c.toLowerCase()))
    .filter((c) => !/^\d+(?:\.\d+){1,3}$/.test(c));
}


function utf8ToBase64(input: string): string {
  const bytes = new TextEncoder().encode(input);
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary);
}

function ContentPane({ server, addLog }: { server: ServerInfo; addLog: ServerModalProps["addLog"] }) {
  type InstalledProject = {
    project_id: string;
    title: string;
    author?: string | null;
    icon_url?: string | null;
    description?: string | null;
    preferred_config_path?: string | null;
    files: string[];
    installed_at?: number | null;
  };

  const primaryType = primaryContentTypeForServer(server);
  const primaryLabel = primaryType === "mod" ? "Mods" : "Plugins";
  const [tab, setTab] = useState<ContentTabKey>("primary");
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [items, setItems] = useState<ModrinthHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ModrinthHit | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [installedByType, setInstalledByType] = useState<{ primary: InstalledProject[]; datapack: InstalledProject[] }>({ primary: [], datapack: [] });
  const [configPicker, setConfigPicker] = useState<{ projectType: "plugin" | "mod" | "datapack"; projectId: string; projectTitle: string; baseRelative?: string; manual?: boolean; candidates: Array<{ relative_path: string; reason?: string; score?: number }> } | null>(null);
  const [editorState, setEditorState] = useState<{ projectType: "plugin" | "mod" | "datapack"; projectId: string; projectTitle: string; relativePath: string; content: string; dirty: boolean; saving: boolean; fromManual: boolean; justSaved: boolean } | null>(null);
  const [preferredPrompt, setPreferredPrompt] = useState<{ projectType: "plugin" | "mod" | "datapack"; projectId: string; projectTitle: string; relativePath: string } | null>(null);

  const activeProjectType: "plugin" | "mod" | "datapack" = tab === "datapack" ? "datapack" : primaryType;
  const loader = modrinthLoaderForServer(server, activeProjectType);
  const gameVersion = typeof server.version === "string" && server.version.trim() ? server.version.trim() : null;

  useEffect(() => {
    setItems([]);
    setErr(null);
    setQuery("");
    setSelectedCategory("all");
    setSelectedItem(null);
  }, [tab, server.server_id]);

  async function refreshInstalled() {
    if (!server.folder) return;
    try {
      const [primaryRes, datapackRes] = await Promise.all([
        cli<any>("modrinth_list_installed", server.folder, `--project_type=${primaryType}`),
        cli<any>("modrinth_list_installed", server.folder, "--project_type=datapack"),
      ]);

      const mapRows = (rows: any[]) =>
        rows
          .filter((r) => r && typeof r.project_id === "string")
          .map((r) => ({
            project_id: String(r.project_id),
            title: String(r.title ?? r.project_id),
            author: typeof r.author === "string" ? r.author : null,
            icon_url: typeof r.icon_url === "string" ? r.icon_url : null,
            description: typeof r.description === "string" ? r.description : null,
            preferred_config_path: typeof r.preferred_config_path === "string" ? r.preferred_config_path : null,
            files: Array.isArray(r.files) ? r.files.map((f: any) => String(f)) : [],
            installed_at: typeof r.installed_at === "number" ? r.installed_at : null,
          }));

      setInstalledByType({
        primary: mapRows(Array.isArray(primaryRes?.data?.projects) ? primaryRes.data.projects : []),
        datapack: mapRows(Array.isArray(datapackRes?.data?.projects) ? datapackRes.data.projects : []),
      });
    } catch (e: any) {
      addLog("err", `Failed to load installed content: ${String(e)}`);
    }
  }

  const installedIds = useMemo(() => {
    if (activeProjectType === "datapack") return new Set(installedByType.datapack.map((x) => x.project_id));
    return new Set(installedByType.primary.map((x) => x.project_id));
  }, [activeProjectType, installedByType]);

  const categoryOptions = useMemo(() => {
    const all = new Set<string>();
    for (const item of items) {
      for (const c of normalizeCategories(item)) all.add(c);
    }
    return ["all", ...Array.from(all).sort((a, b) => a.localeCompare(b))];
  }, [items]);

  const shownItems = useMemo(() => {
    let out = items;
    if (selectedCategory !== "all") out = out.filter((item) => normalizeCategories(item).includes(selectedCategory));
    return out;
  }, [items, selectedCategory]);

  async function runSearch(searchText: string) {
    const trimmed = searchText.trim();
    try {
      setLoading(true);
      setErr(null);
      const args = ["modrinth_search", trimmed, `--project_type=${activeProjectType}`];
      if (loader) args.push(`--loader=${loader}`);
      if (gameVersion) args.push(`--game_version=${gameVersion}`);
      if (selectedCategory !== "all") args.push(`--category=${selectedCategory}`);
      const res = await cli<any>(...args);
      const hits = Array.isArray(res?.data?.hits) ? res.data.hits : [];
      setItems(hits);
      addLog("ok", `Found ${hits.length} ${activeProjectType} result(s) on Modrinth.`);
    } catch (e: any) {
      const msg = String(e);
      setErr(msg);
      setItems([]);
      addLog("err", `Modrinth search failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshInstalled();
    if (tab !== "installed") void runSearch("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, server.server_id, primaryType]);

  useEffect(() => {
    if (tab === "installed" || selectedCategory === "all") return;
    void runSearch(query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCategory]);

  async function installProject(projectId: string) {
    if (!server.folder) return addLog("err", "Cannot install content: server folder is unavailable.");
    if (installedIds.has(projectId)) return addLog("warn", "Already installed.");

    try {
      setInstallingId(projectId);
      const args = ["modrinth_download", server.folder, projectId, `--project_type=${activeProjectType}`];
      if (loader) args.push(`--loader=${loader}`);
      if (gameVersion) args.push(`--game_version=${gameVersion}`);
      const res = await cli<any>(...args);
      if (Boolean(res?.data?.already_installed)) addLog("warn", `"${projectId}" is already installed.`);
      else addLog("ok", `Installed ${Number(res?.data?.count ?? 0)} file(s) from ${projectId}.`);
      await refreshInstalled();
    } catch (e: any) {
      addLog("err", `Install failed for ${projectId}: ${String(e)}`);
    } finally {
      setInstallingId(null);
    }
  }

  async function uninstallProject(projectType: "plugin" | "mod" | "datapack", projectId: string) {
    if (!server.folder) return;
    try {
      const key = `${projectType}:${projectId}`;
      setDeletingId(key);
      await cli("modrinth_uninstall_project", server.folder, projectType, projectId);
      addLog("ok", `Uninstalled ${projectId}.`);
      await refreshInstalled();
    } catch (e: any) {
      addLog("err", `Uninstall failed for ${projectId}: ${String(e)}`);
    } finally {
      setDeletingId(null);
    }
  }

  async function openConfigFile(projectType: "plugin" | "mod" | "datapack", projectId: string, projectTitle: string, relPath: string, fromManual = false) {
    if (!server.folder) return;
    try {
      const res = await cli<any>("read_server_text_file", server.folder, relPath);
      setEditorState({ projectType, projectId, projectTitle, relativePath: relPath, content: String(res?.data?.content ?? ""), dirty: false, saving: false, fromManual, justSaved: false });
      setConfigPicker(null);
    } catch (e: any) {
      addLog("err", `Could not open config file: ${String(e)}`);
    }
  }

  async function openConfigPicker(projectType: "plugin" | "mod" | "datapack", projectId: string, projectTitle: string) {
    if (!server.folder) return;
    try {
      const res = await cli<any>("modrinth_config_candidates", server.folder, projectType, projectId);
      const preferred = typeof res?.data?.preferred_config_path === "string" ? res.data.preferred_config_path : null;
      if (preferred) {
        await openConfigFile(projectType, projectId, projectTitle, preferred, false);
        return;
      }
      const cands = Array.isArray(res?.data?.candidates) ? res.data.candidates : [];
      if (cands.length === 0) {
        addLog("warn", `Could not auto-detect config for ${projectTitle}. Please choose a file manually.`);
        const browse = await cli<any>("modrinth_browse_config_files", server.folder, projectType);
        const files = Array.isArray(browse?.data?.files) ? browse.data.files : [];
        const baseRelative = typeof browse?.data?.base_relative === "string" ? browse.data.base_relative : undefined;
        if (files.length === 0) {
          addLog("warn", `No editable config files found under ${baseRelative ?? "the expected config directory"}.`);
          return;
        }
        setConfigPicker({
          projectType,
          projectId,
          projectTitle,
          baseRelative,
          manual: true,
          candidates: files.map((c: any) => ({ relative_path: String(c.relative_path) })),
        });
        return;
      }
      if (cands.length === 1) {
        await openConfigFile(projectType, projectId, projectTitle, String(cands[0].relative_path), false);
        return;
      }
      setConfigPicker({ projectType, projectId, projectTitle, candidates: cands.map((c: any) => ({ relative_path: String(c.relative_path), reason: c.reason, score: c.score })) });
    } catch (e: any) {
      addLog("err", `Failed to find config files: ${String(e)}`);
    }
  }

  async function saveEditor() {
    if (!editorState || !server.folder) return;
    try {
      setEditorState((prev) => (prev ? { ...prev, saving: true } : prev));
      const encoded = utf8ToBase64(editorState.content);
      await cli("write_server_text_file", server.folder, editorState.relativePath, encoded);
      setEditorState((prev) => (prev ? { ...prev, saving: false, dirty: false, justSaved: true } : prev));
      addLog("ok", `Saved ${editorState.relativePath}.`);
    } catch (e: any) {
      setEditorState((prev) => (prev ? { ...prev, saving: false } : prev));
      addLog("err", `Failed saving file: ${String(e)}`);
    }
  }

  async function setPreferredConfig(projectType: "plugin" | "mod" | "datapack", projectId: string, projectTitle: string, relativePath: string) {
    if (!server.folder) return;
    try {
      await cli("modrinth_set_preferred_config", server.folder, projectType, projectId, relativePath);
      addLog("ok", `Saved preferred config file for ${projectTitle}.`);
      await refreshInstalled();
    } catch (e: any) {
      addLog("err", `Failed to save preferred config file: ${String(e)}`);
    }
  }

  function closeEditor() {
    if (!editorState) return;
    if (editorState.dirty) {
      addLog("warn", "Please save or discard your config changes before closing.");
      return;
    }
    if (editorState.fromManual) {
      setPreferredPrompt({
        projectType: editorState.projectType,
        projectId: editorState.projectId,
        projectTitle: editorState.projectTitle,
        relativePath: editorState.relativePath,
      });
    }
    setEditorState(null);
  }

  function renderInstalledSection(label: string, projectType: "plugin" | "mod" | "datapack", rows: InstalledProject[]) {
    return (
      <>
        <div style={styles.contentSectionTitle}>{label}</div>
        {rows.length === 0 ? (
          <div style={styles.playersEmpty}>No installed {label.toLowerCase()}.</div>
        ) : (
          rows.map((row) => {
            const key = `${projectType}:${row.project_id}`;
            const icon = row.icon_url || null;
            return (
              <div key={key} style={styles.contentItem}>
                <div style={styles.contentThumbWrap}>{icon ? <img src={icon} alt="project" style={styles.contentThumb} /> : <div style={styles.contentThumbPlaceholder}>?</div>}</div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={styles.contentItemTitle}>{row.title || row.project_id}</div>
                  <div style={styles.contentItemMeta}>{row.author ? `by ${row.author} • ` : ""}{row.files.length} file(s)</div>
                  <div style={styles.contentItemDesc}>{row.description || row.project_id}</div>
                </div>
                <div style={{ display: "grid", gap: 6 }}>
                  <button type="button" style={btn("ghost")} onClick={() => void openConfigPicker(projectType, row.project_id, row.title || row.project_id)}>{row.preferred_config_path ? "Config (preferred)" : "Config"}</button>
                  <button type="button" style={btn("danger")} disabled={deletingId === key} onClick={() => void uninstallProject(projectType, row.project_id)}>{deletingId === key ? "Deleting…" : "Delete"}</button>
                </div>
              </div>
            );
          })
        )}
      </>
    );
  }

  return (
    <div>
      <div style={styles.paneTitle}>Content</div>
      <div style={styles.contentTabRow}>
        <button type="button" style={{ ...styles.contentTabBtn, ...(tab === "primary" ? styles.contentTabBtnActive : {}) }} onClick={() => setTab("primary")}>{primaryLabel}</button>
        <button type="button" style={{ ...styles.contentTabBtn, ...(tab === "datapack" ? styles.contentTabBtnActive : {}) }} onClick={() => setTab("datapack")}>Datapacks</button>
        <button type="button" style={{ ...styles.contentTabBtn, ...(tab === "installed" ? styles.contentTabBtnActive : {}) }} onClick={() => setTab("installed")}>Installed</button>
      </div>

      <div style={styles.contentMeta}>{tab === "installed" ? "Manage installed content and configs." : `Showing ${activeProjectType}s relevant to this server${loader ? ` • loader: ${loader}` : ""}${gameVersion ? ` • MC ${gameVersion}` : ""}`}</div>

      {tab !== "installed" && (
        <>
          <div style={styles.contentSearchRow}>
            <input style={styles.search} placeholder={`Search ${activeProjectType}s on Modrinth…`} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void runSearch(query); } }} />
            <button type="button" style={btn("primary")} onClick={() => void runSearch(query)} disabled={loading}>{loading ? "Searching…" : "Search"}</button>
          </div>
          <div style={styles.contentSearchRow}>
            <select style={styles.contentSelect} value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}>
              {categoryOptions.map((cat) => <option key={cat} value={cat}>{cat === "all" ? "All categories" : cat}</option>)}
            </select>
          </div>
          {err && <div style={styles.consoleError}>Search error: {err}</div>}
          <div style={styles.contentResults}>
            {shownItems.length === 0 ? <div style={styles.playersEmpty}>{loading ? "Loading…" : "No results found for this server/version."}</div> : shownItems.map((item) => {
              const id = String(item.project_id ?? "");
              const title = item.title || id;
              const installing = installingId === id;
              const isInstalled = installedIds.has(id);
              const icon = typeof item.icon_url === "string" ? item.icon_url : null;
              return (
                <div key={id} style={styles.contentItemBtn} onClick={() => setSelectedItem(item)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedItem(item); } }}>
                  <div style={styles.contentItem}>
                    <div style={styles.contentThumbWrap}>{icon ? <img src={icon} alt="project" style={styles.contentThumb} /> : <div style={styles.contentThumbPlaceholder}>?</div>}</div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={styles.contentItemTitle}>{title}</div>
                      <div style={styles.contentItemMeta}>by {item.author ?? "unknown"} • {Number(item.downloads ?? 0).toLocaleString()} downloads</div>
                      <div style={styles.contentItemDesc}>{item.description ?? "No description."}</div>
                    </div>
                    <button type="button" style={btn(isInstalled ? "ghost" : "primary")} onClick={(e) => { e.stopPropagation(); if (!isInstalled) void installProject(id); }} disabled={installing || !id || isInstalled}>{isInstalled ? "Installed" : installing ? "Installing…" : "Install"}</button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {tab === "installed" && (
        <div style={styles.contentResults}>
          {renderInstalledSection(primaryLabel, primaryType, installedByType.primary)}
          {renderInstalledSection("Datapacks", "datapack", installedByType.datapack)}
        </div>
      )}

      {selectedItem && tab !== "installed" && (
        <div style={styles.contentOverlay} onClick={() => setSelectedItem(null)}>
          <div style={styles.contentModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.contentModalHead}>
              <div style={{ fontWeight: 900 }}>{selectedItem.title ?? selectedItem.project_id}</div>
              <button type="button" style={btn("ghost")} onClick={() => setSelectedItem(null)}>Close</button>
            </div>
            <div style={styles.contentModalBody}>
              {selectedItem.icon_url ? <img src={selectedItem.icon_url} alt="project" style={styles.contentModalImage} /> : null}
              <div style={styles.contentItemDesc}>{selectedItem.description ?? "No description."}</div>
              <div style={styles.contentItemMeta}>Author: {selectedItem.author ?? "unknown"}</div>
              <div style={styles.contentItemMeta}>Downloads: {Number(selectedItem.downloads ?? 0).toLocaleString()}</div>
              <div style={styles.contentItemMeta}>Categories: {normalizeCategories(selectedItem).join(", ") || "—"}</div>
              <div style={styles.contentItemMeta}>Versions: {Array.isArray(selectedItem.versions) ? selectedItem.versions.join(", ") : "—"}</div>
            </div>
            <div style={styles.contentModalActions}>
              <button type="button" style={btn(installedIds.has(String(selectedItem.project_id ?? "")) ? "ghost" : "primary")} onClick={() => { const pid = String(selectedItem.project_id ?? ""); if (!installedIds.has(pid)) void installProject(pid); }} disabled={installingId === String(selectedItem.project_id ?? "") || !selectedItem.project_id || installedIds.has(String(selectedItem.project_id ?? ""))}>{installedIds.has(String(selectedItem.project_id ?? "")) ? "Installed" : installingId === String(selectedItem.project_id ?? "") ? "Installing…" : "Install"}</button>
            </div>
          </div>
        </div>
      )}

      {configPicker && (
        <div style={styles.contentOverlay} onClick={() => setConfigPicker(null)}>
          <div style={styles.contentModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.contentModalHead}>
              <div style={{ fontWeight: 900 }}>{configPicker.manual ? `Config file picker — ${configPicker.projectTitle}` : `Choose config file — ${configPicker.projectTitle}`}</div>
              <button type="button" style={btn("ghost")} onClick={() => setConfigPicker(null)}>Close</button>
            </div>
            <div style={styles.contentModalBody}>
              {configPicker.manual && <div style={styles.contentItemMeta}>Could not auto-detect config. Select a file from {configPicker.baseRelative ?? "the expected directory"}.</div>}
              {configPicker.candidates.map((c) => (
                <button key={c.relative_path} type="button" style={styles.contentPickerBtn} onClick={() => void openConfigFile(configPicker.projectType, configPicker.projectId, configPicker.projectTitle, c.relative_path, Boolean(configPicker.manual))}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={styles.contentItemTitle}>{c.relative_path}</div>
                    <div style={styles.contentItemMeta}>{c.reason ?? "match"}{typeof c.score === "number" ? ` • score ${c.score}` : ""}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {editorState && (
        <div style={styles.contentOverlay} onClick={() => { void closeEditor(); }}>
          <div style={styles.contentModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.contentModalHead}>
              <div style={{ fontWeight: 900 }}>Edit config — {editorState.projectTitle}</div>
              <button type="button" style={btn("ghost")} onClick={() => { void closeEditor(); }} disabled={editorState.dirty || editorState.saving}>Close</button>
            </div>
            <div style={styles.contentModalBody}>
              <div style={styles.contentItemMeta}>{editorState.relativePath}</div>
              {editorState.justSaved && <div style={styles.contentSaveOk}>Saved.</div>}
              <textarea
                style={styles.configEditorArea}
                value={editorState.content}
                onChange={(e) => setEditorState((prev) => (prev ? { ...prev, content: e.target.value, dirty: true, justSaved: false } : prev))}
              />
            </div>
            <div style={styles.contentModalActions}>
              <button type="button" style={btn("primary")} disabled={!editorState.dirty || editorState.saving} onClick={() => void saveEditor()}>{editorState.saving ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
      {preferredPrompt && (
        <div style={styles.contentOverlay} onClick={() => setPreferredPrompt(null)}>
          <div style={styles.contentModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.contentModalHead}>
              <div style={{ fontWeight: 900 }}>Use this config file by default?</div>
              <button type="button" style={btn("ghost")} onClick={() => setPreferredPrompt(null)}>Close</button>
            </div>
            <div style={styles.contentModalBody}>
              <div style={styles.contentItemDesc}>Always use this config file for <strong>{preferredPrompt.projectTitle}</strong>?</div>
              <div style={styles.contentItemMeta}>{preferredPrompt.relativePath}</div>
            </div>
            <div style={styles.contentModalActions}>
              <button type="button" style={btn("ghost")} onClick={() => setPreferredPrompt(null)}>Not now</button>
              <button
                type="button"
                style={btn("primary")}
                onClick={() => {
                  const p = preferredPrompt;
                  setPreferredPrompt(null);
                  if (p) void setPreferredConfig(p.projectType, p.projectId, p.projectTitle, p.relativePath);
                }}
              >
                Always use this file
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}


function BackupsPane({ server, addLog }: { server: ServerInfo; addLog: ServerModalProps["addLog"] }) {
  const [items, setItems] = useState<Array<{ backup_id: string; created_at?: string | null; label?: string | null; size_bytes?: number; file_count?: number }>>([]);
  const [schedule, setSchedule] = useState<{ enabled: boolean; interval_minutes: number; keep_latest: number; label_prefix: string; next_run_at?: string | null; last_run_at?: string | null; last_error?: string | null } | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [runningScheduleNow, setRunningScheduleNow] = useState(false);
  const [label, setLabel] = useState("");
  const [confirmAction, setConfirmAction] = useState<{ type: "restore" | "delete"; backupId: string; backupLabel: string } | null>(null);

  async function refreshBackups() {
    try {
      setLoading(true);
      const [res, scheduleRes] = await Promise.all([
        cli<any>("backup_list", server.server_id),
        cli<any>("backup_schedule_get", server.server_id),
      ]);
      const rows = Array.isArray(res?.data?.backups) ? res.data.backups : [];
      setItems(rows);
      setSchedule(scheduleRes?.data?.schedule ?? null);
    } catch (e: any) {
      addLog("err", `Failed to load backups: ${String(e)}`);
      setItems([]);
      setSchedule(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshBackups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [server.server_id]);

  async function createBackup() {
    try {
      setCreating(true);
      const args = ["backup_create", server.server_id];
      if (label.trim()) args.push(`--label=${label.trim()}`);
      await cli<any>(...args);
      setLabel("");
      addLog("ok", `Backup created for ${server.name}.`);
      await refreshBackups();
    } catch (e: any) {
      addLog("err", `Backup creation failed: ${String(e)}`);
    } finally {
      setCreating(false);
    }
  }

  async function restoreBackup(backupId: string) {
    try {
      setBusyId(`restore:${backupId}`);
      const res = await cli<any>("backup_restore", server.server_id, backupId);
      if (Boolean(res?.data?.auto_stopped)) {
        addLog("warn", `Server was running and was stopped automatically before restore.`);
      }
      addLog("ok", `Backup ${backupId} restored.`);
    } catch (e: any) {
      addLog("err", `Restore failed for ${backupId}: ${String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteBackup(backupId: string) {
    try {
      setBusyId(`delete:${backupId}`);
      await cli("backup_delete", server.server_id, backupId);
      addLog("ok", `Backup ${backupId} deleted.`);
      await refreshBackups();
    } catch (e: any) {
      addLog("err", `Delete failed for ${backupId}: ${String(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function saveSchedule() {
    if (!schedule) return;
    try {
      setSavingSchedule(true);
      await cli(
        "backup_schedule_set",
        server.server_id,
        `--enabled=${schedule.enabled ? "true" : "false"}`,
        `--interval-minutes=${Math.max(5, Number(schedule.interval_minutes) || 60)}`,
        `--keep-latest=${Math.max(1, Number(schedule.keep_latest) || 10)}`,
        `--label-prefix=${(schedule.label_prefix || "Scheduled").trim() || "Scheduled"}`,
      );
      addLog("ok", `Scheduled backups updated for ${server.name}.`);
      await refreshBackups();
    } catch (e: any) {
      addLog("err", `Failed to save backup schedule: ${String(e)}`);
    } finally {
      setSavingSchedule(false);
    }
  }

  async function runScheduledNow() {
    try {
      setRunningScheduleNow(true);
      const res = await cli<any>("backup_schedule_run", server.server_id);
      if (res?.data?.ran) addLog("ok", "Scheduled backup created now.");
      else addLog("info", `Scheduled backup did not run (${String(res?.data?.reason || "not due")}).`);
      await refreshBackups();
    } catch (e: any) {
      addLog("err", `Failed to run scheduled backup: ${String(e)}`);
    } finally {
      setRunningScheduleNow(false);
    }
  }

  return (
    <div>
      <div style={styles.paneTitle}>Backups</div>
      <div style={styles.contentMeta}>Create, restore, and delete snapshots for this server. Restore will automatically stop a running server first.</div>

      <div style={styles.contentSearchRow}>
        <input style={styles.search} placeholder="Optional backup label…" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button type="button" style={btn("primary")} disabled={creating} onClick={() => void createBackup()}>{creating ? "Creating…" : "Create Backup"}</button>
        <button type="button" style={btn("ghost")} disabled={loading} onClick={() => void refreshBackups()}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      <div style={{ ...styles.contentItem, marginBottom: 10, alignItems: "end" }}>
        <div style={{ minWidth: 0, flex: 1, display: "grid", gap: 8 }}>
          <div style={styles.contentItemTitle}>Scheduled backups</div>
          <div style={styles.contentItemMeta}>Enable automatic backups with retention cleanup.</div>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={Boolean(schedule?.enabled)}
              onChange={(e) => setSchedule((s) => ({ ...(s ?? { interval_minutes: 60, keep_latest: 10, label_prefix: "Scheduled" }), enabled: e.target.checked } as any))}
            />
            <span>Enabled</span>
          </label>
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))" }}>
            <input
              style={styles.search}
              type="number"
              min={5}
              value={schedule?.interval_minutes ?? 60}
              onChange={(e) => setSchedule((s) => ({ ...(s ?? { enabled: false, keep_latest: 10, label_prefix: "Scheduled" }), interval_minutes: Number(e.target.value) || 60 } as any))}
              placeholder="Interval (minutes)"
            />
            <input
              style={styles.search}
              type="number"
              min={1}
              value={schedule?.keep_latest ?? 10}
              onChange={(e) => setSchedule((s) => ({ ...(s ?? { enabled: false, interval_minutes: 60, label_prefix: "Scheduled" }), keep_latest: Number(e.target.value) || 10 } as any))}
              placeholder="Keep latest"
            />
            <input
              style={styles.search}
              value={schedule?.label_prefix ?? "Scheduled"}
              onChange={(e) => setSchedule((s) => ({ ...(s ?? { enabled: false, interval_minutes: 60, keep_latest: 10 }), label_prefix: e.target.value } as any))}
              placeholder="Label prefix"
            />
          </div>
          {schedule?.next_run_at && <div style={styles.contentItemMeta}>Next run: {new Date(schedule.next_run_at).toLocaleString()}</div>}
          {schedule?.last_run_at && <div style={styles.contentItemMeta}>Last run: {new Date(schedule.last_run_at).toLocaleString()}</div>}
          {schedule?.last_error && <div style={{ ...styles.contentItemMeta, color: "#ff9a9a" }}>Last error: {schedule.last_error}</div>}
        </div>
        <div style={{ display: "grid", gap: 6 }}>
          <button type="button" style={btn("primary")} disabled={savingSchedule || !schedule} onClick={() => void saveSchedule()}>{savingSchedule ? "Saving…" : "Save Schedule"}</button>
          <button type="button" style={btn("ghost")} disabled={runningScheduleNow} onClick={() => void runScheduledNow()}>{runningScheduleNow ? "Running…" : "Run Due Now"}</button>
        </div>
      </div>

      <div style={styles.contentResults}>
        {items.length === 0 ? (
          <div style={styles.playersEmpty}>{loading ? "Loading backups…" : "No backups yet."}</div>
        ) : (
          items.map((b) => {
            const restoreBusy = busyId === `restore:${b.backup_id}`;
            const deleteBusy = busyId === `delete:${b.backup_id}`;
            const created = b.created_at ? new Date(b.created_at).toLocaleString() : b.backup_id;
            const sizeMb = typeof b.size_bytes === "number" ? `${(b.size_bytes / (1024 * 1024)).toFixed(2)} MB` : "—";
            const displayLabel = b.label?.trim() || b.backup_id;
            return (
              <div key={b.backup_id} style={styles.contentItem}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={styles.contentItemTitle}>{displayLabel}</div>
                  <div style={styles.contentItemMeta}>{created} • {sizeMb} • {typeof b.file_count === "number" ? `${b.file_count} files` : "file count unknown"}</div>
                </div>
                <div style={{ display: "grid", gap: 6 }}>
                  <button type="button" style={btn("ghost")} disabled={restoreBusy || deleteBusy} onClick={() => setConfirmAction({ type: "restore", backupId: b.backup_id, backupLabel: displayLabel })}>{restoreBusy ? "Restoring…" : "Restore"}</button>
                  <button type="button" style={btn("danger")} disabled={restoreBusy || deleteBusy} onClick={() => setConfirmAction({ type: "delete", backupId: b.backup_id, backupLabel: displayLabel })}>{deleteBusy ? "Deleting…" : "Delete"}</button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {confirmAction && (
        <div style={styles.contentOverlay} onClick={() => setConfirmAction(null)}>
          <div style={styles.contentModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.contentModalHead}>
              <div style={{ fontWeight: 900 }}>{confirmAction.type === "restore" ? "Restore backup?" : "Delete backup?"}</div>
              <button type="button" style={btn("ghost")} onClick={() => setConfirmAction(null)}>Close</button>
            </div>
            <div style={styles.contentModalBody}>
              <div style={styles.contentItemDesc}>{confirmAction.backupLabel}</div>
              <div style={styles.contentItemMeta}>
                {confirmAction.type === "restore"
                  ? "Current server files will be replaced. If running, the server will be stopped automatically before restore."
                  : "This backup archive and metadata will be removed permanently."}
              </div>
            </div>
            <div style={styles.contentModalActions}>
              <button type="button" style={btn("ghost")} onClick={() => setConfirmAction(null)}>Cancel</button>
              <button
                type="button"
                style={btn(confirmAction.type === "restore" ? "primary" : "danger")}
                onClick={() => {
                  const action = confirmAction;
                  setConfirmAction(null);
                  if (!action) return;
                  if (action.type === "restore") void restoreBackup(action.backupId);
                  else void deleteBackup(action.backupId);
                }}
              >
                {confirmAction.type === "restore" ? "Restore" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


type ServerPropertyRow = {
  key: string;
  value: string;
};

function parseServerProperties(content: string): ServerPropertyRow[] {
  const rows: ServerPropertyRow[] = [];
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || line.startsWith("!")) continue;
    const idx = line.indexOf("=");
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1);
    if (!key) continue;
    rows.push({ key, value });
  }
  rows.sort((a, b) => a.key.localeCompare(b.key));
  return rows;
}

function serializeServerProperties(rows: ServerPropertyRow[]): string {
  return rows.map((r) => `${r.key}=${r.value}`).join("\n") + "\n";
}

function SettingsPane({ server, addLog }: { server: ServerInfo; addLog: ServerModalProps["addLog"] }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<ServerPropertyRow[]>([]);

  async function loadProperties() {
    try {
      setLoading(true);
      const res = await cli<any>("read_server_text_file", server.folder, "server.properties");
      const content = typeof res?.data?.content === "string" ? res.data.content : "";
      setRows(parseServerProperties(content));
    } catch (e: any) {
      addLog("err", `Failed to load server.properties: ${String(e)}`);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProperties();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [server.server_id]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.key.toLowerCase().includes(q) || r.value.toLowerCase().includes(q));
  }, [rows, query]);

  async function saveProperties() {
    try {
      setSaving(true);
      const content = serializeServerProperties(rows);
      const encoded = btoa(unescape(encodeURIComponent(content)));
      await cli("write_server_text_file", server.folder, "server.properties", encoded);
      addLog("ok", `Saved server.properties for ${server.name}.`);
      await loadProperties();
    } catch (e: any) {
      addLog("err", `Failed to save server.properties: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  function setValueByKey(key: string, nextValue: string) {
    setRows((curr) => curr.map((row) => (row.key === key ? { ...row, value: nextValue } : row)));
  }

  return (
    <div>
      <div style={styles.paneTitle}>Settings</div>
      <div style={styles.contentMeta}>Edit <code>server.properties</code> in a structured form.</div>

      <div style={styles.contentSearchRow}>
        <input style={styles.search} placeholder="Filter properties…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button type="button" style={btn("ghost")} onClick={() => void loadProperties()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
        <button type="button" style={btn("primary")} onClick={() => void saveProperties()} disabled={saving || loading}>{saving ? "Saving…" : "Save"}</button>
      </div>

      <div style={styles.contentResults}>
        {filtered.length === 0 ? (
          <div style={styles.playersEmpty}>{loading ? "Loading properties…" : "No properties match your filter."}</div>
        ) : (
          filtered.map((row) => (
            <div key={row.key} style={styles.contentItem}>
              <div style={{ minWidth: 180, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", fontWeight: 700 }}>{row.key}</div>
              <input
                style={{ ...styles.search, flex: 1 }}
                value={row.value}
                onChange={(e) => setValueByKey(row.key, e.target.value)}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ServerFolderPane({ server, addLog }: { server: ServerInfo; addLog: ServerModalProps["addLog"] }) {
  const [opening, setOpening] = useState(false);

  async function openServerFolder() {
    const target = server.server_dir || `servers/${server.folder}`;
    try {
      setOpening(true);
      await openPath(target);
      addLog("ok", `Opened server folder for ${server.name}.`);
    } catch (e: any) {
      addLog("err", `Failed to open server folder: ${String(e)}`);
    } finally {
      setOpening(false);
    }
  }

  return (
    <div>
      <div style={styles.paneTitle}>Server Folder</div>
      <div style={styles.contentMeta}>Open this server in your operating system file manager.</div>
      <div style={{ ...styles.contentItem, marginTop: 12 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={styles.contentItemTitle}>{server.server_dir || `servers/${server.folder}`}</div>
          <div style={styles.contentItemMeta}>Folder for {server.name}</div>
        </div>
        <button type="button" style={btn("primary")} onClick={() => void openServerFolder()} disabled={opening}>
          {opening ? "Opening…" : "Open Folder"}
        </button>
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
