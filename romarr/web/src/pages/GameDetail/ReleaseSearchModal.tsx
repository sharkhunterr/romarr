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

import { useDownloadClients } from "@/lib/api/queries/download-clients";
import { useIndexersById } from "@/lib/api/queries/indexers";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import {
  useManualGrab,
  useManualSearch,
  type Candidate,
} from "@/lib/api/queries/search";
import { regionLabelKey } from "@/lib/regions/catalogue";
import { useToastStore } from "@/lib/store/toast";

interface ReleaseSearchModalProps {
  open: boolean;
  onClose: () => void;
  /** Initial query — typically the Release.name (per-release
   * mode) or the Game.title (game-level manual search). */
  initialQuery: string;
  /** Pinned to the game's platform so the search builder uses
   * the right newznab category set. */
  platformId: number;
  /** The game the modal was opened from. Threaded into the
   * grab payload so ``search_history.game_id`` is filled and
   * the per-game History tab actually surfaces this manual
   * grab. ``null`` when the modal is opened from a context
   * without a parent game (none today, but kept open for
   * future global-search flows). */
  gameId: number | null;
  /** Pre-bound to the candidate via /grab so import-time can
   * resolve the right Release without a re-match. ``null`` for
   * game-level manual search where no Release exists yet — the
   * importer will resolve the release via the spec 008 fuzzy
   * match when the file lands. */
  releaseId: number | null;
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

function _scoreOf(c: Candidate): number | null {
  if (c.score_breakdown === null || c.score_breakdown === undefined) {
    return null;
  }
  return (c.score_breakdown as { total?: number }).total ?? null;
}

function _scoreContributions(
  c: Candidate,
): readonly { source: string; name: string; value: number }[] {
  const breakdown = c.score_breakdown as
    | {
        contributions?: readonly {
          source: string;
          name: string;
          value: number;
        }[];
      }
    | null
    | undefined;
  return breakdown?.contributions ?? [];
}

function _matchPercent(
  candidate: Candidate,
  profileScore: number,
  maxProfileScore: number,
): number {
  // Composite score: 50% identification (title fuzzy match against
  // the monitored Game; platform already filtered upstream so
  // every accepted candidate scores 100% on platform) + 50%
  // profile match (round-relative — the best profile score in
  // this round = 100% on this half).
  const titleHalf = candidate.title_match_score ?? 100;
  const profileHalf =
    maxProfileScore > 0
      ? Math.max(0, profileScore) / maxProfileScore * 100
      : 0;
  return Math.round(titleHalf * 0.5 + profileHalf * 0.5);
}

type FacetTone = "good" | "neutral" | "warn" | "bad";

const _FACET_PALETTE: Record<FacetTone, string> = {
  good: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  neutral: "bg-zinc-800 text-zinc-300 ring-zinc-600",
  warn: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  bad: "bg-red-700/30 text-red-200 ring-red-500/40",
};

function FacetChip(props: {
  label: string;
  tone: FacetTone;
  title?: string;
}): ReactElement {
  return (
    <span
      title={props.title}
      className={[
        "inline-flex items-center rounded-md px-2 py-0.5",
        "text-[0.65rem] font-medium ring-1 ring-inset",
        _FACET_PALETTE[props.tone],
      ].join(" ")}
    >
      {props.label}
    </span>
  );
}

const _DUMP_TONE: Record<string, FacetTone> = {
  verified: "good",
  good: "good",
  proto: "warn",
  beta: "warn",
  demo: "warn",
  sample: "warn",
  trainer: "warn",
  translation: "warn",
  hack: "bad",
  baddump: "bad",
  overdump: "bad",
  unknown: "neutral",
};

function _toneFor(
  candidate: Candidate,
  field: string,
  whenPresent: FacetTone,
): FacetTone {
  // If the pipeline rejected on this exact field, paint it red so
  // the operator's eye lands on the failing facet immediately.
  // Other rejection fields stay in their natural tone — a
  // language-rejected row still shows its region in green.
  if (candidate.rejection && candidate.rejection.field === field) {
    return "bad";
  }
  return whenPresent;
}

function MatchPercentBadge(props: {
  pct: number;
  tooltip?: string;
}): ReactElement {
  const { pct, tooltip } = props;
  let palette = "bg-zinc-700/30 text-zinc-300 ring-zinc-500/40";
  if (pct >= 80) {
    palette = "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40";
  } else if (pct >= 40) {
    palette = "bg-amber-700/30 text-amber-200 ring-amber-500/40";
  }
  return (
    <span
      title={tooltip}
      className={[
        "inline-flex items-center rounded-md px-2.5 py-1",
        "text-sm font-mono font-medium tabular-nums ring-1 ring-inset",
        palette,
      ].join(" ")}
    >
      {pct}%
    </span>
  );
}

function CandidateRow(props: {
  candidate: Candidate;
  maxScore: number;
  gameId: number | null;
  releaseId: number | null;
  force: boolean;
  indexerName: string | null;
  platformShortName: string | null;
  /** Platform id the modal opened for (the matched_game's
   * platform). When the candidate's detected ``platform_id``
   * disagrees with this, the platform chip turns red. */
  expectedPlatformId: number;
  onGrabSuccess: () => void;
}): ReactElement {
  const { t } = useTranslation("game");
  const {
    candidate,
    maxScore,
    gameId,
    releaseId,
    force,
    indexerName,
    platformShortName,
    expectedPlatformId,
    onGrabSuccess,
  } = props;
  const grab = useManualGrab();
  const pushToast = useToastStore((s) => s.push);
  const [expanded, setExpanded] = useState(false);
  const onClick = (): void => {
    grab.mutate(
      {
        indexerId: candidate.indexer_id,
        indexerGuid: candidate.indexer_guid,
        downloadUrl: candidate.download_url,
        title: candidate.title,
        gameId: gameId ?? undefined,
        releaseId: releaseId ?? undefined,
        force,
      },
      {
        // The backend returns HTTP 200 even when dispatch falls
        // short of a real grab (no routable client, all clients
        // failed, etc.) — the body's ``status`` carries the real
        // outcome. Surface it as a toast so the operator sees why
        // nothing landed in the queue, and only close the modal
        // on an actual successful grab.
        onSuccess: (data) => {
          const status =
            (data as { status?: string }).status ?? "unknown";
          const reason = (data as { reason?: string | null }).reason;
          if (status === "grabbed") {
            pushToast({
              kind: "success",
              title: t("search.grab.toast.successTitle"),
              description: t("search.grab.toast.successBody", {
                title: candidate.title,
              }),
            });
            onGrabSuccess();
            return;
          }
          pushToast({
            kind: "error",
            title: t("search.grab.toast.failedTitle"),
            description:
              reason ||
              t(`search.grab.toast.failedReasons.${status}` as never, {
                defaultValue: status,
              }),
          });
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("search.grab.toast.failedTitle"),
            description: err.message,
          });
        },
      },
    );
  };

  const score = _scoreOf(candidate);
  const sizeLabel = formatBytes(candidate.size_bytes);
  // The breakdown tooltip surfaces the per-source contributions
  // so the operator sees *why* this candidate scored what it did
  // — region match, language preferred, custom-format hits, DAT
  // verified bonus, size penalty.
  const breakdownTooltip = _scoreContributions(candidate)
    .map((c) => `${c.name}: ${c.value >= 0 ? "+" : ""}${c.value}`)
    .join("\n");

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
        {/* Slice 400 — title is now a toggle button. The row
            stays compact by default (truncate); tap the title to
            expand inline details (full title, download URL,
            score breakdown, indexer GUID, …). Modal would crowd
            the already-modal search; collapsible keeps the list
            scannable while still surfacing every field. */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className={[
            "min-w-0 flex-1 text-left text-sm font-medium text-zinc-100",
            "hover:text-brand focus-visible:outline-none focus-visible:text-brand",
            expanded ? "" : "truncate",
          ].join(" ")}
          title={candidate.title}
        >
          <span aria-hidden="true" className="mr-1 text-zinc-500">
            {expanded ? "▾" : "▸"}
          </span>
          {candidate.title}
        </button>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {/* Match-quality column: profile score for accepted
              candidates, "Rejected" badge for rejected ones. The
              parent list sorts by score desc so the best match
              floats to the top. */}
          {score !== null ? (
            <MatchPercentBadge
              pct={_matchPercent(candidate, score, maxScore)}
              tooltip={breakdownTooltip || undefined}
            />
          ) : (
            <span
              className={[
                "inline-flex items-center rounded-md px-2 py-0.5",
                "text-[0.65rem] font-mono uppercase tracking-wider",
                "bg-red-950/30 text-red-300 ring-1 ring-inset ring-red-900/50",
              ].join(" ")}
              title={candidate.rejection?.message ?? undefined}
            >
              {t("search.rejected")}
            </span>
          )}
          <button
            type="button"
            onClick={onClick}
            disabled={grab.isPending || grab.isSuccess}
            className={[
              "rounded-md px-3 py-1 text-xs font-medium",
              "bg-brand/20 text-brand ring-1 ring-inset ring-brand/40",
              "hover:bg-brand/30",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
            title={
              grab.isError && grab.error?.message
                ? grab.error.message
                : undefined
            }
          >
            {grab.isSuccess
              ? t("search.grab.dispatched")
              : grab.isPending
                ? t("search.grab.pending")
                : t("search.grab.button")}
          </button>
        </div>
      </div>

      {/* Per-facet identity row: platform / region / language /
          dump status / naming convention with semantic colours so
          the operator sees at a glance whether each dimension is
          consistent with the matched game (or flagged as the
          rejection cause). Every facet renders unconditionally —
          a missing / unknown value shows as ``?`` in zinc so the
          row layout stays predictable and the operator notices
          which dimensions the parser couldn't recover. */}
      <div className="flex flex-wrap items-center gap-1">
        {(() => {
          // Detected platform vs expected (modal's platform_id).
          // - mismatch  → red, surfaces a candidate that bound to
          //   a fuzzy game on this platform but advertises another
          //   platform in its title;
          // - match     → green, the title and the matched game
          //   agree;
          // - unknown   → zinc with the matched-game's short name
          //   if available, else "Plateforme ?".
          const detectedId = candidate.platform_id ?? null;
          let tone: FacetTone = "neutral";
          let label: string;
          if (detectedId === null) {
            label =
              platformShortName ?? t("search.facet.unknownLabel.platform");
          } else if (detectedId === expectedPlatformId) {
            label = platformShortName ?? "";
            tone = "good";
          } else {
            label = platformShortName ?? `#${detectedId}`;
            tone = "bad";
          }
          return (
            <FacetChip
              label={label}
              tone={tone}
              title={t("search.facet.platform")}
            />
          );
        })()}
        <FacetChip
          label={(() => {
            if (!candidate.region)
              return t("search.facet.unknownLabel.region");
            const key = regionLabelKey(candidate.region);
            return key === candidate.region
              ? candidate.region
              : t(`settings:profiles.region.catalogue.${key}` as never, {
                  defaultValue: candidate.region,
                });
          })()}
          tone={
            candidate.region
              ? _toneFor(candidate, "region", "good")
              : _toneFor(candidate, "region", "neutral")
          }
          title={t("search.facet.region")}
        />
        <FacetChip
          label={
            (candidate.languages?.length ?? 0) > 0
              ? (candidate.languages ?? []).join(" · ").toUpperCase()
              : t("search.facet.unknownLabel.languages")
          }
          tone={
            (candidate.languages?.length ?? 0) > 0
              ? _toneFor(candidate, "languages", "good")
              : _toneFor(candidate, "languages", "neutral")
          }
          title={t("search.facet.languages")}
        />
        <FacetChip
          label={
            candidate.dump_status
              ? t(
                  `search.dumpStatus.${candidate.dump_status}` as never,
                  { defaultValue: candidate.dump_status },
                )
              : t("search.facet.unknownLabel.dumpStatus")
          }
          tone={_toneFor(
            candidate,
            "dump_status",
            candidate.dump_status
              ? (_DUMP_TONE[candidate.dump_status] ?? "neutral")
              : "neutral",
          )}
          title={t("search.facet.dumpStatus")}
        />
        <FacetChip
          label={
            candidate.naming_convention &&
            candidate.naming_convention !== "unknown"
              ? candidate.naming_convention
              : t("search.facet.unknownLabel.naming")
          }
          tone={
            candidate.naming_convention === "scene" ? "warn" : "neutral"
          }
          title={t("search.facet.naming")}
        />
        <FacetChip
          label={
            candidate.file_format
              ? candidate.file_format.toUpperCase()
              : t("search.facet.unknownLabel.fileFormat")
          }
          tone={_toneFor(candidate, "format", "neutral")}
          title={t("search.facet.fileFormat")}
        />
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
        {/* Only paint the DAT badge when it's actionable:
            "verified" (green) or "hack" (amber). Indexers almost
            never expose per-file ROM hashes — they ship the
            torrent info-hash, which the cascade can't resolve —
            so "none" / "skipped" render on every other candidate
            and become pure noise. */}
        {(candidate.pre_grab_dat_match === "verified" ||
          candidate.pre_grab_dat_match === "hack") && (
          <span
            className={[
              "ml-auto rounded px-1.5 py-0.5 font-mono uppercase",
              "tracking-wider",
              candidate.pre_grab_dat_match === "verified"
                ? "bg-emerald-950/40 text-emerald-300"
                : "bg-amber-950/40 text-amber-300",
            ].join(" ")}
            title={
              candidate.pre_grab_dat_match === "verified"
                ? t("search.datBadge.verifiedTooltip")
                : t("search.datBadge.hackTooltip")
            }
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

      {expanded && (
        <div className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 rounded border border-zinc-800/70 bg-zinc-950/40 p-2 text-[0.7rem]">
          <DetailKv
            label={t("search.detail.fields.indexer")}
            value={
              indexerName
                ? `${indexerName} (#${candidate.indexer_id})`
                : `#${candidate.indexer_id}`
            }
          />
          <DetailKv
            label={t("search.detail.fields.guid")}
            value={candidate.indexer_guid}
            mono
          />
          {candidate.size_bytes !== null &&
            candidate.size_bytes !== undefined && (
              <DetailKv
                label={t("search.detail.fields.size")}
                value={`${(candidate.size_bytes / 1_048_576).toFixed(1)} MiB · ${candidate.size_bytes} B`}
              />
            )}
          {candidate.languages && candidate.languages.length > 0 && (
            <DetailKv
              label={t("search.detail.fields.languages")}
              value={candidate.languages.join(", ")}
            />
          )}
          {candidate.file_format && (
            <DetailKv
              label={t("search.detail.fields.fileFormat")}
              value={candidate.file_format}
            />
          )}
          {typeof candidate.title_match_score === "number" && (
            <DetailKv
              label={t("search.detail.fields.titleScore")}
              value={`${Math.round((candidate.title_match_score ?? 0) * 100)} %`}
            />
          )}
          {typeof candidate.grabs === "number" && (
            <DetailKv
              label={t("search.detail.fields.grabs")}
              value={String(candidate.grabs)}
            />
          )}
          {typeof candidate.download_volume_factor === "number" && (
            <DetailKv
              label={t("search.detail.fields.downloadVolumeFactor")}
              value={
                candidate.download_volume_factor === 0
                  ? t("search.detail.fields.freeleech")
                  : `${candidate.download_volume_factor}×`
              }
            />
          )}
          {typeof candidate.upload_volume_factor === "number" &&
            candidate.upload_volume_factor !== 1 && (
              <DetailKv
                label={t("search.detail.fields.uploadVolumeFactor")}
                value={`${candidate.upload_volume_factor}×`}
              />
            )}
          {typeof candidate.year === "number" && (
            <DetailKv
              label={t("search.detail.fields.year")}
              value={String(candidate.year)}
            />
          )}
          {candidate.genre && (
            <DetailKv
              label={t("search.detail.fields.genre")}
              value={candidate.genre}
            />
          )}
          {candidate.description && (
            <DetailKv
              label={t("search.detail.fields.description")}
              value={candidate.description}
              pre
            />
          )}
          {candidate.info_url && (
            <>
              <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
                {t("search.detail.fields.infoUrl")}
              </dt>
              <dd className="min-w-0">
                <a
                  href={candidate.info_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-[0.65rem] text-brand hover:underline"
                >
                  {candidate.info_url}
                </a>
              </dd>
            </>
          )}
          {candidate.nfo_url && (
            <>
              <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
                {t("search.detail.fields.nfoUrl")}
              </dt>
              <dd className="min-w-0">
                <a
                  href={candidate.nfo_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-[0.65rem] text-brand hover:underline"
                >
                  {candidate.nfo_url}
                </a>
              </dd>
            </>
          )}
          {breakdownTooltip && (
            <DetailKv
              label={t("search.detail.fields.scoreBreakdown")}
              value={breakdownTooltip}
              pre
            />
          )}
          <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
            {t("search.detail.fields.downloadUrl")}
          </dt>
          <dd className="min-w-0">
            <a
              href={candidate.download_url}
              target="_blank"
              rel="noreferrer"
              className="block truncate font-mono text-[0.65rem] text-brand hover:underline"
            >
              {candidate.download_url}
            </a>
          </dd>
        </div>
      )}
    </li>
  );
}

function DetailKv(props: {
  label: string;
  value: string;
  mono?: boolean;
  pre?: boolean;
}): ReactElement {
  return (
    <>
      <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
        {props.label}
      </dt>
      <dd
        className={[
          "min-w-0 break-words text-zinc-200",
          props.mono ? "font-mono text-[0.65rem]" : "",
          props.pre ? "whitespace-pre-line" : "",
        ]
          .join(" ")
          .trim()}
      >
        {props.value}
      </dd>
    </>
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
  const platformsById = usePlatformsById();
  const downloadClients = useDownloadClients();
  // Spec 004: indexer rows are stored in the same map. An empty
  // map means the operator has no indexer configured yet, so the
  // round can't return anything — surface a clear hint with a
  // link to Settings rather than a silent "no candidates".
  const noIndexersConfigured = indexersById.size === 0;
  // Mirror banner for download clients: search returns candidates
  // happily but every Grab will fall to ``no_routable_indexer``
  // because dispatch_winner has nothing to hand the source to.
  const noDownloadClientConfigured =
    downloadClients.isSuccess &&
    (downloadClients.data ?? []).filter((c) => c.enabled).length === 0;

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

        {noIndexersConfigured && (
          <p className="rounded-md border border-amber-900/60 bg-amber-950/30 p-3 text-xs text-amber-200">
            {t("search.noIndexers")}
          </p>
        )}

        {noDownloadClientConfigured && (
          <p className="rounded-md border border-amber-900/60 bg-amber-950/30 p-3 text-xs text-amber-200">
            {t("search.noDownloadClient")}
          </p>
        )}

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
            <>
              {/* Slice 404 — when no candidates came back, look at
                  ``indexer_outcomes`` and surface a precise
                  diagnostic. Rate-limited indexers are the
                  common case for a fresh "no candidates" — they
                  silently dropped every result. */}
              {(() => {
                const outcomes = search.data.indexer_outcomes ?? {};
                const rateLimited = Object.values(outcomes).filter(
                  (v) => v === "rate_limited",
                ).length;
                const failed = Object.values(outcomes).filter(
                  (v) => v === "failed",
                ).length;
                if (rateLimited > 0) {
                  return (
                    <p className="rounded-md border border-amber-900/50 bg-amber-950/20 p-3 text-xs text-amber-200">
                      {t("search.outcome.rateLimited", { count: rateLimited })}
                    </p>
                  );
                }
                if (failed > 0) {
                  return (
                    <p className="rounded-md border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-300">
                      {t("search.outcome.failed", { count: failed })}
                    </p>
                  );
                }
                return (
                  <p className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400">
                    {t("search.empty")}
                  </p>
                );
              })()}
            </>
          )}

          {search.isSuccess && (search.data.candidates ?? []).length > 0 && (
            (() => {
              // Normalise the % display against the best score
              // returned by THIS round so the operator reads
              // "100% = best match Romarr found", not "100% = some
              // theoretical max". Recomputed on each render — the
              // candidate list is small (≤ 200/indexer per FR-029)
              // so there's no win in memoising.
              const acceptedScores = (search.data.candidates ?? [])
                .map((c) => _scoreOf(c))
                .filter((s): s is number => s !== null);
              const maxScore = acceptedScores.length
                ? Math.max(0, ...acceptedScores)
                : 0;
              return (
                <ul className="space-y-2">
                  {[...(search.data.candidates ?? [])]
                    .sort((a, b) => {
                      // Match-quality first: accepted candidates rank
                      // desc by the same composite the badge shows
                      // (title + profile, 50/50). Rejected ones
                      // (score=null) sink to the bottom in their
                      // original order so the operator can still see
                      // what was filtered and why.
                      const sa = _scoreOf(a);
                      const sb = _scoreOf(b);
                      if (sa === null && sb === null) return 0;
                      if (sa === null) return 1;
                      if (sb === null) return -1;
                      const pa = _matchPercent(a, sa, maxScore);
                      const pb = _matchPercent(b, sb, maxScore);
                      return pb - pa;
                    })
                    .map((c) => {
                      // Detected platform = round-time match against
                      // the catalogue (slice 354). The chip label
                      // pulls its short_name from the platforms
                      // store; the colour comparison happens inside
                      // CandidateRow against ``expectedPlatformId``.
                      const platform =
                        c.platform_id !== null && c.platform_id !== undefined
                          ? platformsById.get(c.platform_id)
                          : undefined;
                      return (
                        <CandidateRow
                          key={`${c.indexer_id}-${c.indexer_guid}`}
                          candidate={c}
                          maxScore={maxScore}
                          gameId={props.gameId}
                          releaseId={props.releaseId}
                          force={force}
                          indexerName={
                            indexersById.get(c.indexer_id)?.name ?? null
                          }
                          platformShortName={
                            platform?.short_name ?? platform?.name ?? null
                          }
                          expectedPlatformId={props.platformId}
                          onGrabSuccess={props.onClose}
                        />
                      );
                    })}
                </ul>
              );
            })()
          )}
        </div>
      </div>
    </div>
  );
}
