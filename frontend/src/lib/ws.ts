import { wsUrl } from "@/lib/api";

export type WsEvent =
  | { type: "message"; chat_id: number; message: import("@/types").ChatMessage }
  | { type: "typing"; chat_id: number; user_id: number }
  | { type: "read"; chat_id: number; user_id: number; message_id: number }
  | { type: "presence"; user_id: number; online: boolean; last_seen_at: string }
  | { type: "presence_snapshot"; online_user_ids: number[] }
  | { type: "pong" };

export type WsListener = (event: WsEvent) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<WsListener>();
  private token: string;
  private closedByUser = false;
  private reconnectAttempts = 0;
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  constructor(token: string) {
    this.token = token;
  }

  start() {
    this.closedByUser = false;
    this.connect();
  }

  private connect() {
    if (typeof window === "undefined") return;
    const ws = new WebSocket(wsUrl(this.token));
    this.ws = ws;
    ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
      }, 25_000);
    };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WsEvent;
        this.listeners.forEach((l) => l(data));
      } catch {
        // ignore
      }
    };
    ws.onclose = () => {
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.pingTimer = null;
      this.ws = null;
      if (this.closedByUser) return;
      this.reconnectAttempts += 1;
      const delay = Math.min(15_000, 500 * 2 ** this.reconnectAttempts);
      setTimeout(() => this.connect(), delay);
    };
    ws.onerror = () => {
      ws.close();
    };
  }

  stop() {
    this.closedByUser = true;
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.ws) this.ws.close();
    this.listeners.clear();
  }

  send(data: unknown) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  on(listener: WsListener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
