import { useEffect, useState } from "react";
import type { ServerInfo } from "../lib/types";
import { btn, pill } from "./ui";
import { styles } from "../styles/styles";
import { readServerIconDataUrl, serverIconUrl } from "../lib/serverRuntime";

export function ServerCard({
  index,
  server,
  onOpen,
  onStart,
  onStop,
  onlinePlayers,
  maxPlayers,
  actionBusy,
  isOnline,
}: {
  index: number;
  server: ServerInfo;
  onOpen: () => void;
  onStart: () => void;
  onStop: () => void;
  onlinePlayers: number | null;
  maxPlayers: string;
  actionBusy: boolean;
  isOnline: boolean;
}) {
  const icon = serverIconUrl(server);
  const defaultIcon = new URL("/default-server-icon.png", window.location.origin).toString();
  const resolvedSrc = icon ?? defaultIcon;
  const [imgSrc, setImgSrc] = useState(resolvedSrc);

  useEffect(() => {
    let cancelled = false;

    async function hydrateIcon() {
      setImgSrc(resolvedSrc);
      const dataUrl = await readServerIconDataUrl(server);
      if (!cancelled && dataUrl) {
        setImgSrc(dataUrl);
      }
    }

    void hydrateIcon();

    return () => {
      cancelled = true;
    };
  }, [resolvedSrc, server.server_id, server.server_dir]);

  return (
    <div className="server-card" style={{ ...styles.card, animationDelay: `${Math.min(index * 55, 420)}ms` }} onClick={onOpen}>
      <div style={styles.cardIconWrap}>
        <img
          className="server-card-icon"
          src={imgSrc}
          alt="server icon"
          style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated" }}
          onError={(e) => {
            if ((e.currentTarget as HTMLImageElement).src !== defaultIcon) {
              setImgSrc(defaultIcon);
            }
          }}
        />

        <div style={styles.cardIconShade} />
      </div>

      <div style={styles.cardBottom}>
        <div style={{ minWidth: 0 }}>
          <div style={styles.cardName}>{server.name}</div>
          <div style={styles.cardMetaRow}>
            {isOnline ? pill("Online", "ok") : pill("Offline", "muted")}
            {isOnline ? <span style={styles.playerHint}>{typeof onlinePlayers === "number" ? onlinePlayers : 0}/{maxPlayers}</span> : null}
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
