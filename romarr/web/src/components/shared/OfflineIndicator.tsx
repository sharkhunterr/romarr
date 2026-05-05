/**
 * OfflineIndicator (T021).
 *
 * Top-of-app banner that surfaces when the device itself is
 * offline (no network at all — distinct from the WebSocket
 * health that ConnectionIndicator owns). Subscribes to the
 * window ``online`` / ``offline`` events and renders nothing
 * when the navigator reports a healthy connection.
 *
 * The banner is purely informational — TanStack Query keeps
 * serving its cached responses, mutations queue at the
 * fetch level. Once the device comes back online the banner
 * unmounts and the WS bridge reconnects on its own backoff
 * schedule.
 */

import { WifiOff } from "lucide-react";
import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

function _initialOffline(): boolean {
  if (typeof navigator === "undefined") return false;
  // ``onLine`` is conservative — false is the source of truth
  // for "offline"; true means "the browser thinks it has a
  // connection" but doesn't guarantee reachability. Pair with
  // the WS connection indicator for the latter.
  return navigator.onLine === false;
}

export function OfflineIndicator(): ReactElement | null {
  const { t } = useTranslation();
  const [isOffline, setIsOffline] = useState<boolean>(_initialOffline);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onOnline = (): void => setIsOffline(false);
    const onOffline = (): void => setIsOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  if (!isOffline) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        "sticky top-0 z-50 flex items-center justify-center gap-2",
        "bg-amber-700/30 px-4 py-1.5 text-[0.7rem] font-medium",
        "text-amber-100 ring-1 ring-inset ring-amber-500/40",
      ].join(" ")}
    >
      <WifiOff size={12} aria-hidden="true" />
      <span>{t("connection.deviceOffline")}</span>
    </div>
  );
}
