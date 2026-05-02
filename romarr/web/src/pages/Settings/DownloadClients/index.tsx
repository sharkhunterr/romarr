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

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useDownloadClients } from "@/lib/api/queries/download-clients";

import { DownloadClientRow } from "./DownloadClientRow";

export function DownloadClientsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const clients = useDownloadClients();

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
        <ul className="space-y-2">
          {clients.data.map((client) => (
            <DownloadClientRow key={client.id} client={client} />
          ))}
        </ul>
      )}
    </div>
  );
}
