/**
 * Add New page (P-ADD, slices 144 + 145).
 *
 * Operator-driven search across every enabled metadata
 * provider, plus a per-row "Add to Library" mutation. Drives
 * the spec 014 "Add New" workflow:
 *   1. Search every provider for matching titles.
 *   2. Pick a candidate, choose a Platform + monitored flag.
 *   3. Persist a Game row with ``needs_metadata_refresh=true``
 *      so the aggregator enriches the rest of the fields.
 *
 * Strings resolve through the `addNew` namespace.
 */

import { Gamepad2, Plus } from "lucide-react";
import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useAddGameFromLookup,
  useGameLookup,
  type GameLookupRow,
} from "@/lib/api/queries/lookup";
import { usePlatforms } from "@/lib/api/queries/platforms";
import { useToastStore } from "@/lib/store/toast";

import { AddGameModal } from "./AddGameModal";
import { RecentAdditions } from "./RecentAdditions";

function ProviderPill(props: { name: string }): ReactElement {
  return (
    <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-zinc-300">
      {props.name}
    </span>
  );
}

function ConfidenceBar(props: { value: number }): ReactElement {
  const pct = Math.round(props.value * 100);
  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <div
        className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800"
        aria-hidden="true"
      >
        <div
          className={[
            "h-full",
            pct >= 80
              ? "bg-emerald-500"
              : pct >= 50
                ? "bg-amber-400"
                : "bg-red-500",
          ].join(" ")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[0.65rem] text-zinc-400">{pct}%</span>
    </div>
  );
}

/**
 * Two-state platform pill.
 *
 * The pill colour is a "recognised by Romarr" hint, nothing more:
 *   * brand-green — the platform is in the operator's installed
 *     Platform Pack (the AddGame modal can pre-select it);
 *   * muted zinc — IGDB knows about this platform but Romarr's
 *     pack doesn't (e.g. Xbox Series X). The operator still sees
 *     the candidate and can pick the closest configured platform
 *     manually if relevant.
 */
function PlatformPill(props: {
  name: string;
  isKnown: boolean;
}): ReactElement {
  return (
    <span
      className={[
        "mt-1 inline-flex max-w-full items-center gap-1 rounded-md px-2 py-0.5",
        "ring-1 ring-inset",
        "text-[0.7rem] font-medium",
        props.isKnown
          ? "bg-brand/15 text-brand ring-brand/30"
          : "bg-zinc-800/60 text-zinc-400 ring-zinc-700/60",
      ].join(" ")}
      title={props.isKnown ? undefined : props.name}
    >
      <span className="truncate">{props.name}</span>
    </span>
  );
}

function CoverThumb(props: {
  url: string | null | undefined;
  title: string;
}): ReactElement {
  if (!props.url) {
    return (
      <div
        aria-hidden="true"
        className="flex h-20 w-14 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-zinc-800 to-zinc-900 ring-1 ring-zinc-800"
      >
        <Gamepad2 size={20} className="text-zinc-600" aria-hidden="true" />
      </div>
    );
  }
  return (
    <img
      src={props.url}
      alt={props.title}
      loading="lazy"
      className="h-20 w-14 shrink-0 rounded-md object-cover ring-1 ring-zinc-800"
    />
  );
}

function LookupRow(props: {
  row: GameLookupRow;
  onAdd: (row: GameLookupRow) => void;
  onOpenDetail: (row: GameLookupRow) => void;
  isAdding?: boolean;
}): ReactElement {
  const { t } = useTranslation("addNew");
  const { row } = props;
  return (
    <li
      className={[
        "flex gap-3 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
      ].join(" ")}
    >
      <CoverThumb url={row.coverUrl} title={row.title} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {/* Slice 399 — title is now a button. Truncated for
                layout, but the operator can tap to open a modal
                with the full title + every extracted field. */}
            <button
              type="button"
              onClick={() => props.onOpenDetail(row)}
              title={row.title}
              className="block w-full max-w-full truncate text-left text-sm font-medium text-zinc-100 hover:text-brand focus-visible:outline-none focus-visible:text-brand"
            >
              {row.title}
              {row.releaseYear && (
                <span className="ml-1.5 font-mono text-xs font-normal text-zinc-500">
                  ({row.releaseYear})
                </span>
              )}
            </button>
            {(row.platformName || row.platformSlug) && (
              <PlatformPill
                name={row.platformName ?? row.platformSlug ?? ""}
                isKnown={Boolean(row.platformSlug)}
              />
            )}
          </div>
          <ConfidenceBar value={row.confidence} />
        </div>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 text-[0.65rem] text-zinc-500">
          {/* Slice 410 — when dedupe collapsed multiple
              providers into this row, surface every one as a
              pill instead of just the highest-confidence
              ``providerName``. Tooltip carries the provider's
              id so the operator can cross-check. */}
          <div className="flex flex-wrap items-center gap-1">
            {(row.providers ?? []).length > 0 ? (
              (row.providers ?? []).map((p) => (
                <span
                  key={`${p.name}-${p.gameId}`}
                  title={`${p.name} · id ${p.gameId}`}
                  className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.55rem] uppercase tracking-wider text-zinc-300"
                >
                  {p.name}
                </span>
              ))
            ) : (
              <ProviderPill name={row.providerName} />
            )}
          </div>
          <button
            type="button"
            onClick={() => props.onAdd(row)}
            disabled={props.isAdding}
            className={[
              "inline-flex items-center gap-1 rounded-md bg-brand px-2.5 py-1 text-[0.65rem] font-medium text-zinc-900",
              "hover:bg-brand-300",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              "disabled:cursor-not-allowed disabled:opacity-60",
            ].join(" ")}
          >
            <Plus size={12} aria-hidden="true" />
            {t("addButton")}
          </button>
        </div>
      </div>
    </li>
  );
}

function applyFilters(
  rows: readonly GameLookupRow[],
  platformSlug: string,
  year: string,
  providerName: string,
): GameLookupRow[] {
  return rows.filter((row) => {
    if (platformSlug && row.platformSlug !== platformSlug) return false;
    if (year && String(row.releaseYear ?? "") !== year) return false;
    if (providerName) {
      const names = (row.providers ?? []).map((p) => p.name);
      if (!names.includes(providerName) && row.providerName !== providerName)
        return false;
    }
    return true;
  });
}

interface FilterBarProps {
  platforms: ReadonlyArray<{ slug: string; name: string }>;
  years: ReadonlyArray<number>;
  providers: ReadonlyArray<string>;
  filterPlatform: string;
  setFilterPlatform: (s: string) => void;
  filterYear: string;
  setFilterYear: (s: string) => void;
  filterProvider: string;
  setFilterProvider: (s: string) => void;
  open: boolean;
  setOpen: (b: boolean) => void;
  totalRows: number;
}

function FilterBar(props: FilterBarProps): ReactElement {
  const { t } = useTranslation("addNew");
  const activeCount =
    (props.filterPlatform ? 1 : 0) +
    (props.filterYear ? 1 : 0) +
    (props.filterProvider ? 1 : 0);
  return (
    <div className="mb-3 rounded-md border border-zinc-800 bg-zinc-900/40">
      <button
        type="button"
        onClick={() => props.setOpen(!props.open)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        aria-expanded={props.open}
      >
        <span className="inline-flex items-center gap-2">
          <span className="font-medium">{t("filters.title")}</span>
          {activeCount > 0 && (
            <span className="rounded-full bg-brand/20 px-1.5 py-0.5 text-[0.6rem] font-medium text-brand ring-1 ring-inset ring-brand/40">
              {activeCount}
            </span>
          )}
          <span className="text-[0.65rem] text-zinc-500">
            {t("filters.summary", { count: props.totalRows })}
          </span>
        </span>
        <span aria-hidden="true" className="text-zinc-500">
          {props.open ? "▾" : "▸"}
        </span>
      </button>
      {props.open && (
        <div className="grid gap-3 border-t border-zinc-800 p-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
              {t("filters.platform")}
            </span>
            <select
              value={props.filterPlatform}
              onChange={(e) => props.setFilterPlatform(e.target.value)}
              className="rounded-md bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <option value="">{t("filters.platformAll")}</option>
              {props.platforms.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
              {t("filters.year")}
            </span>
            <select
              value={props.filterYear}
              onChange={(e) => props.setFilterYear(e.target.value)}
              className="rounded-md bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <option value="">{t("filters.yearAll")}</option>
              {props.years.map((y) => (
                <option key={y} value={String(y)}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
              {t("filters.provider")}
            </span>
            <select
              value={props.filterProvider}
              onChange={(e) => props.setFilterProvider(e.target.value)}
              className="rounded-md bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <option value="">{t("filters.providerAll")}</option>
              {props.providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          {activeCount > 0 && (
            <button
              type="button"
              onClick={() => {
                props.setFilterPlatform("");
                props.setFilterProvider("");
                props.setFilterYear("");
              }}
              className="col-span-full justify-self-start text-[0.65rem] text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {t("filters.clear")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function AddNewPage(): ReactElement {
  const { t } = useTranslation("addNew");
  const navigate = useNavigate();
  const pushToast = useToastStore((s) => s.push);
  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = useState(urlQuery);
  const [pendingAdd, setPendingAdd] = useState<GameLookupRow | null>(null);
  const [detailRow, setDetailRow] = useState<GameLookupRow | null>(null);

  // Slice 396 — client-side filters on the lookup results.
  // Platform / year are projected directly from the candidate
  // shape (``platformSlug`` + ``releaseYear`` already on the
  // GameLookupRow contract). Genre / type / edition aren't in
  // the contract yet — defer to a follow-up that enriches the
  // lookup endpoint with provider-side genre tags.
  const [filterPlatform, setFilterPlatform] = useState<string>("");
  const [filterYear, setFilterYear] = useState<string>("");
  const [filterProvider, setFilterProvider] = useState<string>("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const platforms = usePlatforms();
  const directAdd = useAddGameFromLookup();

  // Click flow:
  //   * Candidate has a platformSlug Romarr recognises → fire add
  //     directly (one-click), navigate to detail on success.
  //   * Otherwise (gray pill: IGDB-only platform) → open the modal
  //     so the operator picks the closest local platform.
  function handleAdd(row: GameLookupRow): void {
    const list = platforms.data ?? [];
    const matched = row.platformSlug
      ? list.find((p) => p.slug === row.platformSlug)
      : undefined;
    if (matched === undefined) {
      setPendingAdd(row);
      return;
    }
    directAdd.mutate(
      {
        providerName: row.providerName,
        providerGameId: row.providerGameId,
        title: row.title,
        platformId: matched.id,
        monitored: true,
      },
      {
        onSuccess: (game) => {
          pushToast({
            kind: "success",
            title: t("add.successTitle"),
            description: t("add.successBody", { title: game.title }),
          });
          navigate(`/game/${game.id}`);
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("add.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  // Debounce URL writes so keystrokes don't pollute history,
  // and the API call key only updates once the operator pauses.
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed === urlQuery) return;
    const handle = window.setTimeout(() => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmed === "") next.delete("q");
          else next.set("q", trimmed);
          return next;
        },
        { replace: true },
      );
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, urlQuery, setSearchParams]);

  // No cap from the operator's perspective: 500 hits per query so
  // every (game, platform) combination IGDB / MobyGames /
  // ScreenScraper return surfaces in the list. Multi-platform
  // franchises (Harry Potter, Pokémon, Lego…) show up across
  // every console + handheld they shipped on.
  const lookup = useGameLookup({ q: urlQuery, limit: 500 });

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-4 space-y-1">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="text-sm text-zinc-400">{t("subtitle")}</p>
      </header>

      <label className="mb-4 block">
        <span className="sr-only">{t("search.label")}</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("search.placeholder")}
          aria-label={t("search.label")}
          autoFocus
          className={[
            "w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
            "ring-1 ring-inset ring-zinc-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        />
      </label>

      {urlQuery.length === 0 ? (
        <EmptyState
          title={t("empty.title")}
          description={t("empty.body")}
        />
      ) : lookup.isPending ? (
        <ListSkeleton rows={4} />
      ) : lookup.isError ? (
        <EmptyState
          title={t("loadError")}
          description={lookup.error.message}
        />
      ) : lookup.data.length === 0 ? (
        <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
          {t("noResults", { q: urlQuery })}
        </p>
      ) : (
        <>
          <FilterBar
            platforms={
              Array.from(
                new Map(
                  lookup.data
                    .filter((r) => r.platformSlug)
                    .map((r) => [
                      r.platformSlug!,
                      { slug: r.platformSlug!, name: r.platformName ?? r.platformSlug! },
                    ]),
                ).values(),
              )
            }
            years={
              Array.from(
                new Set(
                  lookup.data
                    .map((r) => r.releaseYear)
                    .filter((y): y is number => y !== null && y !== undefined),
                ),
              ).sort((a, b) => b - a)
            }
            providers={
              Array.from(
                new Set(
                  lookup.data.flatMap((r) =>
                    (r.providers ?? []).map((p) => p.name).concat(r.providerName),
                  ),
                ),
              ).sort()
            }
            filterPlatform={filterPlatform}
            setFilterPlatform={setFilterPlatform}
            filterYear={filterYear}
            setFilterYear={setFilterYear}
            filterProvider={filterProvider}
            setFilterProvider={setFilterProvider}
            open={filtersOpen}
            setOpen={setFiltersOpen}
            totalRows={lookup.data.length}
          />

          <ul className="space-y-2">
            {applyFilters(lookup.data, filterPlatform, filterYear, filterProvider).map((row) => (
              <LookupRow
                key={`${row.providerName}-${row.providerGameId}-${row.platformSlug ?? "any"}`}
                row={row}
                onAdd={handleAdd}
                onOpenDetail={setDetailRow}
                isAdding={directAdd.isPending}
              />
            ))}
          </ul>
          {applyFilters(lookup.data, filterPlatform, filterYear, filterProvider).length ===
            0 && (
            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
              {t("filters.noMatches")}
            </p>
          )}
          <p className="mt-3 rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("addHint")}
          </p>
        </>
      )}

      <RecentAdditions />

      {pendingAdd !== null && (
        <AddGameModal
          candidate={pendingAdd}
          onClose={() => setPendingAdd(null)}
        />
      )}

      {detailRow !== null && (
        <CandidateDetailModal
          row={detailRow}
          onClose={() => setDetailRow(null)}
          onAdd={(row) => {
            setDetailRow(null);
            handleAdd(row);
          }}
          onOpenAddModal={(row) => {
            setDetailRow(null);
            setPendingAdd(row);
          }}
          isAdding={directAdd.isPending}
        />
      )}
    </div>
  );
}

function CandidateDetailModal(props: {
  row: GameLookupRow;
  onClose: () => void;
  onAdd: (row: GameLookupRow) => void;
  onOpenAddModal: (row: GameLookupRow) => void;
  isAdding: boolean;
}): ReactElement {
  const { t } = useTranslation("addNew");
  const { row } = props;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("detail.modalTitle", { title: row.title })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start gap-3 border-b border-zinc-800 px-4 py-3">
          <CoverThumb url={row.coverUrl} title={row.title} />
          <div className="min-w-0 flex-1">
            <h2 className="break-words text-sm font-semibold text-zinc-100">
              {row.title}
            </h2>
            <p className="mt-0.5 text-[0.65rem] text-zinc-500">
              {t("detail.subhead", {
                provider: row.providerName,
                id: row.providerGameId,
              })}
            </p>
          </div>
        </header>

        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 px-4 py-4 text-xs">
          <DetailField
            label={t("detail.fields.platform")}
            value={
              row.platformName || row.platformSlug
                ? `${row.platformName ?? row.platformSlug ?? ""}${row.platformSlug ? ` · ${row.platformSlug}` : ""}`
                : null
            }
          />
          <DetailField
            label={t("detail.fields.manufacturer")}
            value={row.platformManufacturer ?? null}
          />
          <DetailField
            label={t("detail.fields.year")}
            value={row.releaseYear ? String(row.releaseYear) : null}
          />
          <DetailField
            label={t("detail.fields.confidence")}
            value={`${Math.round(row.confidence * 100)} %`}
          />
          <DetailField
            label={t("detail.fields.rank")}
            value={`#${row.rank + 1}`}
          />
          {row.coverUrl && (
            <>
              <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
                {t("detail.fields.coverUrl")}
              </dt>
              <dd className="min-w-0">
                <a
                  href={row.coverUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-[0.65rem] text-brand hover:underline"
                >
                  {row.coverUrl}
                </a>
              </dd>
            </>
          )}
        </dl>

        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("detail.actions.close")}
          </button>
          <button
            type="button"
            onClick={() => props.onOpenAddModal(row)}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("detail.actions.openAddModal")}
          </button>
          <button
            type="button"
            onClick={() => props.onAdd(row)}
            disabled={props.isAdding}
            className="inline-flex items-center gap-1 rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus size={12} aria-hidden="true" />
            {t("addButton")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function DetailField(props: {
  label: string;
  value: string | null;
}): ReactElement | null {
  if (props.value === null || props.value === "") return null;
  return (
    <>
      <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
        {props.label}
      </dt>
      <dd className="min-w-0 break-words text-zinc-200">{props.value}</dd>
    </>
  );
}
