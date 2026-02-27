import type React from "react";

export const styles: Record<string, React.CSSProperties> = {
  app: {
    minHeight: "100vh",
    paddingBottom: "calc(46px + env(safe-area-inset-bottom, 0px))",
    color: "rgba(255,255,255,.92)",
    fontFamily: "\"Manrope\", \"Avenir Next\", \"Segoe UI\", sans-serif",
    background:
      "radial-gradient(1250px 760px at 10% 0%, rgba(56,189,248,.16), transparent 60%), radial-gradient(900px 620px at 100% 10%, rgba(14,165,233,.12), transparent 55%), #070A12",
  },

  topChrome: {
    maxWidth: "var(--luna-content-max)",
    margin: "0 auto",
    padding: "clamp(12px, 1.25vw, 20px) clamp(14px, 1.45vw, 24px) 6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "clamp(10px, 1vw, 16px)",
  },

  brandDot: {
    width: "clamp(12px, .9vw, 15px)",
    height: "clamp(12px, .9vw, 15px)",
    borderRadius: 999,
    background: "linear-gradient(135deg, rgba(56,189,248,1), rgba(37,99,235,1))",
    boxShadow: "0 0 0 clamp(4px, .6vw, 7px) rgba(255,255,255,.03)",
  },

  brandTitle: { fontSize: "clamp(18px, 1.1vw, 23px)", fontWeight: 950, letterSpacing: 0.2 },
  brandSub: { fontSize: "clamp(11px, .72vw, 13px)", opacity: 0.65, marginTop: 2 },

  errorBox: {
    maxWidth: "var(--luna-content-max)",
    margin: "8px auto 0",
    padding: "clamp(10px, 1vw, 14px)",
    borderRadius: "clamp(14px, 1vw, 18px)",
    background: "rgba(239,68,68,.12)",
    border: "1px solid rgba(239,68,68,.25)",
    color: "rgba(255,255,255,.92)",
    fontSize: "clamp(12px, .76vw, 13px)",
  },

  grid: {
    maxWidth: "var(--luna-content-max)",
    margin: "10px auto 0",
    padding: "clamp(10px, .95vw, 14px) clamp(14px, 1.45vw, 24px) clamp(20px, 2.5vw, 30px)",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(clamp(220px, 28vw, 320px), 1fr))",
    gap: "clamp(12px, 1vw, 18px)",
  },

  empty: {
    gridColumn: "1 / -1",
    padding: "clamp(14px, 1.3vw, 22px)",
    borderRadius: "clamp(14px, 1.2vw, 20px)",
    border: "1px dashed rgba(255,255,255,.14)",
    background: "rgba(255,255,255,.04)",
  },

  // Card
  card: {
    borderRadius: "clamp(15px, 1.2vw, 22px)",
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.05)",
    boxShadow: "0 18px 56px rgba(0,0,0,.45)",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    minHeight: "clamp(214px, 27vw, 290px)",
    transition: "transform 200ms ease, box-shadow 220ms ease",
  },

  cardIconWrap: {
    position: "relative",
    height: "clamp(128px, 17vw, 186px)",
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
    padding: "clamp(12px, 1vw, 16px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "clamp(10px, .9vw, 14px)",
  },

  cardName: {
    fontSize: "clamp(14px, .92vw, 17px)",
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
    fontSize: "clamp(11px, .75vw, 13px)",
    fontWeight: 800,
  },

  // Modal
  modal: {
    width: "min(1320px, 100%)",
    borderRadius: "clamp(16px, 1.4vw, 24px)",
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
    gap: "clamp(10px, .9vw, 14px)",
    padding: "clamp(10px, .9vw, 14px)",
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
    width: "clamp(40px, 2.8vw, 48px)",
    height: "clamp(40px, 2.8vw, 48px)",
    borderRadius: "clamp(12px, .95vw, 15px)",
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
    fontSize: "clamp(15px, .95vw, 18px)",
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
    fontSize: "clamp(15px, .95vw, 18px)",
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
    fontSize: "clamp(14px, .9vw, 16px)",
    fontWeight: 900,
    padding: "clamp(5px, .5vw, 7px) clamp(9px, .8vw, 11px)",
    minWidth: 170,
  },

  modalSubtitle: {
    marginTop: 4,
    fontSize: "clamp(11px, .72vw, 13px)",
    opacity: 0.65,
  },

  modalTopRight: {
    display: "flex",
    alignItems: "center",
    gap: "clamp(8px, .85vw, 12px)",
    minWidth: 0,
    paddingRight: 4,
  },

  addrButton: {
    minWidth: "clamp(180px, 22vw, 290px)",
    maxWidth: "min(390px, 100%)",
    flex: "1 1 clamp(180px, 24vw, 270px)",
    padding: "clamp(7px, .75vw, 9px) clamp(9px, .9vw, 12px)",
    borderRadius: "clamp(10px, .95vw, 14px)",
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

  addrLabel: { fontSize: "clamp(10px, .66vw, 11px)", opacity: 0.7, fontWeight: 800 },
  addrValue: {
    marginTop: 2,
    fontSize: "clamp(11px, .78vw, 13px)",
    fontWeight: 900,
    opacity: 0.92,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  },

  addrHint: { fontSize: "clamp(10px, .66vw, 11px)", opacity: 0.7, marginTop: 4, fontWeight: 700 },

  modalBody: {
    display: "grid",
    gridTemplateColumns: "minmax(180px, 220px) minmax(0, 1fr) minmax(250px, 320px)",
    minHeight: "clamp(460px, 66vh, 760px)",
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
    borderRadius: "clamp(14px, 1vw, 18px)",
    border: "1px solid rgba(255,255,255,.14)",
    background: "rgba(12,16,28,.98)",
    padding: "clamp(12px, 1vw, 16px)",
    boxShadow: "0 20px 60px rgba(0,0,0,.55)",
  },

  confirmActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    marginTop: 14,
  },

  leftNav: {
    padding: "clamp(10px, .9vw, 14px)",
    borderRight: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.03)",
    display: "flex",
    flexDirection: "column",
    gap: "clamp(8px, .7vw, 10px)",
  },

  leftNavFooter: {
    marginTop: "auto",
    paddingTop: 8,
  },

  deleteServerBtn: {
    width: "100%",
    textAlign: "left",
    padding: "clamp(9px, .8vw, 11px) clamp(10px, .85vw, 12px)",
    borderRadius: 12,
    border: "1px solid rgba(239,68,68,.4)",
    background: "rgba(239,68,68,.16)",
    color: "rgba(255,220,220,.95)",
    fontWeight: 900,
    cursor: "pointer",
  },

  centerPane: { padding: "clamp(12px, 1vw, 18px)" },

  rightPane: {
    padding: "clamp(10px, .9vw, 14px)",
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
    padding: "clamp(9px, .85vw, 11px) clamp(10px, .95vw, 13px)",
    borderRadius: "clamp(12px, .95vw, 15px)",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.06)",
    color: "rgba(255,255,255,.92)",
    fontWeight: 800,
    fontSize: "clamp(12px, .8vw, 13px)",
  },

  playersList: {
    flex: 1,
    overflow: "auto",
    padding: 6,
    borderRadius: "clamp(12px, 1vw, 16px)",
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.04)",
  },

  playersEmpty: { padding: "clamp(10px, .85vw, 12px)", opacity: 0.7, fontWeight: 800, fontSize: "clamp(12px, .82vw, 13px)" },

  playerRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "clamp(7px, .7vw, 9px) clamp(9px, .85vw, 11px)",
    borderRadius: "clamp(11px, .9vw, 14px)",
    border: "1px solid rgba(255,255,255,.08)",
    background: "rgba(255,255,255,.05)",
    marginBottom: 8,
  },

  playerHead: {
    width: "clamp(30px, 2vw, 34px)",
    height: "clamp(30px, 2vw, 34px)",
    borderRadius: "clamp(9px, .75vw, 11px)",
    border: "1px solid rgba(255,255,255,.12)",
    background: "rgba(255,255,255,.06)",
    display: "grid",
    placeItems: "center",
    overflow: "hidden",
    flexShrink: 0,
  },

  paneTitle: { fontSize: "clamp(15px, .95vw, 18px)", fontWeight: 950 },

  consoleHint: {
    marginTop: 8,
    opacity: 0.7,
    fontSize: "clamp(11px, .72vw, 13px)",
    fontWeight: 700,
  },

  consoleView: {
    marginTop: 10,
    height: "clamp(280px, 40vh, 430px)",
    overflow: "auto",
    borderRadius: "clamp(12px, 1vw, 16px)",
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(2,6,23,.92)",
    padding: "clamp(8px, .8vw, 10px)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "clamp(11px, .72vw, 13px)",
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
    flexWrap: "wrap",
  },

  consoleInput: {
    flex: 1,
    minWidth: 0,
    padding: "clamp(9px, .85vw, 11px) clamp(10px, .95vw, 13px)",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,.10)",
    background: "rgba(255,255,255,.04)",
    color: "rgba(255,255,255,.95)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "clamp(11px, .72vw, 13px)",
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
    height: "clamp(42px, 3.4vw, 48px)",
    padding: "0 clamp(12px, 1.2vw, 16px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "rgba(8,10,18,.92)",
    borderTop: "1px solid rgba(255,255,255,.10)",
    backdropFilter: "blur(10px)",
    cursor: "pointer",
    userSelect: "none",
  },

  logsHandle: { width: "clamp(30px, 2.4vw, 36px)", height: 6, borderRadius: 999, background: "rgba(255,255,255,.14)" },

  logsDrawer: {
    overflow: "hidden",
    background: "rgba(8,10,18,.92)",
    backdropFilter: "blur(10px)",
    transition: "height 200ms ease",
  },

  logsHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px 8px",
  },

  logsBody: {
    maxHeight: "calc(var(--logs-open-height) - 56px)",
    overflow: "auto",
    padding: "0 clamp(10px, 1vw, 12px) clamp(10px, 1vw, 12px)",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "clamp(11px, .72vw, 13px)",
  },

  logRow: {
    display: "grid",
    gridTemplateColumns: "clamp(62px, 6vw, 78px) clamp(62px, 6vw, 78px) 1fr",
    gap: "clamp(8px, .8vw, 12px)",
    padding: "6px 0",
    borderBottom: "1px solid rgba(255,255,255,.06)",
  },

  logTime: { opacity: 0.7 },
  logLevel: { fontWeight: 900 },
  logMsg: { opacity: 0.9 },
};
