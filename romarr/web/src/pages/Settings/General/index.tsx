/**
 * Settings > General (slice 106).
 *
 * Today's slice ships the per-user API-key surface against
 * spec 010's `/api/v3/auth/api-key` endpoints. The richer
 * "operator account" page (password change, OIDC unlink, login
 * history) lands once those endpoints surface.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useApiKeys } from "@/lib/api/queries/api-keys";

import { ApiKeyRow } from "./ApiKeyRow";
import { CreateApiKeyForm } from "./CreateApiKeyForm";

export function GeneralPage(): ReactElement {
  const { t } = useTranslation("settings");
  const apiKeys = useApiKeys();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("general.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{t("general.subtitle")}</p>
      </header>

      <section className="space-y-3">
        <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
          {t("general.apiKeys.section")}
        </h3>

        <CreateApiKeyForm />

        {apiKeys.isLoading && <ListSkeleton rows={2} />}
        {apiKeys.isError && (
          <EmptyState
            title={t("general.apiKeys.empty.title")}
            description={apiKeys.error.message}
          />
        )}
        {apiKeys.isSuccess && apiKeys.data.length === 0 && (
          <EmptyState
            title={t("general.apiKeys.empty.title")}
            description={t("general.apiKeys.empty.body")}
          />
        )}
        {apiKeys.isSuccess && apiKeys.data.length > 0 && (
          <ul className="space-y-2">
            {apiKeys.data.map((apiKey) => (
              <ApiKeyRow key={apiKey.id} apiKey={apiKey} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
