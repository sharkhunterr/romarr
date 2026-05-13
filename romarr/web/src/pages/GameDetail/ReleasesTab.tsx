/**
 * GameDetail > Releases tab (slices 89 / 452 / 453).
 *
 * Layout per release card:
 *
 *   ┌─────────────────────────────────────────────┐
 *   │ Title                  [DAT] [Status] ⋯ ⌄  │
 *   │ Regions · Convention · Status · 🇬🇧 EN · Disc│
 *   │ ── expanded: DAT details, file path, etc ───│
 *   └─────────────────────────────────────────────┘
 *
 * All right-side controls share the same height and rounded
 * corners. The bottom meta strip uses uniform pill chips
 * (emoji-free) except for languages, which keep their flag
 * emoji at the operator's explicit request.
 */

import {
  ChevronDown,
  Eye,
  EyeOff,
  Search,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  ConventionBadge,
  DatVerifiedBadge,
  DumpStatusIcon,
  LanguagePills,
  MultiDiscAccordion,
  RegionBadge,
  type DumpStatus,
  type NamingConvention,
} from "@/components/rom";
import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useReleasesForGame,
  useToggleReleaseMonitor,
  type Release,
} from "@/lib/api/queries/games";

import { ReleaseSearchModal } from "./ReleaseSearchModal";

const KNOWN_CONVENTIONS: ReadonlySet<NamingConvention> = new Set([
  "no-intro",
  "redump",
  "tosec",
  "goodtools",
  "scene",
  "unknown",
]);

const KNOWN_DUMP_STATUSES: ReadonlySet<DumpStatus> = new Set([
  "verified",
  "good",
  "proto",
  "beta",
  "demo",
  "sample",
  "hack",
  "trainer",
  "translation",
  "baddump",
  "overdump",
  "unknown",
]);

function asConvention(raw: string): NamingConvention {
  return KNOWN_CONVENTIONS.has(raw as NamingConvention)
    ? (raw as NamingConvention)
    : "unknown";
}

function asDumpStatus(raw: string): DumpStatus {
  return KNOWN_DUMP_STATUSES.has(raw as DumpStatus)
    ? (raw as DumpStatus)
    : "unknown";
}

interface ReleaseRowProps {
  release: Release;
  gameId: number;
  platformId: number;
}

/* ---------------------------------------------------------------- */
/* Reusable icon-button primitive — uniform style across the tab     */
/* ---------------------------------------------------------------- */

const _ICON_BTN_BASE =
  "inline-flex items-center justify-center h-7 w-7 rounded-md " +
  "ring-1 ring-inset transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand " +
  "disabled:cursor-not-allowed disabled:opacity-60";

function IconButton(props: {
  icon: LucideIcon;
  onClick: () => void;
  tone?: "neutral" | "accent" | "emerald";
  label: string;
  pressed?: boolean;
  disabled?: boolean;
}): ReactElement {
  const tone =
    props.tone === "emerald"
      ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40 hover:bg-emerald-700/40"
      : props.tone === "accent"
        ? "bg-brand/15 text-brand ring-brand/40 hover:bg-brand/25"
        : "bg-zinc-800 text-zinc-300 ring-zinc-700 hover:bg-zinc-700";
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      aria-pressed={props.pressed}
      aria-label={props.label}
      title={props.label}
      className={`${_ICON_BTN_BASE} ${tone}`}
    >
      <props.icon size={15} strokeWidth={2.2} aria-hidden="true" />
    </button>
  );
}

/* ---------------------------------------------------------------- */
/* Expandable detail rows                                           */
/* ---------------------------------------------------------------- */

function DetailRow(props: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
}): ReactElement | null {
  if (props.value === null || props.value === undefined || props.value === "") {
    return null;
  }
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2">
      <span className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
        {props.label}
      </span>
      <span
        className={[
          "min-w-0 break-words text-[0.7rem] text-zinc-200",
          props.mono ? "font-mono text-[0.65rem]" : "",
        ]
          .join(" ")
          .trim()}
      >
        {props.value}
      </span>
    </div>
  );
}

function ReleaseRow(props: ReleaseRowProps): ReactElement {
  const { t } = useTranslation("game");
  const { release, gameId, platformId } = props;
  const [searchOpen, setSearchOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const toggleMonitor = useToggleReleaseMonitor();
  const regions = release.regions ?? [];
  const languages = release.languages ?? [];
  const hasDatBadge =
    release.dat_source !== null && release.dat_source !== undefined;

  return (
    <li
      className={[
        "flex flex-col gap-2 rounded-lg border border-zinc-800",
        "bg-zinc-900/40 px-3 py-2.5",
      ].join(" ")}
    >
      {/* Header — title + right-aligned action cluster. */}
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 truncate text-sm font-medium text-zinc-100">
          {release.name}
        </h3>
        <div className="flex shrink-0 items-center gap-1.5">
          {hasDatBadge && (
            <DatVerifiedBadge
              status={release.dat_verified ? "verified" : "invalid"}
              title={
                release.dat_entry_name
                  ? `${release.dat_source} — ${release.dat_entry_name}`
                  : (release.dat_source ?? undefined)
              }
              className="!h-7 !w-7 !p-0"
            />
          )}
          <IconButton
            icon={release.monitored ? Eye : EyeOff}
            onClick={() => {
              toggleMonitor.mutate({
                releaseId: release.id,
                gameId,
                monitored: !release.monitored,
              });
            }}
            disabled={toggleMonitor.isPending}
            pressed={release.monitored}
            tone={release.monitored ? "emerald" : "neutral"}
            label={
              release.monitored
                ? t("releases.monitor.on")
                : t("releases.monitor.off")
            }
          />
          <IconButton
            icon={Search}
            onClick={() => setSearchOpen(true)}
            tone="accent"
            label={t("search.button")}
          />
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-pressed={expanded}
            aria-label={
              expanded
                ? t("releases.collapse")
                : t("releases.expand")
            }
            title={
              expanded
                ? t("releases.collapse")
                : t("releases.expand")
            }
            className={`${_ICON_BTN_BASE} bg-zinc-800 text-zinc-300 ring-zinc-700 hover:bg-zinc-700`}
          >
            <ChevronDown
              size={15}
              strokeWidth={2.2}
              aria-hidden="true"
              className={`transition-transform ${expanded ? "rotate-180" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Meta strip — uniform pills (languages keep their flag). */}
      <div className="flex flex-wrap items-center gap-1.5">
        {regions.map((code) => (
          <RegionBadge
            key={`${release.id}-${code}`}
            code={code}
            noEmoji
          />
        ))}
        <ConventionBadge convention={asConvention(release.naming_convention)} />
        {/* ``Release.dump_status`` is parsed from the filename's
            naming-convention tokens — NOT from the actual DAT
            cascade. ``verified`` / ``good`` are the parser's
            "looks like a clean dump" guess, which would be
            misleading next to a missing DAT badge: the operator
            sees "Verified" and assumes cryptographic truth, when
            in fact only the filename matched the convention.
            So we hide those two default states entirely — the
            DAT badge is the single source of truth for "this
            file is good". Anything else (Hack, Proto, Beta,
            BadDump, Demo, etc.) stays visible because it's
            actionable signal. */}
        {(() => {
          const ds = asDumpStatus(release.dump_status);
          if (ds === "verified" || ds === "good") return null;
          return <DumpStatusIcon status={ds} noEmoji />;
        })()}
        {languages.length > 0 && (
          <LanguagePills codes={languages} max={3} />
        )}
        {release.disc_total > 1 && (
          <span
            className={[
              "inline-flex items-center gap-1 rounded-md px-2 py-0.5",
              "text-xs font-mono font-medium",
              "bg-zinc-800 text-zinc-200 ring-1 ring-inset ring-zinc-700",
            ].join(" ")}
          >
            {t("releases.disc", {
              n: release.disc_number,
              total: release.disc_total,
            })}
          </span>
        )}
      </div>

      {/* Expand — DAT match details + identifiers. */}
      {expanded && (
        <div className="mt-1 space-y-1 rounded-md border border-zinc-800/70 bg-zinc-950/40 px-3 py-2">
          {hasDatBadge && (
            <>
              <DetailRow
                label={t("releases.detail.datSource")}
                value={release.dat_source}
              />
              <DetailRow
                label={t("releases.detail.datEntry")}
                value={release.dat_entry_name}
              />
              <DetailRow
                label={t("releases.detail.datStatus")}
                value={
                  release.dat_verified
                    ? t("releases.detail.datStatusVerified")
                    : t("releases.detail.datStatusInvalid")
                }
              />
            </>
          )}
          <DetailRow
            label={t("releases.detail.releaseId")}
            value={`#${release.id}`}
            mono
          />
          <DetailRow
            label={t("releases.detail.namingConvention")}
            value={release.naming_convention}
            mono
          />
          {release.revision && (
            <DetailRow
              label={t("releases.detail.revision")}
              value={release.revision}
            />
          )}
          {release.cutoff_met && (
            <DetailRow
              label={t("releases.detail.cutoff")}
              value={t("releases.detail.cutoffMet")}
            />
          )}
        </div>
      )}

      <ReleaseSearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        initialQuery={release.name}
        platformId={platformId}
        gameId={gameId}
        releaseId={release.id}
      />
    </li>
  );
}

interface ReleasesTabProps {
  gameId: number;
  platformId: number;
}

export function ReleasesTab(props: ReleasesTabProps): ReactElement {
  const { t } = useTranslation("game");
  const releases = useReleasesForGame(props.gameId);

  if (releases.isLoading) return <ListSkeleton rows={4} />;
  if (releases.isError) {
    return (
      <EmptyState
        title={t("releases.loadError")}
        description={releases.error.message}
      />
    );
  }
  if (releases.data && releases.data.length === 0) {
    return (
      <EmptyState
        title={t("releases.empty.title")}
        description={t("releases.empty.body")}
      />
    );
  }

  const allReleases = releases.data ?? [];
  const childrenByParent = new Map<number, Release[]>();
  for (const r of allReleases) {
    if (r.parent_release_id !== null && r.parent_release_id !== undefined) {
      const list = childrenByParent.get(r.parent_release_id) ?? [];
      list.push(r);
      childrenByParent.set(r.parent_release_id, list);
    }
  }
  for (const list of childrenByParent.values()) {
    list.sort((a, b) => a.disc_number - b.disc_number);
  }
  const topLevel = allReleases.filter(
    (r) => r.parent_release_id === null || r.parent_release_id === undefined,
  );

  return (
    <ul className="space-y-2">
      {topLevel.map((release) => {
        const children = childrenByParent.get(release.id) ?? [];
        if (children.length === 0) {
          return (
            <ReleaseRow
              key={release.id}
              release={release}
              gameId={props.gameId}
              platformId={props.platformId}
            />
          );
        }
        const totalDiscs = release.disc_total || children.length + 1;
        return (
          <div key={release.id} role="listitem">
            <MultiDiscAccordion
              parentTitle={t("releases.multiDiscTitle", {
                title: release.name,
                total: totalDiscs,
              })}
              totalDiscs={totalDiscs}
              defaultOpen={false}
            >
              <ul className="space-y-2 p-2">
                <ReleaseRow
                  release={release}
                  gameId={props.gameId}
                  platformId={props.platformId}
                />
                {children.map((child) => (
                  <ReleaseRow
                    key={child.id}
                    release={child}
                    gameId={props.gameId}
                    platformId={props.platformId}
                  />
                ))}
              </ul>
            </MultiDiscAccordion>
          </div>
        );
      })}
    </ul>
  );
}
