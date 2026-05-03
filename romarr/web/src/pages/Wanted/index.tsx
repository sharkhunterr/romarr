/**
 * Wanted page (P-WANT, slices 68, 152).
 *
 * Two tabs: Missing | Cutoff. Each pulls the canonical
 * pagination envelope from spec 013's wanted router and
 * renders one ReleaseRow per record. The page hosts both
 * the global "search all" command buttons (spec 007's
 * MissingSearch / CutoffSearch task triggers) and slice 152's
 * per-row bulk-select toolbar with monitor / unmonitor.
 *
 * Strings resolve through the `wanted` namespace (slice 68).
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useBulkMonitorReleases } from "@/lib/api/queries/games";
import { usePlatforms } from "@/lib/api/queries/platforms";
import { useTriggerCommand } from "@/lib/api/queries/system";
import {
  useWantedCutoff,
  useWantedMissing,
} from "@/lib/api/queries/wanted";
import { useToastStore } from "@/lib/store/toast";

import { ReleaseRow } from "./ReleaseRow";

const ALL_PLATFORMS = "all" as const;
type PlatformFilter = number | typeof ALL_PLATFORMS;

type WantedSortKey = "name" | "created_at" | "updated_at" | "status";
const SORT_KEYS: readonly WantedSortKey[] = [
  "name",
  "created_at",
  "updated_at",
  "status",
];
const SORT_KEY_SET: ReadonlySet<WantedSortKey> = new Set<WantedSortKey>(
  SORT_KEYS,
);

type SortDirection = "asc" | "desc";

function parsePlatformParam(raw: string | null): PlatformFilter {
  if (raw === null || raw === "") return ALL_PLATFORMS;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : ALL_PLATFORMS;
}

function parseTabParam(raw: string | null): Tab {
  return raw === "cutoff" ? "cutoff" : "missing";
}

function parseSortParam(raw: string | null): WantedSortKey {
  return raw !== null && SORT_KEY_SET.has(raw as WantedSortKey)
    ? (raw as WantedSortKey)
    : "name";
}

function parseDirectionParam(raw: string | null): SortDirection {
  return raw === "desc" ? "desc" : "asc";
}

interface BulkSearchButtonProps {
  /** Sonarr-shape command name (MissingSearch / CutoffSearch). */
  command: "MissingSearch" | "CutoffSearch";
  label: string;
  pendingLabel: string;
  successLabel: string;
}

function BulkSearchButton(props: BulkSearchButtonProps): ReactElement {
  const trigger = useTriggerCommand();
  const onClick = (): void => {
    trigger.mutate({ name: props.command });
  };
  const label = trigger.isPending
    ? props.pendingLabel
    : trigger.isSuccess
      ? props.successLabel
      : props.label;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={trigger.isPending}
      className={[
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5",
        "text-xs font-medium ring-1 ring-inset",
        "bg-brand/20 text-brand ring-brand/40",
        "transition-colors hover:bg-brand/30",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
      ].join(" ")}
      title={
        trigger.isError && trigger.error?.message
          ? trigger.error.message
          : undefined
      }
    >
      <span aria-hidden="true">
        {trigger.isPending ? "⏳" : trigger.isSuccess ? "✓" : "🔎"}
      </span>
      <span>{label}</span>
    </button>
  );
}

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
  sortKey: WantedSortKey;
  sortDirection: SortDirection;
  q: string | undefined;
  selectionActive: boolean;
  selectedIds: ReadonlySet<number>;
  onToggleSelect: (releaseId: number) => void;
  onAllVisible: (ids: number[]) => void;
}

function MissingTab(props: TabBodyProps): ReactElement {
  const { t } = useTranslation("wanted");
  const { data, isPending, isError, error } = useWantedMissing({
    pageSize: 50,
    sortKey: props.sortKey,
    sortDirection: props.sortDirection,
    platformId: props.platformId,
    q: props.q,
  });

  // Hand the visible ids upstream so the bulk-toolbar's
  // "select all visible" action knows which rows to flip.
  useEffect(() => {
    if (data) props.onAllVisible(data.records.map((r) => r.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

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
          <ReleaseRow
            release={release}
            selectionActive={props.selectionActive}
            selected={props.selectedIds.has(release.id)}
            onToggleSelect={props.onToggleSelect}
          />
        </li>
      ))}
    </ul>
  );
}

function CutoffTab(props: TabBodyProps): ReactElement {
  const { t } = useTranslation("wanted");
  const { data, isPending, isError, error } = useWantedCutoff({
    pageSize: 50,
    sortKey: props.sortKey,
    sortDirection: props.sortDirection,
    platformId: props.platformId,
    q: props.q,
  });

  useEffect(() => {
    if (data) props.onAllVisible(data.records.map((r) => r.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

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
          <ReleaseRow
            release={release}
            selectionActive={props.selectionActive}
            selected={props.selectedIds.has(release.id)}
            onToggleSelect={props.onToggleSelect}
          />
        </li>
      ))}
    </ul>
  );
}

export function WantedPage(): ReactElement {
  const { t } = useTranslation("wanted");
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTabParam(searchParams.get("tab"));
  const platformFilter = parsePlatformParam(searchParams.get("platform"));
  const sortKey = parseSortParam(searchParams.get("sort"));
  const sortDirection = parseDirectionParam(searchParams.get("direction"));
  const rawQuery = searchParams.get("q") ?? "";
  const trimmedQuery = rawQuery.trim();
  const platforms = usePlatforms();

  const setTab = (next: Tab): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "missing") params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: false },
    );
  };

  const setPlatformFilter = (next: PlatformFilter): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === ALL_PLATFORMS) params.delete("platform");
        else params.set("platform", String(next));
        return params;
      },
      { replace: false },
    );
  };

  const setSortKey = (next: WantedSortKey): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "name") params.delete("sort");
        else params.set("sort", next);
        return params;
      },
      { replace: false },
    );
  };

  const toggleSortDirection = (): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        const next = sortDirection === "asc" ? "desc" : "asc";
        if (next === "asc") params.delete("direction");
        else params.set("direction", next);
        return params;
      },
      { replace: false },
    );
  };

  const setQuery = (next: string): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next.trim() === "") params.delete("q");
        else params.set("q", next);
        return params;
      },
      { replace: true },
    );
  };

  const platformId =
    platformFilter === ALL_PLATFORMS ? undefined : platformFilter;

  // -- Bulk select state (slice 152) ----------------------------------------
  const pushToast = useToastStore((s) => s.push);
  const bulkMonitor = useBulkMonitorReleases();
  const [selectionActive, setSelectionActive] = useState(false);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const [visibleIds, setVisibleIds] = useState<readonly number[]>([]);

  const toggleSelect = (releaseId: number): void => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(releaseId)) next.delete(releaseId);
      else next.add(releaseId);
      return next;
    });
  };

  const selectAllVisible = (): void => {
    setSelectedIds(new Set(visibleIds));
  };

  const exitSelection = (): void => {
    setSelectionActive(false);
    setSelectedIds(new Set());
  };

  // Resetting selection when the active tab flips avoids
  // stale ids carrying across — Missing and Cutoff have
  // disjoint id sets in practice, so a leftover selection
  // would silently skip rows the operator just selected.
  useEffect(() => {
    setSelectedIds(new Set());
  }, [tab]);

  const runBulkMonitor = (monitored: boolean): void => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    bulkMonitor.mutate(
      { releaseIds: ids, monitored },
      {
        onSuccess: (resp) => {
          pushToast({
            kind: "success",
            title: monitored
              ? t("bulk.monitor.successTitle")
              : t("bulk.unmonitor.successTitle"),
            description: t("bulk.monitor.successBody", {
              updated: resp.updated,
              missing: resp.missing.length,
            }),
          });
          exitSelection();
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("bulk.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  };

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

      <label className="mb-3 block">
        <span className="sr-only">{t("search.label")}</span>
        <input
          type="search"
          value={rawQuery}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("search.placeholder")}
          aria-label={t("search.label")}
          className={[
            "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
            "ring-1 ring-inset ring-zinc-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        />
      </label>

      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center">
        <label className="block md:max-w-xs md:flex-1">
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

        <div className="flex items-stretch gap-1">
          <label className="block md:w-44">
            <span className="sr-only">{t("sort.label")}</span>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as WantedSortKey)}
              aria-label={t("sort.label")}
              className={[
                "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
                "ring-1 ring-inset ring-zinc-700",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {SORT_KEYS.map((k) => (
                <option key={k} value={k}>
                  {t(`sort.key.${k}`)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={toggleSortDirection}
            aria-label={
              sortDirection === "asc"
                ? t("sort.direction.asc")
                : t("sort.direction.desc")
            }
            title={
              sortDirection === "asc"
                ? t("sort.direction.asc")
                : t("sort.direction.desc")
            }
            className={[
              "rounded-md bg-zinc-950 px-3 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700 hover:bg-zinc-900",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {sortDirection === "asc" ? "↑" : "↓"}
          </button>
        </div>

        {tab === "missing" ? (
          <BulkSearchButton
            command="MissingSearch"
            label={t("bulk.missingSearch.idle")}
            pendingLabel={t("bulk.missingSearch.pending")}
            successLabel={t("bulk.missingSearch.success")}
          />
        ) : (
          <BulkSearchButton
            command="CutoffSearch"
            label={t("bulk.cutoffSearch.idle")}
            pendingLabel={t("bulk.cutoffSearch.pending")}
            successLabel={t("bulk.cutoffSearch.success")}
          />
        )}

        <button
          type="button"
          onClick={() =>
            selectionActive ? exitSelection() : setSelectionActive(true)
          }
          aria-pressed={selectionActive}
          className={[
            "shrink-0 rounded-md px-3 py-2 text-xs font-medium ring-1 ring-inset",
            "transition-colors",
            selectionActive
              ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
              : "bg-zinc-950 text-zinc-400 ring-zinc-700 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {selectionActive
            ? t("bulk.exitSelection")
            : t("bulk.enterSelection")}
        </button>
      </div>

      {selectionActive && (
        <div
          role="region"
          aria-label={t("bulk.toolbarAria")}
          className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-brand/40 bg-brand/10 px-3 py-2"
        >
          <p className="text-xs text-zinc-100">
            {t("bulk.selectedCount", { count: selectedIds.size })}
          </p>
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={selectAllVisible}
              disabled={visibleIds.length === 0}
              className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("bulk.selectAll")}
            </button>
            <button
              type="button"
              onClick={() => runBulkMonitor(true)}
              disabled={selectedIds.size === 0 || bulkMonitor.isPending}
              className="rounded-md bg-emerald-600 px-2 py-1 text-[0.65rem] font-medium text-zinc-950 hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {bulkMonitor.isPending
                ? t("bulk.monitor.pending")
                : t("bulk.monitor.label")}
            </button>
            <button
              type="button"
              onClick={() => runBulkMonitor(false)}
              disabled={selectedIds.size === 0 || bulkMonitor.isPending}
              className="rounded-md bg-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-100 hover:bg-zinc-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {bulkMonitor.isPending
                ? t("bulk.unmonitor.pending")
                : t("bulk.unmonitor.label")}
            </button>
            <button
              type="button"
              onClick={exitSelection}
              disabled={bulkMonitor.isPending}
              className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("bulk.cancel")}
            </button>
          </div>
        </div>
      )}

      {tab === "missing" ? (
        <MissingTab
          platformId={platformId}
          sortKey={sortKey}
          sortDirection={sortDirection}
          q={trimmedQuery === "" ? undefined : trimmedQuery}
          selectionActive={selectionActive}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onAllVisible={setVisibleIds}
        />
      ) : (
        <CutoffTab
          platformId={platformId}
          sortKey={sortKey}
          sortDirection={sortDirection}
          q={trimmedQuery === "" ? undefined : trimmedQuery}
          selectionActive={selectionActive}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onAllVisible={setVisibleIds}
        />
      )}
    </div>
  );
}
