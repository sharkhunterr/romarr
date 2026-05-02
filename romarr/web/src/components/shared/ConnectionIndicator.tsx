/**
 * WebSocket connection indicator (T050, FR-019, T117 partial).
 *
 * Tiny status dot in the header. Mirrors the four runtime
 * states emitted by the WS client:
 *
 *   * idle          → muted (no auth yet / bridge not booted)
 *   * connecting    → amber, "Connecting…"
 *   * connected     → brand green, "Live"
 *   * reconnecting  → amber, "Reconnecting…"
 *   * offline       → red, "Offline" (after the 10 s grace
 *                     window — FR-019 + spec 014 Q3)
 *
 * Title attribute carries the verbose label so a hover
 * surfaces it on desktop. The visible label only renders on
 * md+ — mobile keeps the dot for the 360 px target.
 *
 * Strings resolve via i18next (slice 55).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useConnectionStore } from "@/lib/store/connection";
import type { ConnectionStatus } from "@/lib/ws/types";

const STATUS_DOT: Record<ConnectionStatus, string> = {
  idle: "bg-zinc-600",
  connecting: "bg-amber-500 animate-pulse",
  connected: "bg-brand",
  reconnecting: "bg-amber-500 animate-pulse",
  offline: "bg-red-500",
};

export function ConnectionIndicator(): ReactElement {
  const { t } = useTranslation();
  const status = useConnectionStore((s) => s.status);
  const label = t(`connection.${status}`);

  return (
    <div
      role="status"
      aria-live="polite"
      title={label}
      className={[
        "flex items-center gap-1.5 rounded-md px-2 py-1",
        "text-[0.7rem] font-medium",
      ].join(" ")}
    >
      <span
        aria-hidden="true"
        className={[
          "inline-block h-2 w-2 rounded-full",
          STATUS_DOT[status],
        ].join(" ")}
      />
      <span className="hidden text-zinc-400 md:inline">{label}</span>
    </div>
  );
}
