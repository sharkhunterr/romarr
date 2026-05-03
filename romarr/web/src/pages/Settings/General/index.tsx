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
import { useCurrentPrincipal } from "@/lib/api/queries/auth";
import { useUsers } from "@/lib/api/queries/users";

import { ApiKeyRow } from "./ApiKeyRow";
import { CreateApiKeyForm } from "./CreateApiKeyForm";
import { CreateUserForm } from "./CreateUserForm";
import { UserRow } from "./UserRow";

export function GeneralPage(): ReactElement {
  const { t } = useTranslation("settings");
  const apiKeys = useApiKeys();
  const principal = useCurrentPrincipal();
  const isAdmin = principal.data?.role === "admin";
  const users = useUsers({ enabled: isAdmin });

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

      {isAdmin && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
              {t("general.users.section")}
            </h3>
            <span className="rounded bg-brand/20 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-brand">
              {t("general.users.adminOnly")}
            </span>
          </div>
          <p className="text-[0.7rem] text-zinc-500">
            {t("general.users.subtitle")}
          </p>

          <CreateUserForm />

          {users.isLoading && <ListSkeleton rows={2} />}
          {users.isError && (
            <EmptyState
              title={t("general.users.empty.title")}
              description={users.error.message}
            />
          )}
          {users.isSuccess && users.data.length === 0 && (
            <EmptyState
              title={t("general.users.empty.title")}
              description={t("general.users.empty.body")}
            />
          )}
          {users.isSuccess && users.data.length > 0 && (
            <ul className="space-y-2">
              {users.data.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  isSelf={user.id === principal.data?.id}
                />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
