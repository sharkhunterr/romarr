/**
 * Settings > Connect — Notifications (slice 62).
 *
 * Operator-facing list of every Apprise notification target
 * Romarr can route events through. The MVP slice ships:
 *   * GET /api/v3/notification — list with redacted URLs.
 *   * POST /api/v3/notification/{id}/test — synthetic OnImport.
 *   * DELETE /api/v3/notification/{id} — admin-only removal.
 *
 * Add-new + edit forms are deferred. NotificationCreate
 * carries the URL + 7 event toggles + 7 optional Jinja
 * templates and the canonical UX is a 3-step modal.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useNotifications } from "@/lib/api/queries/notifications";

import { NotificationRow } from "./NotificationRow";

export function ConnectPage(): ReactElement {
  const { t } = useTranslation("settings");
  const notifications = useNotifications();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("connect.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{t("connect.subtitle")}</p>
      </header>

      {notifications.isLoading && <ListSkeleton rows={3} />}
      {notifications.isError && (
        <EmptyState
          title={t("connect.empty.title")}
          description={notifications.error.message}
        />
      )}
      {notifications.isSuccess && notifications.data.length === 0 && (
        <EmptyState
          title={t("connect.empty.title")}
          description={t("connect.empty.body")}
        />
      )}
      {notifications.isSuccess && notifications.data.length > 0 && (
        <ul className="space-y-2">
          {notifications.data.map((n) => (
            <NotificationRow key={n.id} notification={n} />
          ))}
        </ul>
      )}
    </div>
  );
}
