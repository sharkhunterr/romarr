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

import { Check, Copy, KeyRound, Plus } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useApplications,
  useDeleteApplication,
  useRotateApplicationToken,
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
  const rotate = useRotateApplicationToken();
  const [rotatedToken, setRotatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

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
  const onRotate = (): void => {
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        t("indexers.applications.rotateConfirm", { name: app.name }),
      )
    ) {
      return;
    }
    rotate.mutate(app.id, {
      onSuccess: (result) => setRotatedToken(result.app_token),
    });
  };
  const copyRotated = async (): Promise<void> => {
    if (!rotatedToken) return;
    try {
      await navigator.clipboard.writeText(rotatedToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked.
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
        <div className="flex shrink-0 flex-wrap gap-1.5">
          <button
            type="button"
            onClick={onRotate}
            disabled={rotate.isPending}
            className={[
              "inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1",
              "text-xs font-medium text-zinc-200 hover:bg-zinc-800",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            <KeyRound size={12} aria-hidden="true" />
            {rotate.isPending
              ? t("indexers.applications.rotating")
              : t("indexers.applications.rotate")}
          </button>
          <button
            type="button"
            onClick={onUnregister}
            disabled={del.isPending}
            className={[
              "rounded-md border border-red-900/50 px-3 py-1",
              "text-xs font-medium text-red-400 hover:bg-red-950/40",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            {t("indexers.applications.unregister")}
          </button>
        </div>
      </div>

      {rotatedToken && (
        <div className="mt-3 space-y-2 rounded-md border border-amber-900/60 bg-amber-950/30 p-3">
          <p className="text-xs font-medium text-amber-200">
            {t("indexers.applications.rotated.title")}
          </p>
          <p className="text-[0.65rem] text-amber-200/80">
            {t("indexers.applications.rotated.body")}
          </p>
          <div className="flex gap-1.5">
            <input
              type="text"
              readOnly
              value={rotatedToken}
              onFocus={(e) => e.target.select()}
              className="w-full flex-1 rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
            <button
              type="button"
              onClick={copyRotated}
              aria-label={t("indexers.applications.rotated.copy")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 text-zinc-200 hover:bg-zinc-900"
            >
              {copied ? (
                <Check size={14} className="text-brand" />
              ) : (
                <Copy size={14} />
              )}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setRotatedToken(null)}
            className="text-[0.65rem] text-zinc-400 hover:text-zinc-200 underline-offset-2 hover:underline"
          >
            {t("indexers.applications.rotated.dismiss")}
          </button>
        </div>
      )}
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
