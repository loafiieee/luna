import type React from "react";

export const styles: Record<string, React.CSSProperties> = {
  app: {
    minHeight: "100vh",
    paddingBottom: 44,
    color: "rgba(255,255,255,.92)",
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
    background:
      "radial-gradient(1200px 700px at 10% 0%, rgba(59,130,246,.16), transparent 60%), radial-gradient(900px 600px at 100% 10%, rgba(168,85,247,.12), transparent 55%), #070A12",
  },

  topChrome: {
    maxWidth: 1200,
    margin: "0 auto",
    padding: "18px 18px 6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },

  brandDot: {
    width: 14,
    height: 14,
    borderRadius: 999,
    background: "linear-gradient(135deg, rgba(59,130,246,1), rgba(168,85,247,1))",
    boxShadow: "0 0 0 6px rgba(255,255,255,.03)",
  },

  brandTitle: { fontSize: 18, fontWeight: 950, letterSpacing: 0.2 },
  brandSub: { fontSize: 12, opacity: 0.65, marginTop: 2 },

  errorBox: {
    maxWidth: 1200,
    margin: "8px auto 0",
    padding: 12,
    borderRadius: 16,
    background: "rgba(239,68,68,.12)",
    border: "1px solid rgba(239,68,68,.25)",
    color: "rgba(255,255,255,.92)",
    fontSize: 12,
  },

  grid: {
    maxWidth: 1200,
    margin: "10px auto 0",
    padding: "12px 18px 22px",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(270px, 1fr))",
    gap: 16,
  },

  empty: {
    gridColumn: "1 / -1",
    padding: 18,
    borderRadius: 18,
    border: "1px dashed rgba(255,255,255,.14)",
    background: "rgba(255,255,255,.04)",
  },

  // Card
  card: {
    borderRadius: 18,
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.05)",
    boxShadow: "0 18px 60px rgba(0,0,0,.45)",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    minHeight: 220,
  },

  cardIconWrap: {
    position: "relative",
    height: 140,
    background: "rgba(255,255,255,.06)",
  },

  cardIconShade: {
    position: "absolute",
    inset: 0,
    background: "linear-gradient(to bottom, rgba(0,0,0,.00), rgba(0,0,0,.55))",
    pointerEvents: "none",
  },

  cardIconPlaceholder: {
    width: "100%",
    height: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    background:
      "radial-gradient(500px 240px at 20% 10%, rgba(59,130,246,.30), transparent 60%), radial-gradient(500px 240px at 90% 20%, rgba(168,85,247,.22), transparent 60%), rgba(255,255,255,.04)",
    borderBottom: "1px solid rgba(255,255,255,.08)",
  },

  cardBottom: {
    padding: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },

  cardName: {
    fontSize: 15,
    fontWeight: 950,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  cardMetaRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginTop: 8,
  },

  playerHint: {
    opacity: 0.75,
    fontSize: 12,
    fontWeight: 800,
  },

  // Modal
  modal: {
    width: "min(1200px, 100%)",
    borderRadius: 22,
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(10,14,26,.92)",
    boxShadow: "0 30px 90px rgba(0,0,0,.70)",
    position: "relative",
  },

  modalTopBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: 14,
    background: "rgba(255,255,255,.05)",
    borderBottom: "1px solid rgba(255,255,255,.10)",
  },

  modalTopLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
    flex: 1,
  },

  modalIcon: {
    width: 44,
    height: 44,
    borderRadius: 14,
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.06)",
    flexShrink: 0,
  },

  modalIconPlaceholder: {
    width: "100%",
    height: "100%",
    display: "grid",
    placeItems: "center",
    fontWeight: 950,
    opacity: 0.75,
  },

  modalTitleRow: {
    display: "flex",
    alignItems: "center",
    minWidth: 0,
  },

  modalName: {
    fontSize: 16,
    fontWeight: 950,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  modalNameButton: {
    border: "none",
    background: "transparent",
    padding: 0,
    margin: 0,
    color: "rgba(255,255,255,.92)",
    fontSize: 16,
    fontWeight: 950,
    cursor: "text",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left",
  },

  modalNameInput: {
    borderRadius: 10,
    border: "1px solid rgba(59,130,246,.6)",
    background: "rgba(255,255,255,.08)",
    color: "rgba(255,255,255,.95)",
    fontSize: 15,
    fontWeight: 900,
    padding: "6px 10px",
    minWidth: 180,
  },

  modalSubtitle: {
    marginTop: 4,
    fontSize: 12,
    opacity: 0.65,
  },

  modalTopRight: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },

  addrButton: {
    minWidth: 240,
    maxWidth: 360,
    padding: "8px 10px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.14)",
    background: "rgba(255,255,255,.04)",
    color: "rgba(255,255,255,.92)",
    textAlign: "left",
    cursor: "pointer",
  },

  addrButtonCopied: {
    border: "1px solid rgba(34,197,94,.7)",
    background: "rgba(34,197,94,.12)",
  },

  addrLabel: { fontSize: 11, opacity: 0.7, fontWeight: 800 },
  addrValue: {
    marginTop: 2,
    fontSize: 12,
    fontWeight: 900,
    opacity: 0.92,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  },

  addrHint: { fontSize: 11, opacity: 0.7, marginTop: 4, fontWeight: 700 },

  modalBody: {
    display: "grid",
    gridTemplateColumns: "200px 1fr 300px",
    minHeight: 520,
  },

  confirmOverlay: {
    position: "absolute",
    inset: 0,
    background: "rgba(0,0,0,.58)",
    display: "grid",
    placeItems: "center",
    zIndex: 20,
    padding: 20,
  },

  confirmCard: {
    width: "min(520px, 100%)",
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,.14)",
    background: "rgba(12,16,28,.98)",
    padding: 16,
    boxShadow: "0 20px 60px rgba(0,0,0,.55)",
  },

  confirmActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    marginTop: 14,
  },

  leftNav: {
    padding: 12,
    borderRight: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.03)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },

  leftNavFooter: {
    marginTop: "auto",
    paddingTop: 8,
  },

  deleteServerBtn: {
    width: "100%",
    textAlign: "left",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(239,68,68,.4)",
    background: "rgba(239,68,68,.16)",
    color: "rgba(255,220,220,.95)",
    fontWeight: 900,
    cursor: "pointer",
  },

  centerPane: { padding: 16 },

  rightPane: {
    padding: 12,
    borderLeft: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.03)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },

  playersHeader: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 8,
    padding: "10px 10px 4px",
  },

  search: {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.06)",
    color: "rgba(255,255,255,.92)",
    fontWeight: 800,
    fontSize: 13,
  },

  playersList: {
    flex: 1,
    overflow: "auto",
    padding: 6,
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.04)",
  },

  playersEmpty: { padding: 12, opacity: 0.7, fontWeight: 800, fontSize: 13 },

  playerRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 10px",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.05)",
    marginBottom: 8,
  },

  playerHead: {
    width: 32,
    height: 32,
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.06)",
    display: "grid",
    placeItems: "center",
    overflow: "hidden",
    flexShrink: 0,
  },

  paneTitle: { fontSize: 16, fontWeight: 950 },

  consoleHint: {
    marginTop: 8,
    opacity: 0.7,
    fontSize: 12,
    fontWeight: 700,
  },

  consoleView: {
    marginTop: 10,
    height: 370,
    overflow: "auto",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(2,6,23,.92)",
    padding: 10,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: 12,
    lineHeight: 1.45,
  },

  consoleLine: {
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    color: "rgba(229,231,235,.95)",
    marginBottom: 4,
  },

  consoleEmpty: {
    opacity: 0.65,
    fontWeight: 700,
  },

  consoleInputRow: {
    marginTop: 10,
    display: "flex",
    alignItems: "center",
    gap: 10,
  },

  consoleInput: {
    flex: 1,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.04)",
    color: "rgba(255,255,255,.95)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: 12,
    fontWeight: 700,
  },

  consoleError: {
    marginTop: 8,
    fontSize: 12,
    color: "rgba(252,165,165,.95)",
    fontWeight: 800,
  },



  contentTabRow: {
    marginTop: 10,
    display: "flex",
    gap: 8,
  },

  contentTabBtn: {
    border: "1px solid rgba(255,255,255,.14)",
    background: "rgba(255,255,255,.03)",
    color: "rgba(255,255,255,.88)",
    borderRadius: 10,
    padding: "7px 10px",
    fontSize: 12,
    fontWeight: 800,
    cursor: "pointer",
  },

  contentTabBtnActive: {
    border: "1px solid rgba(56,189,248,.55)",
    background: "rgba(56,189,248,.18)",
    color: "rgba(224,242,254,.95)",
  },

  contentMeta: {
    marginTop: 10,
    opacity: 0.72,
    fontSize: 12,
    fontWeight: 700,
  },

  contentSearchRow: {
    marginTop: 10,
    display: "flex",
    gap: 8,
    alignItems: "center",
  },

  contentSelect: {
    flex: 1,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(13,18,31,.96)",
    color: "rgba(255,255,255,.95)",
    fontSize: 12,
    fontWeight: 700,
    colorScheme: "dark",
  },

  contentSectionTitle: {
    marginTop: 8,
    marginBottom: 4,
    fontSize: 12,
    fontWeight: 900,
    opacity: 0.78,
    letterSpacing: 0.2,
  },

  contentResults: {
    marginTop: 10,
    display: "grid",
    gap: 8,
    maxHeight: "52vh",
    overflowY: "auto",
    paddingRight: 4,
  },

  contentItemBtn: {
    border: "none",
    background: "transparent",
    padding: 0,
    margin: 0,
    textAlign: "left",
    cursor: "pointer",
  },

  contentItem: {
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.03)",
    padding: 10,
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "flex-start",
    color: "rgba(245,251,255,.95)",
  },

  contentThumbWrap: {
    width: 48,
    height: 48,
    borderRadius: 10,
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.04)",
    flexShrink: 0,
  },

  contentThumb: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },

  contentThumbPlaceholder: {
    width: "100%",
    height: "100%",
    display: "grid",
    placeItems: "center",
    fontWeight: 900,
    opacity: 0.7,
  },

  contentItemTitle: {
    fontSize: 13,
    fontWeight: 900,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  contentItemMeta: {
    marginTop: 4,
    fontSize: 11,
    opacity: 0.72,
    fontWeight: 700,
  },

  contentPickerBtn: {
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.03)",
    padding: 10,
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "flex-start",
    cursor: "pointer",
    color: "rgba(245,251,255,.95)",
    textAlign: "left",
  },

  contentSaveOk: {
    marginTop: 4,
    fontSize: 11,
    fontWeight: 900,
    color: "rgba(74,222,128,.95)",
  },

  contentItemDesc: {
    marginTop: 6,
    fontSize: 12,
    opacity: 0.84,
    lineHeight: 1.35,
  },


  contentOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,.55)",
    zIndex: 90,
    display: "grid",
    placeItems: "center",
    padding: 20,
  },

  contentModal: {
    width: "min(760px, 100%)",
    maxHeight: "85vh",
    overflow: "auto",
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(10,14,26,.98)",
    boxShadow: "0 30px 80px rgba(0,0,0,.55)",
  },

  contentModalHead: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 12,
    borderBottom: "1px solid rgba(255,255,255,.08)",
  },

  contentModalBody: {
    padding: 12,
    display: "grid",
    gap: 8,
  },

  contentModalImage: {
    width: 96,
    height: 96,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.12)",
    objectFit: "cover",
  },

  contentModalActions: {
    padding: 12,
    borderTop: "1px solid rgba(255,255,255,.08)",
    display: "flex",
    justifyContent: "flex-end",
  },

  configEditorArea: {
    width: "100%",
    minHeight: 360,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(5,9,18,.92)",
    color: "rgba(240,249,255,.95)",
    padding: 10,
    fontSize: 12,
    lineHeight: 1.4,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    resize: "vertical",
  },

  detailsMetricsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 12,
    marginTop: 12,
  },

  perfGraphWrap: {
    display: "grid",
    gridTemplateColumns: "44px minmax(0, 1fr)",
    alignItems: "stretch",
    gap: 8,
    marginTop: 6,
  },

  perfYAxis: {
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    fontSize: 11,
    opacity: 0.62,
    fontWeight: 800,
    padding: "8px 0",
    textAlign: "right",
  },

  perfGraph: {
    height: 110,
    position: "relative",
    overflow: "hidden",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,.08)",
    background: "linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02))",
    padding: 8,
    display: "flex",
    alignItems: "stretch",
  },

  perfBars: {
    position: "relative",
    zIndex: 1,
    display: "grid",
    gridTemplateColumns: "repeat(30, minmax(0, 1fr))",
    alignItems: "end",
    gap: 2,
    width: "100%",
    height: "100%",
  },

  perfBar: {
    borderRadius: "4px 4px 0 0",
    background: "linear-gradient(180deg, rgba(56,189,248,.92), rgba(56,189,248,.28))",
    minHeight: 2,
    boxShadow: "inset 0 0 0 1px rgba(186,230,253,.16)",
  },

  perfBarLatest: {
    background: "linear-gradient(180deg, rgba(192,132,252,.98), rgba(168,85,247,.42))",
    boxShadow: "inset 0 0 0 1px rgba(233,213,255,.3)",
  },

  perfGuide: {
    position: "absolute",
    left: 8,
    right: 8,
    borderTop: "1px dashed rgba(255,255,255,.14)",
    pointerEvents: "none",
  },

  perfStatsRow: {
    marginTop: 8,
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },

  perfStatPill: {
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.05)",
    borderRadius: 999,
    padding: "4px 9px",
    fontSize: 11,
    fontWeight: 900,
    color: "rgba(224,242,254,.94)",
  },

  perfMeta: {
    marginTop: 6,
    fontSize: 11,
    opacity: 0.62,
    fontWeight: 700,
    display: "flex",
    justifyContent: "space-between",
  },

  banManagerToggle: {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(125,211,252,.35)",
    background: "rgba(56,189,248,.14)",
    color: "rgba(224,242,254,.95)",
    fontWeight: 900,
    cursor: "pointer",
    marginTop: 8,
  },

  banManagerWrap: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },

  banManagerHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },

  banSection: {
    border: "1px solid rgba(255,255,255,.08)",
    borderRadius: 12,
    padding: 8,
    background: "rgba(255,255,255,.04)",
  },

  banSectionTitle: {
    fontWeight: 900,
    opacity: 0.8,
    fontSize: 12,
    marginBottom: 8,
  },

  banRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    padding: "6px 8px",
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.03)",
    marginBottom: 6,
  },

  kvGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
    marginTop: 12,
  },

  kv: {
    padding: 12,
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.04)",
  },

  k: { fontSize: 12, opacity: 0.65, fontWeight: 800 },
  v: { marginTop: 6, fontSize: 13, fontWeight: 900, wordBreak: "break-word" },

  smallLabel: { fontSize: 12, opacity: 0.65, fontWeight: 800 },

  monoBox: {
    marginTop: 6,
    padding: 12,
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.04)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: 12,
    opacity: 0.9,
    wordBreak: "break-all",
  },

  // Logs
  logsWrap: {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 60,
  },

  logsBar: {
    height: 44,
    padding: "0 14px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "rgba(8,10,18,.92)",
    borderTop: "1px solid rgba(255,255,255,.10)",
    backdropFilter: "blur(10px)",
    cursor: "pointer",
    userSelect: "none",
  },

  logsHandle: { width: 34, height: 6, borderRadius: 999, background: "rgba(255,255,255,.14)" },

  logsDrawer: {
    overflow: "hidden",
    background: "rgba(8,10,18,.92)",
    backdropFilter: "blur(10px)",
    transition: "height 160ms ease",
  },

  logsHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px 8px",
  },

  logsBody: {
    maxHeight: 180,
    overflow: "auto",
    padding: "0 12px 12px",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: 12,
  },

  logRow: {
    display: "grid",
    gridTemplateColumns: "70px 70px 1fr",
    gap: 10,
    padding: "6px 0",
    borderBottom: "1px solid rgba(255,255,255,.06)",
  },

  logTime: { opacity: 0.7 },
  logLevel: { fontWeight: 900 },
  logMsg: { opacity: 0.9 },
};
