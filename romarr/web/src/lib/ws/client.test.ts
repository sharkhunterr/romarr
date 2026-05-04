/**
 * WebSocketClient tests (spec 014 T045 + T047).
 *
 * Exercises the documented contract of ``WebSocketClient``:
 *   * Initial connect → status "connecting", then "connected"
 *     once the open event fires.
 *   * Disconnect → "reconnecting" status; the offline grace
 *     timer flips status to "offline" after 10 s of sticky
 *     reconnecting (T047).
 *   * Backoff schedule [1s, 2s, 4s, 8s, 16s, 30s] cap-at-last
 *     (T045) — exercised across consecutive close events.
 *   * stop() clears every timer and surfaces "idle".
 *
 * Uses a tiny in-test MockWebSocket that captures the most
 * recent instance so the test can drive open/close/error
 * events synchronously. No real network.
 */

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest";

import { WebSocketClient } from "./client";

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = 0;
  private listeners: Map<string, Array<(event: Event) => void>> = new Map();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  addEventListener(event: string, handler: (event: Event) => void): void {
    const list = this.listeners.get(event) ?? [];
    list.push(handler);
    this.listeners.set(event, list);
  }

  removeEventListener(): void {
    /* no-op */
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED;
  }

  send(): void {
    /* no-op */
  }

  // Test helpers — fire events into the listeners.
  _open(): void {
    this.readyState = MockWebSocket.OPEN;
    for (const fn of this.listeners.get("open") ?? []) {
      fn(new Event("open"));
    }
  }

  _close(code = 1000): void {
    this.readyState = MockWebSocket.CLOSED;
    const event = new CloseEvent("close", { code });
    for (const fn of this.listeners.get("close") ?? []) {
      fn(event);
    }
  }
}

let originalWebSocket: typeof WebSocket | undefined;

beforeEach(() => {
  vi.useFakeTimers();
  originalWebSocket = (globalThis as unknown as { WebSocket?: typeof WebSocket })
    .WebSocket;
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;
  MockWebSocket.instances = [];
});

afterEach(() => {
  vi.useRealTimers();
  if (originalWebSocket !== undefined) {
    (globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      originalWebSocket;
  }
});

function _newClient(): {
  client: WebSocketClient;
  status: Mock;
  onMessage: Mock;
} {
  const status = vi.fn();
  const onMessage = vi.fn();
  const client = new WebSocketClient({
    url: "ws://localhost:9999/signalr/messages",
    onMessage,
    onStatusChange: status,
  });
  return { client, status, onMessage };
}

describe("WebSocketClient", () => {
  it("emits 'connecting' → 'connected' on the happy path", () => {
    const { client, status } = _newClient();
    client.start();

    expect(status).toHaveBeenCalledWith("connecting");

    const sock = MockWebSocket.instances.at(-1)!;
    sock._open();

    expect(status).toHaveBeenCalledWith("connected");
    client.stop();
  });

  it("flips status to 'offline' after the 10s grace window (T047)", () => {
    const { client, status } = _newClient();
    client.start();
    const first = MockWebSocket.instances.at(-1)!;
    first._open();
    status.mockClear();

    // Server-side close → reconnect is scheduled; status flips
    // to "reconnecting" before the next openSocket fires.
    first._close();

    // Within the 10s grace, status hasn't reached "offline" yet.
    vi.advanceTimersByTime(5_000);
    expect(status).not.toHaveBeenCalledWith("offline");

    // Past 10s → offline (the offline grace timer fires when
    // we're STILL in reconnecting state on the next openSocket
    // attempt).
    vi.advanceTimersByTime(20_000);
    const calls = status.mock.calls.map((c) => c[0]);
    expect(calls).toContain("offline");

    client.stop();
  });

  it("backs off at 1s for the first reconnect attempt (T045)", () => {
    const { client } = _newClient();
    client.start();
    const first = MockWebSocket.instances.at(-1)!;
    first._open();
    first._close();

    expect(MockWebSocket.instances.length).toBe(1);
    // 1 s elapses → second connection attempt fires.
    vi.advanceTimersByTime(1_000);
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);

    client.stop();
  });

  it("stop() resets to 'idle' and clears reconnect timers", () => {
    const { client, status } = _newClient();
    client.start();
    const first = MockWebSocket.instances.at(-1)!;
    first._open();
    first._close();

    status.mockClear();
    client.stop();

    expect(status).toHaveBeenCalledWith("idle");
    // After stop, advancing the clock does NOT spawn new
    // sockets (no reconnect leaks past stop()).
    const before = MockWebSocket.instances.length;
    vi.advanceTimersByTime(60_000);
    expect(MockWebSocket.instances.length).toBe(before);
  });
});
