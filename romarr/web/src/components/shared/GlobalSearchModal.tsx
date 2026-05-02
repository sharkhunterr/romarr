/**
 * Global search modal (T110-T113).
 *
 * Mounted once at the top of the AppLayout; visibility is
 * driven by `useSearchStore`. Three result groups today:
 *
 *   * Recent searches — last five queries, restorable.
 *   * Settings — fuzzy-match against the documented sub-page
 *                catalogue (slug + label) so the operator can
 *                jump straight to /settings/<slug>.
 *   * Games / Releases — placeholder until the backend ships
 *                        /api/v3/game search.
 *
 * Keyboard navigation: arrow keys cycle the visible-result
 * list; Enter opens the highlighted entry; Esc closes the
 * modal. The ⌘+K (Ctrl+K on non-Mac) hotkey is bound at the
 * AppLayout level via `useGlobalSearchHotkey`.
 */

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useSearchStore } from "@/lib/store/search";
import { SETTINGS_NAV_ENTRIES } from "@/pages/Settings/SettingsNav";

interface ResultRow {
  id: string;
  group: "recent" | "settings";
  label: string;
  hint?: string;
  emoji?: string;
  /** Resolves to a path on activate. */
  to: string;
  /** Original query for recent-row activation. */
  query?: string;
}

function matchesSettings(
  query: string,
  t: (key: string) => string,
): ResultRow[] {
  const q = query.trim().toLowerCase();
  if (q.length === 0) return [];
  const rows: ResultRow[] = [];
  for (const entry of SETTINGS_NAV_ENTRIES) {
    const label = t(`settings:nav.${entry.slug}`);
    const haystack = `${entry.slug} ${label}`.toLowerCase();
    if (haystack.includes(q)) {
      rows.push({
        id: `settings-${entry.slug}`,
        group: "settings",
        label,
        hint: entry.to,
        emoji: entry.emoji,
        to: entry.to,
      });
    }
  }
  return rows;
}

function recentRows(
  recent: readonly string[],
  query: string,
): ResultRow[] {
  if (query.trim().length > 0) return [];
  return recent.map((q, idx) => ({
    id: `recent-${idx}-${q}`,
    group: "recent",
    label: q,
    emoji: "🕘",
    to: "",
    query: q,
  }));
}

export function GlobalSearchModal(): ReactElement | null {
  const { t } = useTranslation(["search", "settings"]);
  const navigate = useNavigate();
  const open = useSearchStore((s) => s.open);
  const closeModal = useSearchStore((s) => s.closeModal);
  const recent = useSearchStore((s) => s.recent);
  const pushRecent = useSearchStore((s) => s.pushRecent);
  const clearRecent = useSearchStore((s) => s.clearRecent);

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Reset query and focus the input every time the modal opens.
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      // Defer focus so it lands after the modal mounts.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const settingsResults = useMemo(
    () => matchesSettings(query, t),
    [query, t],
  );
  const recentResults = useMemo(
    () => recentRows(recent, query),
    [recent, query],
  );
  const allResults = useMemo<ResultRow[]>(
    () => [...recentResults, ...settingsResults],
    [recentResults, settingsResults],
  );

  // Clamp active index whenever the result set changes.
  useEffect(() => {
    if (activeIndex >= allResults.length) {
      setActiveIndex(0);
    }
  }, [allResults.length, activeIndex]);

  if (!open) return null;

  function activate(row: ResultRow): void {
    if (row.group === "recent" && row.query !== undefined) {
      setQuery(row.query);
      return;
    }
    pushRecent(row.label);
    closeModal();
    if (row.to) {
      navigate(row.to);
    }
  }

  function onKeyDown(event: React.KeyboardEvent): void {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((idx) =>
        allResults.length === 0 ? 0 : (idx + 1) % allResults.length,
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((idx) =>
        allResults.length === 0
          ? 0
          : (idx - 1 + allResults.length) % allResults.length,
      );
    } else if (event.key === "Enter") {
      const row = allResults[activeIndex];
      if (row) {
        event.preventDefault();
        activate(row);
      } else if (query.trim().length > 0) {
        // No exact match — store the query in recent and close.
        event.preventDefault();
        pushRecent(query);
        closeModal();
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("search:ariaLabel")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[10vh] backdrop-blur-sm"
      onClick={closeModal}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-zinc-800 p-3">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onKeyDown}
            placeholder={t("search:placeholder")}
            aria-label={t("search:ariaLabel")}
            className="w-full bg-transparent px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500 focus-visible:outline-none"
          />
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {recentResults.length > 0 && (
            <ResultGroup
              heading={t("search:groups.recent")}
              actionLabel={t("search:clearRecent")}
              onAction={clearRecent}
            >
              {recentResults.map((row, idx) => (
                <ResultRowButton
                  key={row.id}
                  row={row}
                  active={
                    activeIndex ===
                    allResults.findIndex((r) => r.id === row.id)
                  }
                  onActivate={() => activate(row)}
                  onHover={() =>
                    setActiveIndex(
                      allResults.findIndex((r) => r.id === row.id),
                    )
                  }
                  index={idx}
                />
              ))}
            </ResultGroup>
          )}

          {settingsResults.length > 0 && (
            <ResultGroup heading={t("search:groups.settings")}>
              {settingsResults.map((row) => (
                <ResultRowButton
                  key={row.id}
                  row={row}
                  active={
                    activeIndex ===
                    allResults.findIndex((r) => r.id === row.id)
                  }
                  onActivate={() => activate(row)}
                  onHover={() =>
                    setActiveIndex(
                      allResults.findIndex((r) => r.id === row.id),
                    )
                  }
                  index={0}
                />
              ))}
            </ResultGroup>
          )}

          {allResults.length === 0 && (
            <div className="px-3 py-8 text-center">
              <p className="text-sm text-zinc-400">
                {query.trim().length === 0
                  ? t("search:empty.typeToSearch")
                  : t("search:empty.noResults", { query: query.trim() })}
              </p>
            </div>
          )}

          <div className="mt-2 border-t border-zinc-800 pt-2">
            <p className="px-3 py-1 text-[0.6rem] text-zinc-600">
              {t("search:groups.games")} —{" "}
              <span className="text-zinc-700">
                {t("search:deferred.games")}
              </span>
            </p>
            <p className="px-3 py-1 text-[0.6rem] text-zinc-600">
              {t("search:groups.releases")} —{" "}
              <span className="text-zinc-700">
                {t("search:deferred.releases")}
              </span>
            </p>
          </div>
        </div>

        <div className="border-t border-zinc-800 px-3 py-1.5">
          <p className="font-mono text-[0.6rem] text-zinc-600">
            {t("search:navigateHint")}
          </p>
        </div>
      </div>
    </div>
  );
}

interface ResultGroupProps {
  heading: string;
  actionLabel?: string;
  onAction?: () => void;
  children: ReactElement | ReactElement[];
}

function ResultGroup(props: ResultGroupProps): ReactElement {
  return (
    <section className="mb-3 last:mb-0">
      <header className="flex items-center justify-between px-2 py-1">
        <h3 className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
          {props.heading}
        </h3>
        {props.actionLabel && props.onAction && (
          <button
            type="button"
            onClick={props.onAction}
            className="text-[0.6rem] text-zinc-500 hover:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {props.actionLabel}
          </button>
        )}
      </header>
      <ul className="space-y-0.5">{props.children}</ul>
    </section>
  );
}

interface ResultRowButtonProps {
  row: ResultRow;
  active: boolean;
  onActivate: () => void;
  onHover: () => void;
  index: number;
}

function ResultRowButton(props: ResultRowButtonProps): ReactElement {
  const { row, active, onActivate, onHover } = props;
  return (
    <li>
      <button
        type="button"
        onClick={onActivate}
        onMouseEnter={onHover}
        className={[
          "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
          active ? "bg-zinc-800 text-zinc-100" : "text-zinc-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        ].join(" ")}
      >
        {row.emoji && (
          <span aria-hidden="true" className="text-base leading-none">
            {row.emoji}
          </span>
        )}
        <span className="flex-1 truncate">{row.label}</span>
        {row.hint && (
          <span className="font-mono text-[0.6rem] text-zinc-500">
            {row.hint}
          </span>
        )}
      </button>
    </li>
  );
}

/**
 * Bind the global Ctrl/Cmd+K hotkey. Returns a no-arg cleanup
 * function so the AppLayout `useEffect` can restore the
 * listener cleanly.
 */
export function useGlobalSearchHotkey(): void {
  const toggleModal = useSearchStore((s) => s.toggleModal);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggleModal();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleModal]);
}
