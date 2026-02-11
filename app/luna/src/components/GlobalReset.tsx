export function GlobalReset() {
  return (
    <style>{`
      html, body, #root { height: 100%; width: 100%; margin: 0; padding: 0; background: #070A12; }
      * { box-sizing: border-box; }
      button:active { transform: translateY(1px); }
      ::-webkit-scrollbar { width: 10px; height: 10px; }
      ::-webkit-scrollbar-thumb { background: rgba(255,255,255,.10); border-radius: 999px; }
      ::-webkit-scrollbar-track { background: rgba(255,255,255,.03); }
      input { outline: none; }
    `}</style>
  );
}
