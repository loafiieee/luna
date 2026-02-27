export function GlobalReset() {
  return (
    <style>{`
      :root {
        --luna-content-max: 1380px;
        --luna-fab-size: clamp(54px, 5.1vw, 66px);
        --logs-open-height: min(42vh, 320px);
      }

      html, body, #root {
        height: 100%;
        width: 100%;
        margin: 0;
        padding: 0;
        background: #070A12;
      }

      * { box-sizing: border-box; }
      input { outline: none; }

      button {
        transition: transform 140ms ease, filter 160ms ease, box-shadow 160ms ease, background 160ms ease;
      }

      button:active { transform: translateY(1px) scale(.995); }
      button:disabled { cursor: not-allowed; opacity: .58; }

      ::-webkit-scrollbar { width: 10px; height: 10px; }
      ::-webkit-scrollbar-thumb { background: rgba(255,255,255,.10); border-radius: 999px; }
      ::-webkit-scrollbar-track { background: rgba(255,255,255,.03); }

      @keyframes luna-fade-up {
        from { opacity: 0; transform: translateY(12px) scale(.985); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }

      @keyframes luna-overlay-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }

      @keyframes luna-modal-in {
        from { opacity: 0; transform: translateY(18px) scale(.985); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }

      @keyframes luna-fab-in {
        from { opacity: 0; transform: translateY(16px) scale(.92); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }

      @keyframes luna-breathe {
        0% { box-shadow: 0 0 0 0 rgba(56,189,248,.18), 0 18px 42px rgba(0,0,0,.44); }
        70% { box-shadow: 0 0 0 14px rgba(56,189,248,0), 0 18px 42px rgba(0,0,0,.44); }
        100% { box-shadow: 0 0 0 0 rgba(56,189,248,0), 0 18px 42px rgba(0,0,0,.44); }
      }

      .luna-app-shell { animation: luna-fade-up 280ms ease-out both; }
      .luna-top-chrome { animation: luna-fade-up 340ms ease-out both; }

      .server-card {
        animation: luna-fade-up 320ms ease-out both;
        animation-delay: var(--card-delay, 0ms);
      }

      .server-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 28px 72px rgba(0,0,0,.56);
      }

      .server-card:hover .server-card-icon { transform: scale(1.06); }

      .server-card-icon {
        transition: transform 260ms ease;
        will-change: transform;
      }

      .modal-overlay-shell {
        animation: luna-overlay-in 190ms ease-out both;
      }

      .server-modal-shell {
        animation: luna-modal-in 220ms ease-out both;
      }

      .server-modal-shell {
        max-height: 94vh;
        display: flex;
        flex-direction: column;
      }

      .server-modal-body {
        flex: 1;
        min-height: 0 !important;
        overflow: hidden;
      }

      .server-modal-center {
        min-height: 0;
        overflow: auto;
      }

      .server-icon-change-chip {
        opacity: 0;
        transform: translateY(3px);
        transition: opacity 140ms ease, transform 140ms ease;
      }

      .server-icon-button:hover .server-icon-change-chip,
      .server-icon-button:focus-visible .server-icon-change-chip,
      .server-icon-button[data-busy="true"] .server-icon-change-chip {
        opacity: 1;
        transform: translateY(0);
      }

      .luna-create-fab {
        width: var(--luna-fab-size) !important;
        height: var(--luna-fab-size) !important;
        animation: luna-fab-in 320ms ease-out 80ms both, luna-breathe 3.2s ease-in-out 1.1s infinite;
      }

      .luna-create-fab:hover {
        transform: translateY(-4px) scale(1.02);
        filter: saturate(1.08) brightness(1.05);
      }

      .server-modal-body {
        grid-template-columns: minmax(180px, 220px) minmax(0, 1fr) minmax(250px, 320px) !important;
      }

      @media (max-width: 1140px) {
        .server-modal-top {
          align-items: flex-start !important;
          flex-wrap: wrap;
          padding-right: 10px !important;
        }

        .server-modal-top-right {
          width: 100%;
          display: grid !important;
          grid-template-columns: minmax(0, 1fr) auto;
          align-items: start;
          gap: 8px;
          justify-content: stretch !important;
        }

        .server-modal-start-btn {
          justify-self: start;
        }

        .server-modal-close-btn {
          justify-self: end;
          margin-right: 0 !important;
        }

        .server-modal-address-btn {
          grid-column: 1 / -1;
          min-width: 0 !important;
          max-width: 100% !important;
          width: 100%;
          flex: none !important;
        }

        .server-modal-body {
          grid-template-columns: minmax(170px, 220px) minmax(0, 1fr) !important;
        }

        .server-modal-right {
          grid-column: 1 / -1;
          border-left: none !important;
          border-top: 1px solid rgba(255,255,255,.10);
          min-height: 220px;
        }
      }

      @media (max-width: 880px) {
        .server-modal-body {
          grid-template-columns: 1fr !important;
          min-height: 0 !important;
        }

        .server-modal-left {
          border-right: none !important;
          border-bottom: 1px solid rgba(255,255,255,.10);
          flex-direction: row !important;
          flex-wrap: nowrap;
          overflow-x: auto;
          overflow-y: hidden;
          padding-bottom: 10px !important;
          scrollbar-width: thin;
        }

        .server-modal-left > button {
          flex: 0 0 auto;
          min-width: 108px;
          white-space: nowrap;
        }

        .server-modal-left-footer {
          width: auto;
          margin-top: 0 !important;
          margin-left: auto;
          padding-top: 0 !important;
          padding-left: 4px;
          flex-shrink: 0;
        }

        .server-modal-left-footer button {
          width: auto !important;
          white-space: nowrap;
        }

        .server-modal-center {
          min-height: 240px;
        }

        .server-modal-right {
          min-height: 180px;
          max-height: 34vh;
          overflow: hidden;
        }
      }

      @media (max-width: 640px) {
        .luna-top-chrome {
          align-items: flex-start !important;
          flex-direction: column;
        }

        .luna-top-chrome > div:last-child {
          width: 100%;
        }

        .luna-top-chrome > div:last-child > button {
          flex: 1 1 auto;
        }

        .luna-create-fab {
          right: 14px !important;
        }
      }

      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
          animation: none !important;
          transition: none !important;
        }
      }
    `}</style>
  );
}
