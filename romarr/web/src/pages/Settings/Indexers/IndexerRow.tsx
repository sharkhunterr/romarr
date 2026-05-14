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

import { Pencil } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { CreateIndexerModal } from "./CreateIndexerModal";

import {
  useDeleteIndexer,
  useTestIndexer,
  useToggleIndexer,
  type Indexer,
  type IndexerTestResult,
  type ToggleIndexerVariables,
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

type ToggleField =
  | "enabled"
  | "enable_rss"
  | "enable_automatic_search"
  | "enable_interactive_search";

const TOGGLE_LABELS: Record<ToggleField, string> = {
  // Slice 432 — master kill-switch label. When off the indexer
  // is excluded from every search round / RSS poll / grab.
  enabled: "indexers.toggle.enabled",
  enable_rss: "indexers.rss",
  enable_automatic_search: "indexers.auto",
  enable_interactive_search: "indexers.interactive",
};

export function IndexerRow(props: IndexerRowProps): ReactElement {
  const { indexer } = props;
  const { t } = useTranslation("settings");
  const test = useTestIndexer();
  const del = useDeleteIndexer();
  const toggle = useToggleIndexer();

  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<IndexerTestResult | null>(null);

  const health = deriveHealth(indexer);
  const sourceLabel = indexer.source === "prowlarr"
    ? t("indexers.source.prowlarr")
    : t("indexers.source.manual");

  function flip(field: ToggleField): void {
    const variables: ToggleIndexerVariables = {
      id: indexer.id,
      [field]: !indexer[field],
    };
    toggle.mutate(variables);
  }

  function ToggleChip({ field }: { field: ToggleField }): ReactElement {
    const active = indexer[field];
    return (
      <button
        type="button"
        onClick={() => flip(field)}
        disabled={toggle.isPending}
        aria-pressed={active}
        className={[
          "rounded px-1.5 py-0.5 text-[0.6rem] font-medium uppercase tracking-wider",
          "ring-1 ring-inset transition-colors",
          active
            ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
            : "bg-zinc-800 text-zinc-500 ring-zinc-700 hover:bg-zinc-700 hover:text-zinc-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-60",
        ].join(" ")}
      >
        {active ? "✓ " : ""}
        {t(TOGGLE_LABELS[field])}
      </button>
    );
  }

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
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
              {t(`indexers.health.${health}`)}
            </span>
            <ToggleChip field="enabled" />
            <ToggleChip field="enable_rss" />
            <ToggleChip field="enable_automatic_search" />
            <ToggleChip field="enable_interactive_search" />
          </div>
          {toggle.isError && (
            <p className="text-[0.7rem] text-red-300">
              {toggle.error?.message ??
                t("indexers.toggle.errorFallback")}
            </p>
          )}
        </div>
      </div>

      {testResult !== null && (
        <div
          className={[
            "mt-2 space-y-1 text-xs",
            testResult.ok ? "text-zinc-400" : "text-red-300",
          ].join(" ")}
        >
          <p>
            {testResult.ok
              ? `✓ ${t("indexers.test.successCaps")}${
                  testResult.search_ok === true
                    ? ` · ${t("indexers.test.successSearch")}`
                    : ""
                }`
              : `✗ ${
                  testResult.message ??
                  t(`indexers.health.${testResult.category ?? "connectivity"}`)
                }`}
          </p>
          {!testResult.ok &&
            (testResult.message ?? "")
              .toLowerCase()
              .includes("caps response was empty") && (
              <p className="rounded-md bg-amber-950/40 px-2 py-1 text-[0.7rem] text-amber-200">
                {t("indexers.test.emptyCapsHint")}
              </p>
            )}
        </div>
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
          onClick={() => flip("enabled")}
          disabled={toggle.isPending}
          aria-pressed={indexer.enabled}
          className={[
            "min-h-[36px] rounded-md px-3 text-xs font-medium",
            indexer.enabled
              ? "border border-zinc-700 bg-brand/15 text-brand hover:bg-brand/25"
              : "border border-zinc-700 bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {indexer.enabled
            ? t("indexers.action.disable")
            : t("indexers.action.enable")}
        </button>
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
          onClick={() => setEditing(true)}
          className={[
            "inline-flex min-h-[36px] items-center gap-1 rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          <Pencil size={12} aria-hidden="true" />
          {t("indexers.edit.button")}
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

      {editing && (
        <CreateIndexerModal
          indexer={indexer}
          onClose={() => setEditing(false)}
        />
      )}

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
