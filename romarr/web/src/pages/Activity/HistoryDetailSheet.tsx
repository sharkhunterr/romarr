/**
 * History detail sheet.
 *
 * Renders the operator-facing detail panel for a single history
 * row when the operator clicks it in the list. The list row is
 * intentionally terse (one line per event); this sheet surfaces
 * everything else the API ships: score breakdown, indexer GUID,
 * download client, import paths, correlation id, full timestamps.
 *
 * Built on top of :class:`ActionSheet` (the bottom-anchored mobile
 * dialog) so the visual language matches the rest of the app and
 * we don't pull in a second modal primitive.
 */

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";

import { ActionSheet } from "@/components/shared/ActionSheet";
import type { components } from "@/types/api/schema";

type HistoryEvent = components["schemas"]["HistoryEvent"];

interface ScoreContribution {
  source?: string;
  name?: string;
  value?: number;
  [key: string]: unknown;
}

interface HistoryDetailSheetProps {
  event: HistoryEvent | null;
  onClose: () => void;
  locale: string;
}

function _formatDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale);
}

function _formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = s / 60;
  if (m < 60) return `${m.toFixed(1)} min`;
  const h = m / 60;
  return `${h.toFixed(1)} h`;
}

interface DetailRowProps {
  label: string;
  children: ReactElement | string | number | null | undefined;
  mono?: boolean;
}

function DetailRow(props: DetailRowProps): ReactElement | null {
  const { label, children, mono } = props;
  if (children === null || children === undefined || children === "") {
    return null;
  }
  return (
    <div className="flex items-baseline gap-2 py-1 text-xs">
      <dt className="w-32 shrink-0 text-zinc-500">{label}</dt>
      <dd
        className={
          mono
            ? "min-w-0 flex-1 break-all font-mono text-zinc-200"
            : "min-w-0 flex-1 break-words text-zinc-200"
        }
      >
        {children}
      </dd>
    </div>
  );
}

export function HistoryDetailSheet(
  props: HistoryDetailSheetProps,
): ReactElement | null {
  const { event, onClose, locale } = props;
  const { t } = useTranslation("activity");
  const open = event !== null;

  if (event === null) {
    // Closed state — render nothing. The ActionSheet primitive's
    // own internal ``open=false`` guard early-returns null too,
    // but it requires a ``children`` prop we don't have anything
    // to put inside when there's no event selected.
    return null;
  }

  const isSearch = event.eventType === "search";
  const isImport = event.eventType === "import";
  const isJobRun = event.eventType === "job_run";
  const summaryEntries: Array<[string, unknown]> =
    event.outputSummary && typeof event.outputSummary === "object"
      ? Object.entries(event.outputSummary as Record<string, unknown>)
      : [];

  // Translate the reason same way HistoryRow does — split
  // "code: detail" so the head goes through ``history.noGrabReason.<code>``
  // and the tail is rendered verbatim.
  const reasonRendered = ((): string | null => {
    if (!event.reason) return null;
    const idx = event.reason.indexOf(": ");
    const code = idx >= 0 ? event.reason.slice(0, idx) : event.reason;
    const tail = idx >= 0 ? event.reason.slice(idx + 2) : "";
    const label = t(`history.noGrabReason.${code}`, { defaultValue: code });
    return tail ? `${label} — ${tail}` : label;
  })();

  const breakdown: ScoreContribution[] = Array.isArray(event.scoreBreakdown)
    ? (event.scoreBreakdown as ScoreContribution[])
    : [];

  const headerLabel =
    isSearch && event.summary
      ? t(`history.searchType.${event.summary}`, { defaultValue: event.summary })
      : t(`history.eventLabel.${event.eventType}`, {
          defaultValue: event.eventType,
        });

  return (
    <ActionSheet
      open={open}
      onClose={onClose}
      ariaLabel={t("history.detail.title", { defaultValue: "Event detail" })}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-800 pb-2">
          <span className="font-mono text-[0.65rem] uppercase tracking-wider text-zinc-400">
            {headerLabel}
          </span>
          <span
            className={[
              "rounded-full px-2 py-0.5 text-[0.65rem] font-medium ring-1 ring-inset",
              event.successful
                ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
                : "bg-red-700/30 text-red-200 ring-red-500/40",
            ].join(" ")}
          >
            {event.successful
              ? t("history.statusOk")
              : t("history.statusFailed")}
          </span>
        </div>

        {/* ---- Subject + when -------------------------------------- */}
        <dl className="space-y-0">
          <DetailRow label={t("history.detail.dateLabel", { defaultValue: "Date" })}>
            {_formatDate(event.date, locale)}
          </DetailRow>
          {event.finishedAt && (
            <DetailRow
              label={t("history.detail.finishedLabel", {
                defaultValue: "Finished",
              })}
            >
              {_formatDate(event.finishedAt, locale)}
            </DetailRow>
          )}
          <DetailRow
            label={t("history.detail.durationLabel", {
              defaultValue: "Duration",
            })}
          >
            {_formatDuration(event.durationMs)}
          </DetailRow>

          {event.gameTitle && event.gameId && (
            <DetailRow
              label={t("history.detail.gameLabel", { defaultValue: "Game" })}
            >
              <Link
                to={`/game/${event.gameId}`}
                onClick={onClose}
                className="text-brand hover:underline"
              >
                {event.gameTitle}
              </Link>
            </DetailRow>
          )}
          {event.gameId && !event.gameTitle && (
            <DetailRow
              label={t("history.detail.gameLabel", { defaultValue: "Game" })}
            >
              {t("history.subjectGame", { id: event.gameId })}
            </DetailRow>
          )}
          {event.releaseId && (
            <DetailRow
              label={t("history.detail.releaseLabel", {
                defaultValue: "Release",
              })}
            >
              {`#${event.releaseId}`}
            </DetailRow>
          )}
        </dl>

        {/* ---- Search-specific ------------------------------------- */}
        {isSearch && (
          <dl className="space-y-0">
            {event.query && (
              <DetailRow label={t("history.detail.query")} mono>
                {event.query}
              </DetailRow>
            )}
            {(event.score !== null && event.score !== undefined) && (
              <DetailRow label={t("history.detail.score")} mono>
                {event.score}
              </DetailRow>
            )}
            {event.chosenIndexerGuid && (
              <DetailRow label={t("history.detail.guid")} mono>
                {event.chosenIndexerGuid}
              </DetailRow>
            )}
          </dl>
        )}

        {/* ---- Score breakdown ------------------------------------- */}
        {breakdown.length > 0 && (
          <div>
            <h4 className="mb-1 text-[0.65rem] font-medium uppercase tracking-wider text-zinc-500">
              {t("history.detail.breakdown", {
                defaultValue: "Score breakdown",
              })}
            </h4>
            <div className="overflow-hidden rounded border border-zinc-800">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-zinc-900/60 text-[0.65rem] uppercase text-zinc-500">
                    <th className="px-2 py-1 text-left font-medium">
                      {t("history.detail.contributionSource", {
                        defaultValue: "Source",
                      })}
                    </th>
                    <th className="px-2 py-1 text-left font-medium">
                      {t("history.detail.contributionName", {
                        defaultValue: "Rule",
                      })}
                    </th>
                    <th className="px-2 py-1 text-right font-medium">
                      {t("history.detail.contributionValue", {
                        defaultValue: "+/-",
                      })}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map((c, i) => (
                    <tr key={i} className="border-t border-zinc-800/60">
                      <td className="px-2 py-1 text-zinc-400">
                        {c.source ?? "—"}
                      </td>
                      <td className="px-2 py-1 text-zinc-200">
                        {c.name ?? "—"}
                      </td>
                      <td
                        className={[
                          "px-2 py-1 text-right font-mono",
                          (c.value ?? 0) > 0
                            ? "text-emerald-300"
                            : (c.value ?? 0) < 0
                              ? "text-red-300"
                              : "text-zinc-400",
                        ].join(" ")}
                      >
                        {(c.value ?? 0) > 0
                          ? `+${c.value}`
                          : (c.value ?? 0).toString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ---- Job-run summary ------------------------------------- */}
        {/* Free-form k/v dict the runner populates (RssSync,
            RescanLibrary, …). Render as a small two-column table so
            "candidates: 1834 · grabs_dispatched: 4" reads cleanly. */}
        {isJobRun && summaryEntries.length > 0 && (
          <div>
            <h4 className="mb-1 text-[0.65rem] font-medium uppercase tracking-wider text-zinc-500">
              {t("history.detail.summary", {
                defaultValue: "Summary",
              })}
            </h4>
            <div className="overflow-hidden rounded border border-zinc-800">
              <table className="w-full text-xs">
                <tbody>
                  {summaryEntries.map(([k, v]) => (
                    <tr key={k} className="border-t border-zinc-800/60 first:border-t-0">
                      <td className="px-2 py-1 text-zinc-500">
                        {t(`history.outputSummary.${k}`, { defaultValue: k })}
                      </td>
                      <td className="px-2 py-1 text-right font-mono text-zinc-200">
                        {typeof v === "object" && v !== null
                          ? JSON.stringify(v)
                          : String(v)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ---- Import-specific ------------------------------------- */}
        {isImport && (
          <dl className="space-y-0">
            {event.destPath && (
              <DetailRow label={t("history.detail.dest")} mono>
                {event.destPath}
              </DetailRow>
            )}
            {event.summary && (
              <DetailRow label={t("history.detail.source")} mono>
                {event.summary}
              </DetailRow>
            )}
            {event.downloadClientName && (
              <DetailRow label={t("history.detail.client")}>
                {event.downloadClientName}
              </DetailRow>
            )}
            {event.importedVia && (
              <DetailRow label={t("history.detail.via")}>
                {t(`history.importedVia.${event.importedVia}`, {
                  defaultValue: event.importedVia,
                })}
              </DetailRow>
            )}
          </dl>
        )}

        {/* ---- Reason (red, last) ---------------------------------- */}
        {reasonRendered && (
          <div className="rounded border border-red-900/50 bg-red-950/20 px-2 py-1.5">
            <p className="text-xs text-red-300">
              <span className="text-red-500/70">
                {t("history.detail.reason")}:{" "}
              </span>
              {reasonRendered}
            </p>
          </div>
        )}

        {/* ---- Correlation id (foldable footer) -------------------- */}
        {event.correlationId && (
          <p className="border-t border-zinc-800 pt-2 text-[0.65rem] text-zinc-600">
            <span className="text-zinc-500">
              {t("history.detail.correlationLabel", {
                defaultValue: "Round",
              })}
              :{" "}
            </span>
            <span className="font-mono">{event.correlationId}</span>
          </p>
        )}
      </div>
    </ActionSheet>
  );
}
