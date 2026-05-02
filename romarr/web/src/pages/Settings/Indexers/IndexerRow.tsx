/**
 * One row in the Indexers list (slice 60).
 *
 * Shows name + url + source badge + per-feature pills (RSS /
 * Auto / Interactive) + a health dot. Two actions:
 *   * Test — POST /api/v3/indexer/{id}/test, surfaces inline.
 *   * Delete — DELETE /api/v3/indexer/{id} after a confirm.
 *
 * Health interpretation: when the row carries `last_health_at`
 * we trust it; otherwise the dot is muted ("not tested"). The
 * status enum follows the spec 005 ConnectivityTestResult
 * categories.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteIndexer,
  useTestIndexer,
  type Indexer,
  type IndexerTestResult,
} from "@/lib/api/queries/indexers";

type Health = "ok" | "auth" | "protocol" | "connectivity" | "circuit_open" | "untested";

function deriveHealth(indexer: Indexer): Health {
  if (indexer.last_health_at === null || indexer.last_health_at === undefined) {
    return "untested";
  }
  if (indexer.last_health_ok === true) {
    return "ok";
  }
  // last_health_error carries the category prefix when set;
  // the test endpoint also writes the category back. We fall
  // back to "connectivity" for any non-categorized failure.
  const error = indexer.last_health_error ?? "";
  if (error.includes("auth")) return "auth";
  if (error.includes("protocol")) return "protocol";
  if (error.includes("circuit")) return "circuit_open";
  return "connectivity";
}

const HEALTH_DOT: Record<Health, string> = {
  ok: "bg-brand",
  untested: "bg-zinc-600",
  auth: "bg-red-500",
  protocol: "bg-red-500",
  connectivity: "bg-amber-500",
  circuit_open: "bg-amber-500",
};

interface IndexerRowProps {
  indexer: Indexer;
}

export function IndexerRow(props: IndexerRowProps): ReactElement {
  const { indexer } = props;
  const { t } = useTranslation("settings");
  const test = useTestIndexer();
  const del = useDeleteIndexer();

  const [confirming, setConfirming] = useState(false);
  const [testResult, setTestResult] = useState<IndexerTestResult | null>(null);

  const health = deriveHealth(indexer);
  const sourceLabel = indexer.source === "prowlarr"
    ? t("indexers.source.prowlarr")
    : t("indexers.source.manual");

  function runTest(): void {
    setTestResult(null);
    test.mutate(indexer.id, {
      onSuccess: (result) => setTestResult(result),
      onError: () => setTestResult(null),
    });
  }

  function confirmDelete(): void {
    del.mutate(indexer.id);
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-1.5 inline-block h-2 w-2 rounded-full ${HEALTH_DOT[health]}`}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {indexer.name}
            </p>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
              {sourceLabel}
            </span>
          </div>
          <p className="truncate font-mono text-xs text-zinc-500">
            {indexer.url}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem] uppercase tracking-wider">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              {t(`indexers.health.${health}`)}
            </span>
            {indexer.enable_rss && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
                {t("indexers.rss")}
              </span>
            )}
            {indexer.enable_automatic_search && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
                {t("indexers.auto")}
              </span>
            )}
            {indexer.enable_interactive_search && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
                {t("indexers.interactive")}
              </span>
            )}
          </div>
        </div>
      </div>

      {testResult !== null && (
        <p className="mt-2 text-xs text-zinc-400">
          {testResult.ok
            ? `✓ ${t("indexers.test.successCaps")}${
                testResult.search_ok === true ? ` · ${t("indexers.test.successSearch")}` : ""
              }`
            : `✗ ${
                testResult.message ?? t(`indexers.health.${testResult.category ?? "connectivity"}`)
              }`}
        </p>
      )}
      {test.isError && (
        <p role="alert" className="mt-2 text-xs text-red-400">
          {t("indexers.test.failure", {
            message: test.error?.message ?? "",
          })}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={runTest}
          disabled={test.isPending}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {test.isPending ? t("indexers.test.running") : t("indexers.test.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {t("indexers.delete.button")}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("indexers.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("indexers.delete.confirmBody", { name: indexer.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("indexers.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("indexers.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
