/**
 * Single Platform Pack row (slice 93).
 *
 * Read-only audit pill set:
 *   * pack version + source pill (builtin / community / user)
 *   * applied_at (locale-formatted date), applied_by
 *   * schema version, contents_hash (truncated, monospace)
 *
 * Clicking the row toggles a detail accordion that fires
 * `usePlatformPack(version)` to load the per-pack history
 * (PlatformPackApplicationLog rows) lazily.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  usePlatformPack,
  type PackHistoryRow,
  type PackSummary,
} from "@/lib/api/queries/platform-packs";

interface RowProps {
  pack: PackSummary;
}

function SourcePill(props: { source: string }): ReactElement {
  const { t } = useTranslation("settings");
  const tone =
    props.source === "builtin"
      ? "bg-emerald-950/40 text-emerald-400"
      : props.source === "community"
        ? "bg-blue-950/40 text-blue-400"
        : "bg-amber-950/40 text-amber-400";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider ${tone}`}
    >
      {t(`platforms.source.${props.source}`, { defaultValue: props.source })}
    </span>
  );
}

function HistoryRow(props: { row: PackHistoryRow }): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const { row } = props;
  const startedAt = new Date(row.started_at);
  const tone =
    row.status === "applied" || row.status === "reapplied"
      ? "text-emerald-400"
      : row.status === "skipped"
        ? "text-zinc-400"
        : "text-red-400";
  return (
    <li className="flex flex-col gap-0.5 rounded border border-zinc-800 bg-zinc-950/40 p-2 text-[0.7rem]">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`font-mono uppercase tracking-wider ${tone}`}>
          {t(`platforms.action.${row.action}`, { defaultValue: row.action })}
        </span>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-300">
          {startedAt.toLocaleString(i18n.language)}
        </span>
        {row.applied_by && (
          <>
            <span className="text-zinc-500">·</span>
            <span className="text-zinc-400">{row.applied_by}</span>
          </>
        )}
      </div>
      {row.platforms_affected.length > 0 && (
        <p className="text-zinc-500">
          {t("platforms.history.platformsAffected", {
            count: row.platforms_affected.length,
          })}
          : {row.platforms_affected.join(", ")}
        </p>
      )}
      {row.error_message && (
        <p className="text-red-400">{row.error_message}</p>
      )}
    </li>
  );
}

export function PackRow(props: RowProps): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const { pack } = props;
  const [expanded, setExpanded] = useState(false);
  const detail = usePlatformPack(expanded ? pack.pack_version : null);
  const appliedAt = new Date(pack.applied_at);
  const shortHash = pack.contents_hash.slice(0, 12);

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full flex-col gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-mono text-sm font-medium text-zinc-100">
            {pack.pack_version}
          </p>
          <SourcePill source={pack.pack_source} />
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-400">
            v{pack.schema_version}
          </span>
        </div>

        {pack.description && (
          <p className="text-xs text-zinc-400">{pack.description}</p>
        )}

        <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-500">
          <span>{appliedAt.toLocaleString(i18n.language)}</span>
          <span>·</span>
          <span>
            {t("platforms.appliedBy", { user: pack.applied_by })}
          </span>
          {pack.author && (
            <>
              <span>·</span>
              <span>{t("platforms.author", { author: pack.author })}</span>
            </>
          )}
          <span>·</span>
          <span className="font-mono" title={pack.contents_hash}>
            sha256:{shortHash}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2 border-t border-zinc-800 pt-3">
          {detail.isLoading && (
            <p className="text-[0.7rem] text-zinc-500">
              {t("platforms.history.loading")}
            </p>
          )}
          {detail.isError && (
            <p className="text-[0.7rem] text-red-400">
              {detail.error.message}
            </p>
          )}
          {detail.isSuccess && (
            <>
              {detail.data.source_url && (
                <p className="break-all text-[0.65rem] text-zinc-500">
                  {t("platforms.sourceUrl")}:{" "}
                  <a
                    href={detail.data.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand underline"
                  >
                    {detail.data.source_url}
                  </a>
                </p>
              )}
              <p className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
                {t("platforms.history.title")}
              </p>
              {detail.data.history && detail.data.history.length > 0 ? (
                <ul className="space-y-1">
                  {detail.data.history.map((row) => (
                    <HistoryRow key={row.id} row={row} />
                  ))}
                </ul>
              ) : (
                <p className="text-[0.7rem] text-zinc-500">
                  {t("platforms.history.empty")}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}
