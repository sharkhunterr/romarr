/**
 * Romarr system version card — sits at the top of the Update Center
 * page so every "am I up to date?" question lives in one place.
 *
 * Backend call chain :
 *   * ``useVersionCheck`` — cached 1h backend + 30min client. Fast,
 *     may be slightly stale.
 *   * ``useForceVersionCheck`` — POSTs with ``force=true`` to bypass
 *     both caches. Wired to the "Vérifier maintenant" button so a
 *     freshly-published upstream release is picked up on demand.
 */

import { CheckCircle2, ExternalLink, RefreshCw } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useForceVersionCheck,
  useVersionCheck,
} from "@/lib/api/queries/version-check";
import { useToastStore } from "@/lib/store/toast";

export function SystemVersionCard(): ReactElement {
  const { t } = useTranslation("settings");
  const v = useVersionCheck();
  const force = useForceVersionCheck();
  const pushToast = useToastStore((s) => s.push);

  function checkNow(): void {
    force.mutate(undefined, {
      onSuccess: (data) => {
        pushToast({
          kind: data.updateAvailable ? "info" : "success",
          title: data.updateAvailable
            ? t("updateCenter.systemUpdateAvailableTitle")
            : t("updateCenter.systemUpToDateTitle"),
          description: data.updateAvailable
            ? t("updateCenter.systemUpdateAvailableBody", {
                current: data.current,
                latest: data.latest,
              })
            : t("updateCenter.systemUpToDateBody", { version: data.current }),
        });
      },
      onError: (err) =>
        pushToast({
          kind: "error",
          title: t("updateCenter.systemCheckErrorTitle"),
          description: err.message,
        }),
    });
  }

  const data = v.data;
  const isUpdateAvailable = data?.updateAvailable ?? false;
  const hasError = data?.error;
  const isBusy = v.isPending || force.isPending;

  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-zinc-100">
            {t("updateCenter.systemCardTitle")}
          </h3>
          <p className="mt-0.5 text-[0.7rem] text-zinc-500">
            {t("updateCenter.systemCardSubtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={checkNow}
          disabled={isBusy}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-[0.7rem] font-medium text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw
            size={12}
            className={force.isPending ? "animate-spin" : ""}
            aria-hidden="true"
          />
          {force.isPending
            ? t("updateCenter.systemChecking")
            : t("updateCenter.systemCheckNow")}
        </button>
      </header>

      {v.isPending && (
        <p className="mt-3 text-xs text-zinc-500">
          {t("updateCenter.systemLoading")}
        </p>
      )}

      {v.isError && (
        <p role="alert" className="mt-3 text-xs text-red-400">
          {v.error.message}
        </p>
      )}

      {data && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {/* Installed */}
          <span className="inline-flex items-center gap-1.5 rounded border border-zinc-700 bg-zinc-900/60 px-2 py-0.5 text-[0.7rem]">
            <span className="text-zinc-500">
              {t("updateCenter.systemInstalled")}
            </span>
            <span className="font-mono font-semibold text-zinc-100">
              v{data.current}
            </span>
          </span>

          {/* Status pill */}
          {hasError ? (
            <span className="rounded border border-red-800/60 bg-red-950/40 px-2 py-0.5 text-[0.7rem] text-red-300">
              {data.error}
            </span>
          ) : isUpdateAvailable ? (
            <a
              href={data.releaseUrl ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded border border-amber-700/60 bg-amber-950/40 px-2 py-0.5 text-[0.7rem] text-amber-300 hover:bg-amber-950/60"
              title={t("updateCenter.systemViewReleaseTooltip")}
            >
              <span className="font-mono text-amber-400 line-through decoration-amber-700">
                v{data.current}
              </span>
              <span aria-hidden="true">→</span>
              <span className="font-mono font-semibold">v{data.latest}</span>
              <ExternalLink size={11} aria-hidden="true" />
            </a>
          ) : (
            <span className="inline-flex items-center gap-1 rounded border border-emerald-800/50 bg-emerald-950/30 px-2 py-0.5 text-[0.7rem] text-emerald-300">
              <CheckCircle2 size={12} aria-hidden="true" />
              {t("updateCenter.systemUpToDate")}
            </span>
          )}

          {/* Repo link */}
          {data.repo && (
            <a
              href={`https://github.com/${data.repo}`}
              target="_blank"
              rel="noreferrer"
              className="text-[0.65rem] text-zinc-500 hover:text-zinc-300 hover:underline"
            >
              {data.repo}
            </a>
          )}
        </div>
      )}

      {data?.publishedAt && (
        <p className="mt-2 text-[0.65rem] text-zinc-500">
          {t("updateCenter.systemPublishedAt", {
            date: new Date(data.publishedAt).toLocaleString(),
          })}
        </p>
      )}
    </section>
  );
}
