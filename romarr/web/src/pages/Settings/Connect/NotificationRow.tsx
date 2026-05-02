/**
 * One row in the Notifications list (slice 62).
 *
 * Mirrors the Indexer / DownloadClient row contracts — name +
 * redacted URL + last-status badge + per-event pills, with
 * Test (sends a synthetic OnImport via the same dispatcher
 * real events use) + double-confirm Delete actions.
 *
 * The 7 events match the documented Sonarr-shape catalogue:
 * Grab / Import / Upgrade / Fail / Health / DAT / Added.
 * Each is rendered when its `on_*` flag is true.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteNotification,
  useTestNotification,
  type Notification,
  type NotificationTestResult,
} from "@/lib/api/queries/notifications";

type EventKey =
  | "onGrab"
  | "onImport"
  | "onUpgrade"
  | "onFail"
  | "onHealthIssue"
  | "onDatUpdate"
  | "onGameAdded";

interface EventEntry {
  key: EventKey;
  enabled: boolean;
}

function eventEntries(n: Notification): EventEntry[] {
  return [
    { key: "onGrab", enabled: n.on_grab },
    { key: "onImport", enabled: n.on_import },
    { key: "onUpgrade", enabled: n.on_upgrade },
    { key: "onFail", enabled: n.on_fail },
    { key: "onHealthIssue", enabled: n.on_health_issue },
    { key: "onDatUpdate", enabled: n.on_dat_update },
    { key: "onGameAdded", enabled: n.on_game_added },
  ];
}

const STATUS_DOT: Record<"success" | "partial" | "failed" | "never", string> = {
  success: "bg-brand",
  partial: "bg-amber-500",
  failed: "bg-red-500",
  never: "bg-zinc-600",
};

function deriveStatus(
  n: Notification,
): "success" | "partial" | "failed" | "never" {
  if (n.last_status === "success") return "success";
  if (n.last_status === "partial") return "partial";
  if (n.last_status === "failed") return "failed";
  return "never";
}

interface NotificationRowProps {
  notification: Notification;
}

export function NotificationRow(props: NotificationRowProps): ReactElement {
  const { notification } = props;
  const { t } = useTranslation("settings");
  const test = useTestNotification();
  const del = useDeleteNotification();

  const [confirming, setConfirming] = useState(false);
  const [testResult, setTestResult] = useState<
    NotificationTestResult | null
  >(null);

  const status = deriveStatus(notification);

  function runTest(): void {
    setTestResult(null);
    test.mutate(notification.id, {
      onSuccess: (result) => setTestResult(result),
      onError: () => setTestResult(null),
    });
  }

  function confirmDelete(): void {
    del.mutate(notification.id);
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-1.5 inline-block h-2 w-2 rounded-full ${STATUS_DOT[status]}`}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {notification.name}
            </p>
            {!notification.enabled && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
                {t("connect.disabled")}
              </span>
            )}
          </div>
          <p className="truncate font-mono text-xs text-zinc-500">
            {notification.apprise_url_redacted}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              {t(`connect.lastStatus.${status}`)}
            </span>
            {eventEntries(notification)
              .filter((e) => e.enabled)
              .map((e) => (
                <span
                  key={e.key}
                  className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400"
                >
                  {t(`connect.events.${e.key}`)}
                </span>
              ))}
          </div>
        </div>
      </div>

      {testResult !== null && (
        <p
          className={`mt-2 text-xs ${
            testResult.success ? "text-zinc-400" : "text-red-400"
          }`}
          role={testResult.success ? undefined : "alert"}
        >
          {testResult.success
            ? `✓ ${t("connect.test.success")}`
            : `✗ ${
                testResult.error_message ?? t("connect.test.failure", { message: "" })
              }`}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={runTest}
          disabled={test.isPending}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {test.isPending
            ? t("connect.test.running")
            : t("connect.test.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {t("connect.delete.button")}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("connect.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("connect.delete.confirmBody", { name: notification.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("connect.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("connect.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
