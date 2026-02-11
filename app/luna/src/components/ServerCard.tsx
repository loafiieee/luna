import type { ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";
import { serverIconUrl } from "../lib/serverRuntime";

export function ServerCard({
  server,
  onOpen,
  onStart,
  onStop,
  onlinePlayers,
  actionBusy,
  isOnline,
}: {
  server: ServerInfo;
  onOpen: () => void;
  onStart: () => void;
  onStop: () => void;
  onlinePlayers: number | null;
  actionBusy: boolean;
  isOnline: boolean;
}) {
  const icon = serverIconUrl(server);

  return (
    <div style={styles.card} onClick={onOpen}>
      <div style={styles.cardIconWrap}>
        <img
          src={icon ?? "/default-server-icon.png"}
          alt="server icon"
          style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated" }}
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = "/default-server-icon.png";
          }}
        />

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
          disabled={actionBusy}
        >
          {actionBusy ? "…" : isOnline ? "■" : "▶"}
        </button>
      </div>
    </div>
  );
}
