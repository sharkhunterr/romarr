/**
 * Per-release manual-search + grab modal (slice 102).
 *
 * Triggered from the Releases tab "Search" button. Runs the
 * spec 007 manual-search round (admin only) and lists every
 * candidate; the operator picks one to dispatch via the
 * companion manual-grab endpoint.
 *
 * The search round shows everything — winners, rejected,
 * would-auto-reject — so the operator can override the gates
 * when needed (the `force` toggle on Grab bypasses the
 * blocklist gate per FR-022).
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useIndexersById } from "@/lib/api/queries/indexers";
import {
  useManualGrab,
  useManualSearch,
  type Candidate,
} from "@/lib/api/queries/search";

interface ReleaseSearchModalProps {
  open: boolean;
  onClose: () => void;
  /** Initial query — typically the Release.name. */
  initialQuery: string;
  /** Pinned to the game's platform so the search builder uses
   * the right newznab category set. */
  platformId: number;
  /** Pre-bound to the candidate via /grab so import-time can
   * resolve the right Release without a re-match. */
  releaseId: number;
}

function formatBytes(bytes: number | null | undefined): string | null {
  if (bytes === null || bytes === undefined || bytes === 0) return null;
  const k = 1024;
  const sizes = ["B", "KiB", "MiB", "GiB", "TiB"];
  const i = Math.min(
    sizes.length - 1,
    Math.floor(Math.log(bytes) / Math.log(k)),
  );
  return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 2)} ${sizes[i]}`;
}

function CandidateRow(props: {
  candidate: Candidate;
  releaseId: number;
  force: boolean;
  indexerName: string | null;
  onGrabSuccess: () => void;
}): ReactElement {
  const { t } = useTranslation("game");
  const { candidate, releaseId, force, indexerName, onGrabSuccess } = props;
  const grab = useManualGrab();
  const onClick = (): void => {
    grab.mutate(
      {
        indexerId: candidate.indexer_id,
        indexerGuid: candidate.indexer_guid,
        downloadUrl: candidate.download_url,
        title: candidate.title,
        releaseId,
        force,
      },
      { onSuccess: onGrabSuccess },
    );
  };

  const score =
    candidate.score_breakdown !== null &&
    candidate.score_breakdown !== undefined
      ? (candidate.score_breakdown as { total?: number }).total ?? null
      : null;
  const sizeLabel = formatBytes(candidate.size_bytes);

  return (
    <li
      className={[
        "flex flex-col gap-2 rounded-md border p-3",
        candidate.would_auto_reject
          ? "border-red-900/50 bg-red-950/10 opacity-80"
          : "border-zinc-800 bg-zinc-900/40",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">
          {candidate.title}
        </p>
        <button
          type="button"
          onClick={onClick}
          disabled={grab.isPending || grab.isSuccess}
          className={[
            "shrink-0 rounded-md px-3 py-1 text-xs font-medium",
            "bg-brand/20 text-brand ring-1 ring-inset ring-brand/40",
            "hover:bg-brand/30",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
          title={
            grab.isError && grab.error?.message ? grab.error.message : undefined
          }
        >
          {grab.isSuccess
            ? t("search.grab.dispatched")
            : grab.isPending
              ? t("search.grab.pending")
              : t("search.grab.button")}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-[0.65rem] text-zinc-400">
        <span className="font-mono">
          {indexerName ?? `indexer #${candidate.indexer_id}`}
        </span>
        {sizeLabel && (
          <>
            <span>·</span>
            <span>{sizeLabel}</span>
          </>
        )}
        {typeof candidate.seeders === "number" && (
          <>
            <span>·</span>
            <span>{t("search.seeders", { count: candidate.seeders })}</span>
          </>
        )}
        {score !== null && (
          <>
            <span>·</span>
            <span className="font-mono text-zinc-300">score {score}</span>
          </>
        )}
        {candidate.pre_grab_dat_match !== "skipped" && (
          <span
            className={[
              "ml-auto rounded px-1.5 py-0.5 font-mono uppercase",
              "tracking-wider",
              candidate.pre_grab_dat_match === "verified"
                ? "bg-emerald-950/40 text-emerald-300"
                : candidate.pre_grab_dat_match === "hack"
                  ? "bg-amber-950/40 text-amber-300"
                  : "bg-zinc-800 text-zinc-400",
            ].join(" ")}
          >
            DAT {candidate.pre_grab_dat_match}
          </span>
        )}
      </div>

      {candidate.rejection && (
        <p className="text-[0.7rem] text-red-300">
          {t(`search.rejection.${candidate.rejection.code}`, {
            defaultValue: candidate.rejection.code,
          })}
          {candidate.rejection.message
            ? ` — ${candidate.rejection.message}`
            : ""}
        </p>
      )}
    </li>
  );
}

export function ReleaseSearchModal(
  props: ReleaseSearchModalProps,
): ReactElement | null {
  const { t } = useTranslation("game");
  const [query, setQuery] = useState(props.initialQuery);
  const [force, setForce] = useState(false);
  const search = useManualSearch();
  const indexersById = useIndexersById();

  useEffect(() => {
    if (props.open) {
      setQuery(props.initialQuery);
      search.reset();
    }
    // search.reset is a stable callback; intentional dep set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open, props.initialQuery]);

  if (!props.open) return null;

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (query.trim().length === 0) return;
    search.mutate({
      query: query.trim(),
      platformId: props.platformId,
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="release-search-title"
      className={[
        "fixed inset-0 z-50 flex items-end justify-center bg-black/70",
        "p-4 md:items-center",
      ].join(" ")}
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose();
      }}
    >
      <div
        className={[
          "flex max-h-[90vh] w-full max-w-2xl flex-col gap-3 overflow-hidden",
          "rounded-md border border-zinc-800 bg-zinc-950 p-4",
        ].join(" ")}
      >
        <header className="flex items-start justify-between gap-2">
          <h3
            id="release-search-title"
            className="text-base font-semibold text-zinc-100"
          >
            {t("search.title")}
          </h3>
          <button
            type="button"
            onClick={props.onClose}
            className="text-xl text-zinc-500 hover:text-zinc-200"
            aria-label={t("search.close")}
          >
            ×
          </button>
        </header>

        <form onSubmit={onSubmit} className="flex flex-col gap-2">
          <label className="block">
            <span className="sr-only">{t("search.query.label")}</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("search.query.placeholder")}
              className={[
                "w-full rounded-md bg-zinc-900 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            />
          </label>
          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 accent-brand"
              />
              <span>{t("search.force.label")}</span>
            </label>
            <button
              type="submit"
              disabled={search.isPending || query.trim().length === 0}
              className={[
                "rounded-md bg-brand/20 px-3 py-1.5 text-xs font-medium",
                "text-brand ring-1 ring-inset ring-brand/40",
                "hover:bg-brand/30",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {search.isPending
                ? t("search.run.pending")
                : t("search.run.button")}
            </button>
          </div>
        </form>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {search.isError && (
            <p className="rounded-md border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-300">
              {search.error.message}
            </p>
          )}

          {search.isSuccess && (search.data.candidates ?? []).length === 0 && (
            <p className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400">
              {t("search.empty")}
            </p>
          )}

          {search.isSuccess && (search.data.candidates ?? []).length > 0 && (
            <ul className="space-y-2">
              {(search.data.candidates ?? []).map((c) => (
                <CandidateRow
                  key={`${c.indexer_id}-${c.indexer_guid}`}
                  candidate={c}
                  releaseId={props.releaseId}
                  force={force}
                  indexerName={indexersById.get(c.indexer_id)?.name ?? null}
                  onGrabSuccess={props.onClose}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
