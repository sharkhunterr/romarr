/**
 * Prowlarr applications panel (slice 119).
 *
 * Read-only roster of every registered Prowlarr instance.
 * Sits above the per-indexer list because the recommended
 * UX is "set up Prowlarr → it pushes indexers here" — the
 * panel makes the dependency visible at a glance.
 *
 * Admin-only; the page gates the fetch on the principal's
 * role to avoid noisy 403s for non-admin viewers.
 */

import { Plus } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useApplications,
  useDeleteApplication,
  type Application,
} from "@/lib/api/queries/applications";
import { useCurrentPrincipal } from "@/lib/api/queries/auth";

import { RegisterApplicationModal } from "./RegisterApplicationModal";

function formatDate(value: string | null, locale: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(locale);
}

function ApplicationRow(props: { app: Application }): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const { app } = props;
  const del = useDeleteApplication();
  const onUnregister = (): void => {
    if (
      typeof window !== "undefined" &&
      window.confirm(
        t("indexers.applications.unregisterConfirm", { name: app.name }),
      )
    ) {
      del.mutate(app.id);
    }
  };
  const tone = app.enabled
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-zinc-800 text-zinc-400 ring-zinc-700";
  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {app.name}
            </p>
            <span
              className={`rounded-full px-2 py-0.5 text-[0.6rem] font-medium uppercase tracking-wider ring-1 ring-inset ${tone}`}
            >
              {app.enabled
                ? t("indexers.applications.enabled")
                : t("indexers.applications.disabled")}
            </span>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-300">
              {t(`indexers.applications.syncLevel.${app.sync_level}`, {
                defaultValue: app.sync_level,
              })}
            </span>
          </div>
          <p className="truncate font-mono text-[0.65rem] text-zinc-500">
            {app.prowlarr_url}
          </p>
          <p className="text-[0.65rem] text-zinc-500">
            {t("indexers.applications.lastSync", {
              when: formatDate(app.last_sync_at, i18n.language),
            })}
          </p>
        </div>
        <button
          type="button"
          onClick={onUnregister}
          disabled={del.isPending}
          className={[
            "shrink-0 rounded-md border border-red-900/50 px-3 py-1",
            "text-xs font-medium text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {t("indexers.applications.unregister")}
        </button>
      </div>
    </li>
  );
}

export function ApplicationsPanel(): ReactElement | null {
  const { t } = useTranslation("settings");
  const principal = useCurrentPrincipal();
  const isAdmin = principal.data?.role === "admin";
  const apps = useApplications({ enabled: isAdmin });
  const [registerOpen, setRegisterOpen] = useState(false);

  if (!isAdmin) return null;

  return (
    <section className="space-y-3">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
          {t("indexers.applications.section")}
        </h3>
        <div className="flex items-center gap-2">
          <span className="rounded bg-brand/20 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-brand">
            {t("indexers.applications.adminOnly")}
          </span>
          <button
            type="button"
            onClick={() => setRegisterOpen(true)}
            className="inline-flex items-center gap-1 rounded-md border border-brand bg-brand px-2.5 py-1 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <Plus size={12} aria-hidden="true" />
            {t("indexers.applications.register.button")}
          </button>
        </div>
      </header>
      <p className="text-[0.7rem] text-zinc-500">
        {t("indexers.applications.subtitle")}
      </p>

      {apps.isLoading && <ListSkeleton rows={1} />}
      {apps.isError && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-red-300">
          {apps.error.message}
        </p>
      )}
      {apps.isSuccess && apps.data.length === 0 && (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("indexers.applications.empty")}
        </p>
      )}
      {apps.isSuccess && apps.data.length > 0 && (
        <ul className="space-y-2">
          {apps.data.map((app) => (
            <ApplicationRow key={app.id} app={app} />
          ))}
        </ul>
      )}

      {registerOpen && (
        <RegisterApplicationModal onClose={() => setRegisterOpen(false)} />
      )}
    </section>
  );
}
