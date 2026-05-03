/**
 * Settings > Download Clients (slice 61).
 *
 * Operator-facing list of every torrent + usenet client
 * Romarr can hand grabs to. The MVP slice ships:
 *   * GET /api/v3/downloadclient — full list with health.
 *   * POST /api/v3/downloadclient/{id}/test — connectivity probe.
 *   * DELETE /api/v3/downloadclient/{id} — admin-only removal.
 *
 * Add-new + edit forms are deferred for the same reason
 * Indexers' are: DownloadClientCreate carries many required
 * fields and the per-type schema (qBittorrent / SABnzbd /
 * Transmission / Deluge / NZBGet) drives a multi-step form
 * worth a dedicated slice.
 */

import { useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useDownloadClients } from "@/lib/api/queries/download-clients";

import { DownloadClientRow } from "./DownloadClientRow";

export function DownloadClientsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const clients = useDownloadClients();
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
    if (!clients.data) return [];
    if (queryNormalized.length === 0) return clients.data;
    return clients.data.filter(
      (client) =>
        client.name.toLowerCase().includes(queryNormalized) ||
        client.host.toLowerCase().includes(queryNormalized),
    );
  }, [clients.data, queryNormalized]);

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("downloadClients.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("downloadClients.subtitle")}
        </p>
      </header>

      {clients.isLoading && <ListSkeleton rows={3} />}
      {clients.isError && (
        <EmptyState
          title={t("downloadClients.empty.title")}
          description={clients.error.message}
        />
      )}
      {clients.isSuccess && clients.data.length === 0 && (
        <EmptyState
          title={t("downloadClients.empty.title")}
          description={t("downloadClients.empty.body")}
        />
      )}
      {clients.isSuccess && clients.data.length > 0 && (
        <>
          <label className="block">
            <span className="sr-only">{t("downloadClients.search.label")}</span>
            <input
              type="search"
              value={rawQuery}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("downloadClients.search.placeholder")}
              aria-label={t("downloadClients.search.label")}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>
          {filtered.length === 0 ? (
            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
              {t("downloadClients.search.noMatches")}
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((client) => (
                <DownloadClientRow key={client.id} client={client} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
