import React from "react";
import type { LogItem } from "../lib/types";

export function iconUrlFromPath(iconPath?: string | null) {
  if (!iconPath) return null;
  // file:// conversion for Tauri v2
  // use convertFileSrc from @tauri-apps/api/core in the component that needs it
  return iconPath;
}

export function nowTime(ts: number) {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function levelColor(level: LogItem["level"]) {
  if (level === "ok") return "rgb(34,197,94)";
  if (level === "warn") return "rgb(245,158,11)";
  if (level === "err") return "rgb(239,68,68)";
  return "rgb(148,163,184)";
}

export function pill(text: string, tone: "ok" | "warn" | "muted") {
  const bg =
    tone === "ok" ? "rgba(34,197,94,.16)" : tone === "warn" ? "rgba(245,158,11,.16)" : "rgba(148,163,184,.14)";
  const fg =
    tone === "ok" ? "rgb(34,197,94)" : tone === "warn" ? "rgb(245,158,11)" : "rgb(148,163,184)";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "clamp(5px, .55vw, 7px) clamp(9px, .8vw, 11px)",
        borderRadius: 999,
        background: bg,
        color: fg,
        border: "1px solid rgba(255,255,255,.08)",
        fontSize: "clamp(11px, .72vw, 13px)",
        fontWeight: 800,
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: 999, background: fg, boxShadow: "0 0 0 2px rgba(0,0,0,.25)" }} />
      {text}
    </span>
  );
}

export function btn(kind: "primary" | "danger" | "ghost", size: "normal" | "icon" = "normal") {
  const base: React.CSSProperties = {
    borderRadius: "clamp(11px, .95vw, 15px)",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.06)",
    color: "rgba(255,255,255,.92)",
    fontWeight: 900,
    cursor: "pointer",
    userSelect: "none",
    transition: "transform 140ms ease, background 140ms ease, filter 140ms ease, box-shadow 160ms ease",
  };

  const padding = size === "icon" ? "clamp(9px, .85vw, 11px) clamp(11px, .95vw, 13px)" : "clamp(9px, .85vw, 11px) clamp(12px, 1vw, 15px)";
  const fontSize = size === "icon" ? "clamp(13px, .9vw, 15px)" : "clamp(12px, .8vw, 14px)";

  if (kind === "primary") {
    return {
      ...base,
      padding,
      fontSize,
      background: "linear-gradient(150deg, rgba(59,130,246,.34), rgba(56,189,248,.24))",
      border: "1px solid rgba(59,130,246,.40)",
      boxShadow: "0 8px 18px rgba(37,99,235,.18)",
    };
  }
  if (kind === "danger") {
    return {
      ...base,
      padding,
      fontSize,
      background: "linear-gradient(150deg, rgba(239,68,68,.28), rgba(248,113,113,.18))",
      border: "1px solid rgba(239,68,68,.34)",
    };
  }
  return { ...base, padding, fontSize, background: "rgba(255,255,255,.05)" };
}
