/**
 * Settings → Logs page (slice 392).
 *
 * Sonarr-style live log viewer backed by the in-process ring
 * buffer (~2000 most recent records). Auto-refetches every 5 s
 * via :func:`useLogs`. Click a row to open a modal with the
 * full message + traceback.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useLogs,
  type LogEntry,
  type LogLevel,
} from "@/lib/api/queries/logs";

const LEVEL_OPTIONS: readonly { value: "" | LogLevel; labelKey: string }[] = [
  { value: "", labelKey: "logs.filters.all" },
  { value: "debug", labelKey: "logs.filters.debug" },
  { value: "info", labelKey: "logs.filters.info" },
  { value: "warn", labelKey: "logs.filters.warn" },
  { value: "error", labelKey: "logs.filters.error" },
];

const LEVEL_BADGE: Record<LogLevel, string> = {
  debug: "bg-zinc-700/40 text-zinc-300 ring-zinc-500/40",
  info: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
  warn: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  error: "bg-red-700/30 text-red-200 ring-red-500/40",
  fatal: "bg-fuchsia-700/30 text-fuchsia-100 ring-fuchsia-500/40",
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function LogsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const [level, setLevel] = useState<"" | LogLevel>("");
  const [loggerFilter, setLoggerFilter] = useState("");
  const [selected, setSelected] = useState<LogEntry | null>(null);

  const logs = useLogs({
    pageSize: 200,
    level: level || null,
    logger: loggerFilter || null,
  });

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <h2 className="font-mono text-sm font-semibold text-brand">
          {t("logs.title")}
        </h2>
        <p className="text-xs text-zinc-500">{t("logs.subtitle")}</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[0.65rem] uppercase tracking-widest text-zinc-500">
            {t("logs.filters.levelLabel")}
          </span>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as "" | LogLevel)}
            className="rounded-md bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-[0.65rem] uppercase tracking-widest text-zinc-500">
            {t("logs.filters.loggerLabel")}
          </span>
          <input
            type="search"
            value={loggerFilter}
            onChange={(e) => setLoggerFilter(e.target.value)}
            placeholder={t("logs.filters.loggerPlaceholder")}
            className="w-full rounded-md bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
        </label>
      </div>

      {logs.isPending ? (
        <ListSkeleton rows={8} />
      ) : logs.isError ? (
        <EmptyState
          title={t("logs.loadError")}
          description={logs.error.message}
        />
      ) : logs.data.records.length === 0 ? (
        <EmptyState
          title={t("logs.empty.title")}
          description={t("logs.empty.body")}
        />
      ) : (
        <ul className="divide-y divide-zinc-900 rounded-md border border-zinc-800 bg-zinc-900/30">
          {logs.data.records.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => setSelected(entry)}
                className="flex w-full items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-zinc-800/40 focus-visible:outline-none focus-visible:bg-zinc-800/60"
              >
                <span
                  className={[
                    "shrink-0 rounded-full px-2 py-0.5 text-[0.6rem]",
                    "font-medium uppercase ring-1 ring-inset",
                    LEVEL_BADGE[entry.level] ?? LEVEL_BADGE.info,
                  ].join(" ")}
                >
                  {entry.level}
                </span>
                <span className="shrink-0 font-mono text-[0.65rem] text-zinc-500">
                  {formatTime(entry.time)}
                </span>
                <span className="min-w-0 flex-1">
                  <p className="truncate text-xs text-zinc-100">
                    {entry.message}
                  </p>
                  <p className="truncate font-mono text-[0.65rem] text-zinc-500">
                    {entry.logger}
                  </p>
                </span>
                {entry.exception && (
                  <span className="shrink-0 rounded bg-red-900/30 px-1.5 py-0.5 text-[0.6rem] text-red-300">
                    {t("logs.hasTraceback")}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected !== null && (
        <LogDetailModal
          entry={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function LogDetailModal(props: {
  entry: LogEntry;
  onClose: () => void;
}): ReactElement {
  const { t } = useTranslation("settings");
  const { entry } = props;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("logs.detail.title")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-2xl overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-zinc-800 px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-zinc-100">
              {t("logs.detail.title")}
            </h2>
            <p className="mt-0.5 font-mono text-[0.65rem] text-zinc-500">
              {formatTime(entry.time)} · {entry.logger}
            </p>
          </div>
          <span
            className={[
              "shrink-0 rounded-full px-2 py-0.5 text-[0.6rem]",
              "font-medium uppercase ring-1 ring-inset",
              LEVEL_BADGE[entry.level] ?? LEVEL_BADGE.info,
            ].join(" ")}
          >
            {entry.level}
          </span>
        </header>
        <div className="max-h-[70vh] space-y-3 overflow-auto p-4">
          <section>
            <h3 className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("logs.detail.messageLabel")}
            </h3>
            <pre className="whitespace-pre-wrap break-words rounded bg-zinc-950 p-3 text-xs text-zinc-100">
              {entry.message}
            </pre>
          </section>
          {entry.exception && (
            <section>
              <h3 className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {entry.exceptionType
                  ? `${t("logs.detail.tracebackLabel")} — ${entry.exceptionType}`
                  : t("logs.detail.tracebackLabel")}
              </h3>
              <pre className="whitespace-pre-wrap break-words rounded bg-zinc-950 p-3 font-mono text-[0.7rem] text-red-200">
                {entry.exception}
              </pre>
            </section>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("logs.detail.close")}
          </button>
        </footer>
      </div>
    </div>
  );
}
