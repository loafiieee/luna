import { useCallback, useRef, useState } from "react";
import type { LogItem } from "../lib/types";

export function useLogs() {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const endRef = useRef<HTMLDivElement | null>(null);

  const addLog = useCallback((level: LogItem["level"], msg: string) => {
    setLogs((prev) => {
      const next = [...prev, { t: Date.now(), level, msg }];
      return next.length > 300 ? next.slice(next.length - 300) : next;
    });
  }, []);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, addLog, clearLogs, endRef };
}
