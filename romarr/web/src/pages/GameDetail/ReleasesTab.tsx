/**
 * GameDetail > Releases tab (slice 89).
 *
 * Lists every Release for the game via
 * `useReleasesForGame`. Composes the slice 43 ROM badges
 * (RegionBadge / ConventionBadge / DumpStatusIcon /
 * LanguagePills) so the operator gets the same visual
 * vocabulary as the Wanted page.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  ConventionBadge,
  DumpStatusIcon,
  LanguagePills,
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

interface MonitorPillProps {
  release: Release;
  gameId: number;
}

function MonitorPill(props: MonitorPillProps): ReactElement {
  const { t } = useTranslation("game");
  const { release, gameId } = props;
  const toggle = useToggleReleaseMonitor();
  const onClick = (): void => {
    toggle.mutate({
      releaseId: release.id,
      gameId,
      monitored: !release.monitored,
    });
  };
  const tone = release.monitored
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-zinc-800 text-zinc-400 ring-zinc-700";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={toggle.isPending}
      aria-pressed={release.monitored}
      className={[
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5",
        "text-[0.6rem] uppercase tracking-wider ring-1 ring-inset",
        "transition-colors hover:brightness-110",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        tone,
      ].join(" ")}
      title={
        toggle.isError && toggle.error?.message
          ? toggle.error.message
          : undefined
      }
    >
      <span aria-hidden="true">{release.monitored ? "👁️" : "💤"}</span>
      <span>
        {release.monitored
          ? t("releases.monitor.on")
          : t("releases.monitor.off")}
      </span>
    </button>
  );
}

function ReleaseRow(props: ReleaseRowProps): ReactElement {
  const { t } = useTranslation("game");
  const { release, gameId, platformId } = props;
  const [searchOpen, setSearchOpen] = useState(false);
  const regions = release.regions ?? [];
  const languages = release.languages ?? [];
  return (
    <li
      className={[
        "flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="truncate text-sm font-medium text-zinc-100">
          {release.name}
        </p>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
            {release.status}
          </span>
          <MonitorPill release={release} gameId={gameId} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {regions.map((code) => (
          <RegionBadge key={`${release.id}-${code}`} code={code} />
        ))}
        <ConventionBadge convention={asConvention(release.naming_convention)} />
        <DumpStatusIcon status={asDumpStatus(release.dump_status)} iconOnly />
        {languages.length > 0 && (
          <LanguagePills codes={languages} max={3} />
        )}
        {release.disc_total > 1 && (
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
            Disc {release.disc_number}/{release.disc_total}
          </span>
        )}
      </div>
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className={[
            "rounded-md px-2.5 py-1 text-[0.65rem] font-medium",
            "bg-zinc-800 text-zinc-200 ring-1 ring-inset ring-zinc-700",
            "hover:bg-zinc-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          🔎 {t("search.button")}
        </button>
      </div>
      <ReleaseSearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        initialQuery={release.name}
        platformId={platformId}
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
  return (
    <ul className="space-y-2">
      {releases.data?.map((release) => (
        <ReleaseRow
          key={release.id}
          release={release}
          gameId={props.gameId}
          platformId={props.platformId}
        />
      ))}
    </ul>
  );
}
