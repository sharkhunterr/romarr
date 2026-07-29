/**
 * Settings > General > About — running version + GitHub release
 * comparison. Radarr / Sonarr equivalent of "System > Status > About".
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useForceVersionCheck,
  useVersionCheck,
} from "@/lib/api/queries/version-check";

export function AboutSection(): ReactElement {
  const { t } = useTranslation("settings");
  const v = useVersionCheck();
  const forceCheck = useForceVersionCheck();

  return (
    <section className="space-y-2 rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
          {t("general.about.title", "À propos")}
        </h3>
        <button
          type="button"
          onClick={() => forceCheck.mutate()}
          disabled={forceCheck.isPending || v.isLoading}
          className="rounded-md border border-zinc-700 px-2 py-0.5 text-[0.65rem] text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {forceCheck.isPending
            ? t("general.about.checking", "Vérification…")
            : t("general.about.checkNow", "Vérifier maintenant")}
        </button>
      </div>

      {v.isLoading && (
        <p className="text-xs text-zinc-500">
          {t("general.about.loading", "Chargement…")}
        </p>
      )}

      {v.isSuccess && (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
          <dt className="text-zinc-500">
            {t("general.about.current", "Version installée")}
          </dt>
          <dd className="font-mono text-zinc-100">v{v.data.current}</dd>

          <dt className="text-zinc-500">
            {t("general.about.latest", "Dernière release GitHub")}
          </dt>
          <dd className="font-mono text-zinc-100">
            {v.data.latest ? `v${v.data.latest}` : "—"}
            {v.data.publishedAt && (
              <span className="ml-2 text-[0.65rem] text-zinc-500">
                (
                {new Date(v.data.publishedAt).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })}
                )
              </span>
            )}
          </dd>

          <dt className="text-zinc-500">
            {t("general.about.repo", "Dépôt")}
          </dt>
          <dd className="min-w-0 truncate">
            <a
              href={`https://github.com/${v.data.repo}`}
              target="_blank"
              rel="noreferrer"
              className="text-brand hover:underline"
            >
              {v.data.repo}
            </a>
          </dd>

          <dt className="text-zinc-500">
            {t("general.about.status", "Statut")}
          </dt>
          <dd>
            {v.data.error ? (
              <span className="text-amber-300">{v.data.error}</span>
            ) : v.data.updateAvailable ? (
              <a
                href={v.data.releaseUrl ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded border border-amber-700/50 bg-amber-950/40 px-2 py-0.5 text-[0.65rem] text-amber-300 hover:bg-amber-950/60"
              >
                {t("general.about.updateAvailable", "Mise à jour disponible")}
                {" · "}
                {t("general.about.viewRelease", "Voir la release")}
              </a>
            ) : (
              <span className="rounded bg-emerald-950/40 px-2 py-0.5 text-[0.65rem] text-emerald-300">
                {t("general.about.upToDate", "À jour")}
              </span>
            )}
          </dd>
        </dl>
      )}

      {v.isError && (
        <p className="text-xs text-red-400">{v.error.message}</p>
      )}
    </section>
  );
}
