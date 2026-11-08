import { useEffect, useRef, useState } from "react";
import type { BusEvent } from "../types";

/**
 * EventSource 订阅 /api/events；断线 3 秒自动重连。
 * onmessage 收到的是 {type, run_id, employee_id, ts, payload}（"connected" 命名事件被忽略）。
 */
export function useBus(maxItems = 200) {
  const [events, setEvents] = useState<BusEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    let es: EventSource | null = null;
    let timer: number | null = null;

    const connect = () => {
      if (!alive) return;
      es = new EventSource("/api/events");
      esRef.current = es;
      es.onopen = () => setConnected(true);
      es.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as BusEvent;
          setEvents(prev => {
            const next = [...prev, ev];
            return next.length > maxItems ? next.slice(next.length - maxItems) : next;
          });
        } catch { /* 忽略非 JSON 帧 */ }
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (timer == null && alive) timer = window.setTimeout(connect, 3000);
      };
    };
    connect();

    return () => {
      alive = false;
      if (timer != null) clearTimeout(timer);
      es?.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [maxItems]);

  const reset = () => setEvents([]);
  return { events, connected, reset };
}
