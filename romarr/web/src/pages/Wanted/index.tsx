/**
 * Wanted page (P-WANT, T072 partial).
 *
 * Two tabs: Missing | Cutoff. Each pulls the canonical
 * pagination envelope from spec 013's wanted router and
 * renders one ReleaseRow per record.
 *
 * Bulk select / bulk actions / per-platform filters are
 * deferred — they need the bulk-search trigger (T043 in spec
 * 013, depends on spec 007 run_manual_search) and the
 * shadcn/ui Checkbox primitive (slice TBD).
 *
 * Strings resolve through the `wanted` namespace (slice 68).
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { usePlatforms } from "@/lib/api/queries/platforms";
import {
  useWantedCutoff,
  useWantedMissing,
} from "@/lib/api/queries/wanted";

import { ReleaseRow } from "./ReleaseRow";

const ALL_PLATFORMS = "all" as const;
type PlatformFilter = number | typeof ALL_PLATFORMS;

type Tab = "missing" | "cutoff";

interface TabButtonProps {
  tab: Tab;
  active: boolean;
  label: string;
  onClick: (tab: Tab) => void;
}

function TabButton(props: TabButtonProps): ReactElement {
  const { tab, active, label, onClick } = props;
  return (
    <button
      type="button"
      onClick={() => onClick(tab)}
      className={[
        "flex-1 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors",
        active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
      ].join(" ")}
      aria-pressed={active}
    >
      {label}
    </button>
  );
}

interface TabBodyProps {
  platformId: number | undefined;
}

function MissingTab(props: TabBodyProps): ReactElement {
  const { t } = useTranslation("wanted");
  const { data, isPending, isError, error } = useWantedMissing({
    pageSize: 50,
    sortKey: "name",
    sortDirection: "asc",
    platformId: props.platformId,
  });

  if (isPending) return <ListSkeleton rows={6} />;
  if (isError) {
    return (
      <EmptyState
        title={t("missing.loadError")}
        description={error.message}
      />
    );
  }
  if (data.records.length === 0) {
    return (
      <EmptyState
        title={t("missing.empty.title")}
        description={t("missing.empty.body")}
      />
    );
  }
  return (
    <ul className="space-y-2">
      {data.records.map((release) => (
        <li key={release.id}>
          <ReleaseRow release={release} />
        </li>
      ))}
    </ul>
  );
}

function CutoffTab(props: TabBodyProps): ReactElement {
  const { t } = useTranslation("wanted");
  const { data, isPending, isError, error } = useWantedCutoff({
    pageSize: 50,
    sortKey: "name",
    sortDirection: "asc",
    platformId: props.platformId,
  });

  if (isPending) return <ListSkeleton rows={6} />;
  if (isError) {
    return (
      <EmptyState
        title={t("cutoff.loadError")}
        description={error.message}
      />
    );
  }
  if (data.records.length === 0) {
    return (
      <EmptyState
        title={t("cutoff.empty.title")}
        description={t("cutoff.empty.body")}
      />
    );
  }
  return (
    <ul className="space-y-2">
      {data.records.map((release) => (
        <li key={release.id}>
          <ReleaseRow release={release} />
        </li>
      ))}
    </ul>
  );
}

export function WantedPage(): ReactElement {
  const { t } = useTranslation("wanted");
  const [tab, setTab] = useState<Tab>("missing");
  const [platformFilter, setPlatformFilter] =
    useState<PlatformFilter>(ALL_PLATFORMS);
  const platforms = usePlatforms();

  const platformId =
    platformFilter === ALL_PLATFORMS ? undefined : platformFilter;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t(`tabHint.${tab}`)}</p>
      </header>

      <div
        role="tablist"
        aria-label={t("tabs.ariaLabel")}
        className="mb-4 flex gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
      >
        <TabButton
          tab="missing"
          active={tab === "missing"}
          label={t("tabs.missing")}
          onClick={setTab}
        />
        <TabButton
          tab="cutoff"
          active={tab === "cutoff"}
          label={t("tabs.cutoff")}
          onClick={setTab}
        />
      </div>

      <label className="mb-4 block md:max-w-xs">
        <span className="sr-only">{t("filters.platform.label")}</span>
        <select
          value={platformFilter === ALL_PLATFORMS ? "" : String(platformFilter)}
          onChange={(e) => {
            const v = e.target.value;
            setPlatformFilter(
              v === "" ? ALL_PLATFORMS : Number.parseInt(v, 10),
            );
          }}
          aria-label={t("filters.platform.label")}
          disabled={!platforms.isSuccess}
          className={[
            "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
            "ring-1 ring-inset ring-zinc-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          <option value="">{t("filters.platform.all")}</option>
          {platforms.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>

      {tab === "missing" ? (
        <MissingTab platformId={platformId} />
      ) : (
        <CutoffTab platformId={platformId} />
      )}
    </div>
  );
}
