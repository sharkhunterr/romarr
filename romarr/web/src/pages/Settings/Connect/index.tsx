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

import { useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useNotifications } from "@/lib/api/queries/notifications";

import { NotificationRow } from "./NotificationRow";

export function ConnectPage(): ReactElement {
  const { t } = useTranslation("settings");
  const notifications = useNotifications();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawQuery = searchParams.get("q") ?? "";
  const queryNormalized = rawQuery.trim().toLowerCase();

  const setQuery = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next.trim() === "") params.delete("q");
        else params.set("q", next);
        return params;
      },
      { replace: true },
    );
  };

  const filtered = useMemo(() => {
    if (!notifications.data) return [];
    if (queryNormalized.length === 0) return notifications.data;
    return notifications.data.filter(
      (n) =>
        n.name.toLowerCase().includes(queryNormalized) ||
        n.apprise_url_redacted.toLowerCase().includes(queryNormalized),
    );
  }, [notifications.data, queryNormalized]);

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
        <>
          <label className="block">
            <span className="sr-only">{t("connect.search.label")}</span>
            <input
              type="search"
              value={rawQuery}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("connect.search.placeholder")}
              aria-label={t("connect.search.label")}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>
          {filtered.length === 0 ? (
            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
              {t("connect.search.noMatches")}
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((n) => (
                <NotificationRow key={n.id} notification={n} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
