/**
 * WebSocket client (T048, FR-018, FR-019).
 *
 * Wraps the browser WebSocket against /signalr/messages with:
 *   * exponential reconnection backoff: 1 s → 2 → 4 → 8 → 16 →
 *     30 s cap (FR-019).
 *   * a 30 s keepalive ping — the server echoes back as a
 *     systemMessage pong; the protocol is symmetric (handler
 *     side: src/romarr/api/ws/handler.py).
 *   * a typed event handler — only well-formed envelopes hit
 *     the consumer; malformed frames are dropped with a console
 *     warning.
 *   * an offline grace window: the connection store flips to
 *     "offline" only after 10 s of disconnection (FR-019 + the
 *     spec 014 Q3 clarification — operator UI shouldn't flap
 *     during a quick reconnect).
 *
 * Auth is implicit: the WebSocket upgrade carries the session
 * cookie set by /api/v3/auth/login (or the API key in the
 * future). The handler closes with code 1008 if the principal
 * can't be resolved — we surface that as a permanent close
 * (no reconnect attempt).
 *
 * The class is framework-agnostic. The React bridge that wires
 * it to the QueryClient and the Zustand connection store lives
 * in `useWebSocketBridge.ts`.
 */

import {
  isWsEnvelope,
  type ConnectionStatus,
  type WsEnvelope,
} from "./types";

const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000] as const;
const PING_INTERVAL_MS = 30_000;
const OFFLINE_THRESHOLD_MS = 10_000;
/** Close code emitted by the server when auth fails. */
const POLICY_VIOLATION = 1008;

export interface WebSocketClientOptions {
  /**
   * Full WebSocket URL (e.g. `ws://localhost:8585/signalr/messages`).
   * Falls back to `wsUrlFromLocation()` when omitted.
   */
  url?: string;
  /** Called on every well-formed envelope. */
  onMessage: (envelope: WsEnvelope) => void;
  /** Called whenever the connection lifecycle changes. */
  onStatusChange: (status: ConnectionStatus) => void;
}

export function wsUrlFromLocation(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/signalr/messages`;
}

export class WebSocketClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  private offlineTimer: number | null = null;
  private attempt = 0;
  private stopped = false;
  private currentStatus: ConnectionStatus = "idle";
  private readonly options: WebSocketClientOptions;

  constructor(options: WebSocketClientOptions) {
    this.options = options;
  }

  start(): void {
    this.stopped = false;
    this.attempt = 0;
    this.openSocket();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    if (this.offlineTimer !== null) {
      window.clearTimeout(this.offlineTimer);
      this.offlineTimer = null;
    }
    if (this.socket !== null) {
      const socket = this.socket;
      this.socket = null;
      try {
        socket.close(1000, "client-shutdown");
      } catch {
        // Browser already in a closing state; nothing to do.
      }
    }
    this.setStatus("idle");
  }

  /** Emit the offline-grace status if the disconnect is sticky. */
  private armOfflineTimer(): void {
    if (this.offlineTimer !== null) {
      window.clearTimeout(this.offlineTimer);
    }
    this.offlineTimer = window.setTimeout(() => {
      if (this.currentStatus === "reconnecting") {
        this.setStatus("offline");
      }
    }, OFFLINE_THRESHOLD_MS);
  }

  private setStatus(status: ConnectionStatus): void {
    if (status === this.currentStatus) {
      return;
    }
    this.currentStatus = status;
    this.options.onStatusChange(status);
  }

  private nextDelay(): number {
    const idx = Math.min(this.attempt, BACKOFF_MS.length - 1);
    const delay = BACKOFF_MS[idx];
    return delay ?? BACKOFF_MS[BACKOFF_MS.length - 1] ?? 30_000;
  }

  private openSocket(): void {
    if (this.stopped) {
      return;
    }
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    if (this.attempt > 0) {
      this.armOfflineTimer();
    }

    const url = this.options.url ?? wsUrlFromLocation();
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      // Invalid URL or browser blocking the upgrade — schedule
      // a retry with backoff so the operator UI eventually
      // recovers.
      console.warn("[ws] failed to construct WebSocket", err);
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempt = 0;
      if (this.offlineTimer !== null) {
        window.clearTimeout(this.offlineTimer);
        this.offlineTimer = null;
      }
      this.setStatus("connected");
      this.startPing();
    });

    socket.addEventListener("message", (event: MessageEvent) => {
      this.handleMessage(event);
    });

    socket.addEventListener("close", (event: CloseEvent) => {
      this.stopPing();
      this.socket = null;
      if (this.stopped) {
        return;
      }
      if (event.code === POLICY_VIOLATION) {
        // Auth rejected — don't loop, the user needs to log
        // back in. The bridge will restart us once the
        // principal query resolves again.
        console.warn("[ws] auth rejected (1008); not reconnecting");
        this.setStatus("offline");
        return;
      }
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // Errors precede a close; the close handler does the
      // reconnection bookkeeping. Don't double-schedule here.
    });
  }

  private handleMessage(event: MessageEvent): void {
    if (typeof event.data !== "string") {
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(event.data);
    } catch {
      console.warn("[ws] dropped non-JSON frame");
      return;
    }
    if (!isWsEnvelope(parsed)) {
      console.warn("[ws] dropped malformed envelope", parsed);
      return;
    }
    this.options.onMessage(parsed);
  }

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    this.armOfflineTimer();
    const delay = this.nextDelay();
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => {
      const socket = this.socket;
      if (socket === null || socket.readyState !== WebSocket.OPEN) {
        return;
      }
      try {
        socket.send("ping");
      } catch (err) {
        console.warn("[ws] ping failed", err);
      }
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }
}
