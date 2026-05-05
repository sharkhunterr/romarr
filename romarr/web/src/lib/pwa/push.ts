/**
 * Web Push registration scaffolding (spec 014 T057).
 *
 * Three pieces wired together:
 *   * ``useWebPushSupport()`` — ``isSupported`` + ``permission`` state
 *     for the operator UI to gate the subscribe button.
 *   * ``useWebPushSubscription()`` — current subscription endpoint
 *     plus a ``subscribe()`` / ``unsubscribe()`` mutation pair.
 *   * ``getVapidPublicKey()`` / ``persistSubscription()`` — backend
 *     wiring that talks to the spec 012 notification surface
 *     (deferred — endpoints not yet shipped). When the endpoints
 *     are missing, ``subscribe()`` returns ``"backend_unavailable"``
 *     and the operator UI shows a "configure backend first" hint.
 *
 * Browser feature detection (FR-013):
 *   * Service worker registration ready.
 *   * ``Notification`` API present + permission state machine.
 *   * ``PushManager`` available on the SW registration.
 *
 * Key flow:
 *   1. UI checks ``isSupported``. If false, surface "browser
 *      doesn't support push" hint.
 *   2. UI calls ``subscribe()``:
 *      a. Fetch VAPID public key from backend (deferred).
 *      b. Request notification permission via ``Notification.requestPermission``.
 *      c. Call ``registration.pushManager.subscribe`` with the key.
 *      d. POST the resulting subscription to the backend (deferred).
 *
 * Path divergence on the spec note: today's slice ships only the
 * **frontend hooks** since the backend VAPID + persistence
 * endpoints aren't documented yet. The hooks gracefully degrade
 * to ``"backend_unavailable"`` so the UI shows a "configure
 * backend first" message rather than crashing.
 */

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api/client";

export type SubscribeOutcome =
  | "subscribed"
  | "permission_denied"
  | "unsupported"
  | "backend_unavailable"
  | "browser_error";

export interface VapidConfigResponse {
  enabled: boolean;
  publicKey: string | null;
}

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

/** Detect Web Push capability without touching server state. */
export function isWebPushSupported(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function getNotificationPermission(): NotificationPermission {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "denied";
  }
  return Notification.permission;
}

/**
 * Fetch VAPID public key from the backend. Returns ``null`` when
 * the endpoint isn't shipped yet — UI degrades gracefully to
 * "backend not configured" rather than crashing.
 */
async function getVapidPublicKey(): Promise<string | null> {
  try {
    const response = await apiFetch<VapidConfigResponse>(
      "/api/v3/notification/webpush/config",
    );
    if (!response.enabled || !response.publicKey) {
      return null;
    }
    return response.publicKey;
  } catch (error) {
    // Backend doesn't ship this endpoint yet. The UI surface
    // shows a "configure backend" hint via the
    // ``backend_unavailable`` outcome.
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

/**
 * POST the operator's push subscription to the backend so future
 * health-issue / notification events can fan out via Web Push.
 */
async function persistSubscription(
  payload: PushSubscriptionPayload,
): Promise<void> {
  await apiFetch<unknown>("/api/v3/notification/webpush/subscribe", {
    method: "POST",
    json: payload,
  });
}

/**
 * Translate a base64-url-encoded VAPID public key (the format
 * the backend serves) into a ``Uint8Array`` the
 * ``PushManager.subscribe`` API accepts.
 */
function urlBase64ToUint8Array(base64String: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const rawData = atob(base64);
  const buffer = new ArrayBuffer(rawData.length);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < rawData.length; i += 1) {
    view[i] = rawData.charCodeAt(i);
  }
  return buffer;
}

interface UseWebPushSupportResult {
  isSupported: boolean;
  permission: NotificationPermission;
}

export function useWebPushSupport(): UseWebPushSupportResult {
  const [permission, setPermission] = useState<NotificationPermission>(() =>
    getNotificationPermission(),
  );
  const isSupported = isWebPushSupported();

  // Re-read the permission every render so a permission change
  // (operator clicked "Allow" in the browser's site settings)
  // surfaces the next time the component renders.
  useEffect(() => {
    setPermission(getNotificationPermission());
  });

  return { isSupported, permission };
}

interface UseWebPushSubscriptionResult {
  subscribed: boolean;
  endpoint: string | null;
  subscribe: () => Promise<SubscribeOutcome>;
  unsubscribe: () => Promise<void>;
}

/**
 * Reactive Web Push subscription state + control surface. The
 * underlying ``PushSubscription`` is fetched once on mount and
 * refreshed after subscribe / unsubscribe.
 *
 * Returns ``"backend_unavailable"`` from ``subscribe`` when the
 * spec 012 VAPID config endpoint isn't reachable; the UI shows
 * a "configure your push backend first" hint in that case.
 */
export function useWebPushSubscription(): UseWebPushSubscriptionResult {
  const [endpoint, setEndpoint] = useState<string | null>(null);

  useEffect(() => {
    if (!isWebPushSupported()) {
      return;
    }
    void navigator.serviceWorker.ready
      .then((registration) =>
        registration.pushManager.getSubscription(),
      )
      .then((subscription) => {
        setEndpoint(subscription?.endpoint ?? null);
      });
  }, []);

  async function subscribe(): Promise<SubscribeOutcome> {
    if (!isWebPushSupported()) {
      return "unsupported";
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return "permission_denied";
    }

    const publicKey = await getVapidPublicKey();
    if (publicKey === null) {
      return "backend_unavailable";
    }

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      const json = subscription.toJSON();
      const payload: PushSubscriptionPayload = {
        endpoint: subscription.endpoint,
        keys: {
          p256dh: (json.keys as Record<string, string> | undefined)?.p256dh ?? "",
          auth: (json.keys as Record<string, string> | undefined)?.auth ?? "",
        },
      };
      await persistSubscription(payload);
      setEndpoint(subscription.endpoint);
      return "subscribed";
    } catch {
      return "browser_error";
    }
  }

  async function unsubscribe(): Promise<void> {
    if (!isWebPushSupported()) {
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription !== null) {
      await subscription.unsubscribe();
      setEndpoint(null);
    }
  }

  return {
    subscribed: endpoint !== null,
    endpoint,
    subscribe,
    unsubscribe,
  };
}
