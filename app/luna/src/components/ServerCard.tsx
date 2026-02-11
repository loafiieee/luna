import { convertFileSrc } from "@tauri-apps/api/core";
import type { ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";

export function ServerCard({
  server,
  onOpen,
  onStart,
  onStop,
  onlinePlayers,
}: {
  server: ServerInfo;
  onOpen: () => void;
  onStart: () => void;
  onStop: () => void;
  onlinePlayers: number | null;
}) {
  const isOnline = !!server.running;
  const derivedIconPath =
    server.icon_path ||
    (server.server_dir ? `${server.server_dir}/server-icon.png` : null) ||
    (server.server_dir ? `${server.server_dir}/icon.png` : null);
  const icon = derivedIconPath ? convertFileSrc(derivedIconPath) : null;

  return (
    <div style={styles.card} onClick={onOpen}>
      <div style={styles.cardIconWrap}>
        {icon ? (
          <img
            src={icon}
            alt="server icon"
            style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated" }}
          />
        ) : (
          <div style={styles.cardIconPlaceholder}>
            <div style={{ fontWeight: 900, opacity: 0.85 }}>{server.platform}</div>
            <div style={{ fontSize: 12, opacity: 0.7 }}>{server.version}</div>
          </div>
        )}
        <div style={styles.cardIconShade} />
      </div>

      <div style={styles.cardBottom}>
        <div style={{ minWidth: 0 }}>
          <div style={styles.cardName}>{server.name}</div>
          <div style={styles.cardMetaRow}>
            {isOnline ? pill("Online", "ok") : pill("Offline", "muted")}
            {isOnline && typeof onlinePlayers === "number" ? (
              <span style={styles.playerHint}>{onlinePlayers} player{onlinePlayers === 1 ? "" : "s"}</span>
            ) : null}
          </div>
        </div>

        <button
          style={btn(isOnline ? "danger" : "primary", "icon")}
          onClick={(e) => {
            e.stopPropagation();
            isOnline ? onStop() : onStart();
          }}
          title={isOnline ? "Stop" : "Start"}
        >
          {isOnline ? "■" : "▶"}
        </button>
      </div>
    </div>
  );
}
