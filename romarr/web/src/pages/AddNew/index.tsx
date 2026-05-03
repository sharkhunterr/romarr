/**
 * Add New page (P-ADD, slice 144).
 *
 * Operator-driven search across every enabled metadata
 * provider. Drives the spec 014 "Add New" workflow's first
 * step: find the game in the canonical metadata catalogue
 * before adding it to the Library.
 *
 * The "Add this game" button is intentionally deferred — the
 * full add-to-library mutation is multi-step (pick library,
 * pick monitored, pick profile overrides) and lands in a
 * follow-up slice. Today the page surfaces the lookup
 * candidates so the dependency on the metadata provider
 * surface is visible end-to-end.
 *
 * Strings resolve through the `addNew` namespace.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useGameLookup, type GameLookupRow } from "@/lib/api/queries/lookup";

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

function LookupRow(props: { row: GameLookupRow }): ReactElement {
  const { row } = props;
  return (
    <li
      className={[
        "flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">
          {row.title}
        </p>
        <ConfidenceBar value={row.confidence} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-500">
        <ProviderPill name={row.providerName} />
        <span className="font-mono">id: {row.providerGameId}</span>
      </div>
    </li>
  );
}

export function AddNewPage(): ReactElement {
  const { t } = useTranslation("addNew");
  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = useState(urlQuery);

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

  const lookup = useGameLookup({ q: urlQuery, limit: 50 });

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
          <ul className="space-y-2">
            {lookup.data.map((row) => (
              <LookupRow key={`${row.providerName}-${row.providerGameId}`} row={row} />
            ))}
          </ul>
          <p className="mt-3 rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-3 text-[0.7rem] text-zinc-500">
            {t("addHint")}
          </p>
        </>
      )}
    </div>
  );
}
