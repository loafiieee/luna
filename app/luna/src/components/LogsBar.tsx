import type { LogItem } from "../lib/types";
import { btn, levelColor, nowTime } from "./ui";
import { styles } from "../styles/styles";

export function LogsBar({
  open,
  onToggle,
  onClear,
  logs,
  endRef,
}: {
  open: boolean;
  onToggle: () => void;
  onClear: () => void;
  logs: LogItem[];
  endRef: React.RefObject<HTMLDivElement | null>;
}) {
  const drawerHeight = open ? "var(--logs-open-height)" : 0;

  return (
    <div style={styles.logsWrap}>
      <div style={styles.logsBar} onClick={onToggle} role="button">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={styles.logsHandle} />
          <div style={{ fontWeight: 900 }}>Logs</div>
          <div style={{ opacity: 0.65, fontSize: 12 }}>{logs.length ? `${logs.length} event(s)` : "No logs yet"}</div>
        </div>
        <div style={{ opacity: 0.7, fontWeight: 800 }}>{open ? "▼" : "▲"}</div>
      </div>

      <div
        className="logs-drawer-shell"
        style={{
          ...styles.logsDrawer,
          height: drawerHeight,
          borderTop: open ? "1px solid rgba(255,255,255,.10)" : "1px solid rgba(255,255,255,.06)",
        }}
      >
        {open && (
          <>
            <div style={styles.logsHeader}>
              <div style={{ opacity: 0.7, fontSize: 12 }}>Latest activity</div>
              <button
                style={btn("ghost")}
                onClick={(e) => {
                  e.stopPropagation();
                  onClear();
                }}
              >
                Clear
              </button>
            </div>

            <div style={styles.logsBody}>
              {logs.length === 0 ? (
                <div style={{ opacity: 0.7 }}>No logs yet.</div>
              ) : (
                logs.map((l, idx) => (
                  <div key={idx} style={styles.logRow}>
                    <div style={styles.logTime}>{nowTime(l.t)}</div>
                    <div style={{ ...styles.logLevel, color: levelColor(l.level) }}>{l.level.toUpperCase()}</div>
                    <div style={styles.logMsg}>{l.msg}</div>
                  </div>
                ))
              )}
              <div ref={endRef} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
