/**
 * Game detail page (P-GAME, slices 89, 149, 167).
 *
 * Tabbed view: Overview / Releases / History / Files / Notes.
 * Manual Search remains deferred until the indexer search UI
 * lands.
 *
 * Slice 167 adds a destructive "Delete game" action in the
 * page header that reuses ``BulkDeleteModal`` with the single
 * game pre-selected. On success it navigates back to /library
 * since the row no longer exists.
 */

import { Search, Trash2 } from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { DetailSkeleton } from "@/components/shared/LoadingSkeleton";
import { useGame } from "@/lib/api/queries/games";
import { BulkDeleteModal } from "@/pages/Library/BulkDeleteModal";

import { FilesTab } from "./FilesTab";
import { HistoryTab } from "./HistoryTab";
import { NotesTab } from "./NotesTab";
import { OverviewTab } from "./OverviewTab";
import { PendingDownloads } from "./PendingDownloads";
import { ReleaseSearchModal } from "./ReleaseSearchModal";
import { ReleasesTab } from "./ReleasesTab";

type Tab = "overview" | "releases" | "history" | "files" | "notes";

const TABS: readonly Tab[] = [
  "overview",
  "releases",
  "history",
  "files",
  "notes",
];

const TAB_SET: ReadonlySet<Tab> = new Set(TABS);

function parseTabParam(raw: string | null): Tab {
  return raw !== null && TAB_SET.has(raw as Tab) ? (raw as Tab) : "overview";
}

interface TabButtonProps {
  tab: Tab;
  active: boolean;
  label: string;
  onClick: (tab: Tab) => void;
}

function TabButton(props: TabButtonProps): ReactElement {
  return (
    <button
      type="button"
      onClick={() => props.onClick(props.tab)}
      className={[
        "flex-1 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors",
        props.active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
      ].join(" ")}
      aria-pressed={props.active}
    >
      {props.label}
    </button>
  );
}

export function GameDetailPage(): ReactElement {
  const { t } = useTranslation("game");
  const navigate = useNavigate();
  const { gameId: gameIdRaw } = useParams<{ gameId: string }>();
  const gameId = gameIdRaw ? Number(gameIdRaw) : null;
  const game = useGame(gameId);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTabParam(searchParams.get("tab"));
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const setTab = (next: Tab): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "overview") params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: false },
    );
  };

  if (gameId === null || Number.isNaN(gameId)) {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
        <EmptyState title={t("notFound")} />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      {game.isLoading && <DetailSkeleton />}
      {game.isError && (
        <EmptyState
          title={t("loadError")}
          description={game.error.message}
        />
      )}

      {game.isSuccess && (
        <>
          <PendingDownloads gameId={gameId} />
          <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-brand/60 bg-brand/10 px-2 py-1 text-[0.65rem] font-medium text-brand hover:bg-brand/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <Search size={12} aria-hidden="true" />
              {t("search.headerButton")}
            </button>
            <button
              type="button"
              onClick={() => setDeleteOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-700/60 px-2 py-1 text-[0.65rem] font-medium text-red-300 hover:bg-red-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              <Trash2 size={12} aria-hidden="true" />
              {t("delete.button")}
            </button>
          </div>
          <div
            role="tablist"
            aria-label={t("tabs.ariaLabel")}
            className="mb-4 grid grid-cols-5 gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
          >
            {TABS.map((id) => (
              <TabButton
                key={id}
                tab={id}
                active={tab === id}
                label={t(`tabs.${id}`)}
                onClick={setTab}
              />
            ))}
          </div>

          {tab === "overview" && <OverviewTab game={game.data} />}
          {tab === "releases" && (
            <ReleasesTab
              gameId={gameId}
              platformId={game.data.platform_id}
            />
          )}
          {tab === "history" && <HistoryTab gameId={gameId} />}
          {tab === "files" && <FilesTab gameId={gameId} />}
          {tab === "notes" && <NotesTab game={game.data} />}

          {deleteOpen && (
            <BulkDeleteModal
              games={[game.data]}
              onClose={() => setDeleteOpen(false)}
              onSuccess={() => navigate("/library")}
            />
          )}

          <ReleaseSearchModal
            open={searchOpen}
            onClose={() => setSearchOpen(false)}
            initialQuery={game.data.title}
            platformId={game.data.platform_id}
            releaseId={null}
          />
        </>
      )}
    </div>
  );
}
