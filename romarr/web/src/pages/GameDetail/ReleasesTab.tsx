/**
 * GameDetail > Releases tab (slice 89).
 *
 * Lists every Release for the game via
 * `useReleasesForGame`. Composes the slice 43 ROM badges
 * (RegionBadge / ConventionBadge / DumpStatusIcon /
 * LanguagePills) so the operator gets the same visual
 * vocabulary as the Wanted page.
 */

import { type ReactElement } from "react";
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
  type Release,
} from "@/lib/api/queries/games";

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
}

function ReleaseRow(props: ReleaseRowProps): ReactElement {
  const { release } = props;
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
        <span className="shrink-0 rounded-full bg-zinc-800 px-2 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
          {release.status}
        </span>
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
    </li>
  );
}

interface ReleasesTabProps {
  gameId: number;
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
        <ReleaseRow key={release.id} release={release} />
      ))}
    </ul>
  );
}
