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
  useToggleNotification,
  type Notification,
  type NotificationTestResult,
  type ToggleNotificationVariables,
} from "@/lib/api/queries/notifications";

type ToggleField =
  | "enabled"
  | "on_grab"
  | "on_import"
  | "on_upgrade"
  | "on_fail"
  | "on_health_issue"
  | "on_dat_update"
  | "on_game_added";

const TOGGLE_LABEL: Record<ToggleField, string> = {
  enabled: "connect.toggle.enabled",
  on_grab: "connect.events.onGrab",
  on_import: "connect.events.onImport",
  on_upgrade: "connect.events.onUpgrade",
  on_fail: "connect.events.onFail",
  on_health_issue: "connect.events.onHealthIssue",
  on_dat_update: "connect.events.onDatUpdate",
  on_game_added: "connect.events.onGameAdded",
};

const EVENT_FIELDS: readonly ToggleField[] = [
  "on_grab",
  "on_import",
  "on_upgrade",
  "on_fail",
  "on_health_issue",
  "on_dat_update",
  "on_game_added",
];

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
  const toggle = useToggleNotification();

  const [confirming, setConfirming] = useState(false);
  const [testResult, setTestResult] = useState<
    NotificationTestResult | null
  >(null);

  const status = deriveStatus(notification);

  function flip(field: ToggleField): void {
    const variables: ToggleNotificationVariables = {
      id: notification.id,
      [field]: !notification[field],
    };
    toggle.mutate(variables);
  }

  function ToggleChip({ field }: { field: ToggleField }): ReactElement {
    const active = notification[field];
    return (
      <button
        type="button"
        onClick={() => flip(field)}
        disabled={toggle.isPending}
        aria-pressed={active}
        className={[
          "rounded px-1.5 py-0.5 text-[0.6rem] font-medium uppercase tracking-wider",
          "ring-1 ring-inset transition-colors",
          active
            ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
            : "bg-zinc-800 text-zinc-500 ring-zinc-700 hover:bg-zinc-700 hover:text-zinc-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-60",
        ].join(" ")}
      >
        {active ? "✓ " : ""}
        {t(TOGGLE_LABEL[field])}
      </button>
    );
  }

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
          </div>
          <p className="truncate font-mono text-xs text-zinc-500">
            {notification.apprise_url_redacted}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
              {t(`connect.lastStatus.${status}`)}
            </span>
            <ToggleChip field="enabled" />
            {EVENT_FIELDS.map((field) => (
              <ToggleChip key={field} field={field} />
            ))}
          </div>
          {toggle.isError && (
            <p className="text-[0.7rem] text-red-300">
              {toggle.error?.message ??
                t("connect.toggle.errorFallback")}
            </p>
          )}
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
