/**
 * TriageModal (slice 462).
 *
 * Resolves the ROMs a pack ingest left ``unmatched`` — files
 * whose hash hit no DAT entry. Each row offers three exits:
 *
 *   - **Associate** — pick an existing Game; the backend runs
 *     the standard importer with that Game pinned and the ROM
 *     lands in its Library.
 *   - **Park** — hand the file to ``unidentified_dump`` so it
 *     shows up under Settings → Unidentified for later work.
 *   - **Delete** — remove the extracted file from disk.
 *
 * Once every unmatched ROM is resolved the pack flips
 * ``awaiting_triage`` → ``done`` server-side; the list refetch
 * picks that up.
 *
 * Strings resolve through ``settings:romPacks.triage.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { ApiError } from "@/lib/api/client";
import { useGames } from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import {
  useAssociateRomPackItem,
  useDeleteRomPackItem,
  useParkRomPackItem,
  useRomPackItems,
  type RomPackItemRead,
  type RomPackRead,
} from "@/lib/api/queries/rom-packs";
import { useToastStore } from "@/lib/store/toast";

interface TriageRowProps {
  pack: RomPackRead;
  item: RomPackItemRead;
}

function TriageRow({ pack, item }: TriageRowProps): ReactElement {
  const { t } = useTranslation("settings");
  const pushToast = useToastStore((s) => s.push);
  const associate = useAssociateRomPackItem();
  const park = useParkRomPackItem();
  const del = useDeleteRomPackItem();

  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const platformsById = usePlatformsById();
  const games = useGames({
    q: query.trim().length > 0 ? query : undefined,
    platformId: pack.platform_id ?? undefined,
    limit: 8,
  });

  const busy = associate.isPending || park.isPending || del.isPending;

  function _onError(err: ApiError): void {
    const raw = err.details as unknown;
    const details =
      typeof raw === "string"
        ? raw
        : raw !== undefined && raw !== null
          ? JSON.stringify(raw)
          : undefined;
    pushToast({
      kind: "error",
      title: t("romPacks.triage.actionErrorToast"),
      description: details ?? err.message,
    });
  }

  function onAssociate(gameId: number, gameTitle: string): void {
    associate.mutate(
      { packId: pack.id, itemId: item.id, gameId },
      {
        onSuccess: () => {
          setPicking(false);
          pushToast({
            kind: "success",
            title: t("romPacks.triage.associatedToast", {
              file: item.original_filename,
              game: gameTitle,
            }),
          });
        },
        onError: _onError,
      },
    );
  }

  function onPark(): void {
    park.mutate(
      { packId: pack.id, itemId: item.id },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("romPacks.triage.parkedToast", {
              file: item.original_filename,
            }),
          }),
        onError: _onError,
      },
    );
  }

  function onDelete(): void {
    if (
      !window.confirm(
        t("romPacks.triage.deleteConfirm", {
          file: item.original_filename,
        }),
      )
    ) {
      return;
    }
    del.mutate(
      { packId: pack.id, itemId: item.id },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("romPacks.triage.deletedToast", {
              file: item.original_filename,
            }),
          }),
        onError: _onError,
      },
    );
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-zinc-100">
            {item.original_filename}
          </p>
          {item.sha1 !== null && (
            <p className="mt-0.5 truncate font-mono text-[0.6rem] text-zinc-600">
              sha1:{item.sha1}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setPicking((v) => !v)}
            disabled={busy}
            className="rounded border border-brand/60 px-2 py-1 text-[0.65rem] font-medium text-brand hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("romPacks.triage.action.associate")}
          </button>
          <button
            type="button"
            onClick={onPark}
            disabled={busy}
            className="rounded border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("romPacks.triage.action.park")}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={busy}
            className="rounded border border-rose-700/50 px-2 py-1 text-[0.65rem] font-medium text-rose-200 hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("romPacks.triage.action.delete")}
          </button>
        </div>
      </div>

      {picking && (
        <div className="mt-2 space-y-2 border-t border-zinc-800 pt-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("romPacks.triage.searchPlaceholder")}
            autoFocus
            className="w-full rounded-md bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
          {games.isLoading && (
            <p className="text-[0.65rem] text-zinc-500">
              {t("romPacks.triage.searching")}
            </p>
          )}
          {games.isSuccess && games.data.length === 0 && (
            <p className="text-[0.65rem] text-zinc-500">
              {t("romPacks.triage.noGames")}
            </p>
          )}
          {games.isSuccess && games.data.length > 0 && (
            <ul className="max-h-44 space-y-1 overflow-y-auto">
              {games.data.map((g) => (
                <li key={g.id}>
                  <button
                    type="button"
                    onClick={() => onAssociate(g.id, g.title)}
                    disabled={busy}
                    className="flex w-full items-center justify-between gap-2 rounded border border-zinc-800 px-2 py-1.5 text-left text-xs text-zinc-200 hover:border-brand/50 hover:bg-brand/5 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="truncate">{g.title}</span>
                    <span className="shrink-0 font-mono text-[0.6rem] text-zinc-500">
                      {platformsById.get(g.platform_id)?.slug ??
                        `#${g.platform_id}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

interface TriageModalProps {
  pack: RomPackRead;
  onClose: () => void;
}

export function TriageModal({ pack, onClose }: TriageModalProps): ReactElement {
  const { t } = useTranslation("settings");
  const items = useRomPackItems(pack.id, "unmatched");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("romPacks.triage.title", { name: pack.name })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("romPacks.triage.title", { name: pack.name })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("romPacks.triage.subhead")}
          </p>
        </header>

        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {items.isLoading && <ListSkeleton rows={4} />}

          {items.isError && (
            <EmptyState
              title={t("romPacks.triage.loadError")}
              description={items.error.message}
            />
          )}

          {items.isSuccess && items.data.length === 0 && (
            <EmptyState
              title={t("romPacks.triage.allDone.title")}
              description={t("romPacks.triage.allDone.body")}
            />
          )}

          {items.isSuccess && items.data.length > 0 && (
            <ul className="space-y-2">
              {items.data.map((item) => (
                <TriageRow key={item.id} pack={pack} item={item} />
              ))}
            </ul>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t border-zinc-800 bg-zinc-950/50 px-4 py-3">
          <span className="text-[0.65rem] text-zinc-500">
            {items.isSuccess
              ? t("romPacks.triage.remaining", { count: items.data.length })
              : ""}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("romPacks.triage.close")}
          </button>
        </footer>
      </div>
    </div>
  );
}
