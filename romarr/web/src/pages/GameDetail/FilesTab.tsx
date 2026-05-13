/**
 * GameDetail > Files tab (slices 95 + 447).
 *
 * Lists every Dump owned by the game (joined through Releases)
 * via ``GET /api/v3/game/{id}/dump``. Each row carries the on-
 * disk projection: filename, format, size, imported_at, hashes,
 * plus a DAT-verified badge. When a DAT entry actually matched
 * the dump's SHA-1 the tab expands a verbose panel with the
 * canonical DAT name, indexed size, status, and authority — so
 * the operator can see *what* the file matched, not just *that*
 * it matched.
 *
 * Strings resolve through ``game:files.*``.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { DatVerifiedBadge, HashBadge } from "@/components/rom";
import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useDumpsForGame, type Dump } from "@/lib/api/queries/games";

interface FilesTabProps {
  gameId: number;
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KiB", "MiB", "GiB", "TiB"];
  const i = Math.min(
    sizes.length - 1,
    Math.floor(Math.log(bytes) / Math.log(k)),
  );
  return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 2)} ${sizes[i]}`;
}

function DatMatchPanel(props: { dump: Dump }): ReactElement | null {
  const { t } = useTranslation("game");
  const { dump } = props;
  // No match = nothing to expand.
  if (dump.dat_source === null || dump.dat_source === undefined) return null;
  // No joined entry payload (legacy row pre-447 enrichment): we
  // still know it matched, but can't show the canonical name —
  // fall back to a one-liner.
  const hasEntry =
    dump.dat_entry_name !== null && dump.dat_entry_name !== undefined;
  const verified = dump.dat_verified;
  const statusLabel = dump.dat_entry_status ?? "?";

  return (
    <div
      className={[
        "mt-1 grid gap-x-3 gap-y-1 rounded-md border px-3 py-2 text-[0.7rem]",
        verified
          ? "border-emerald-700/40 bg-emerald-900/15"
          : "border-amber-700/40 bg-amber-900/15",
        "sm:grid-cols-[7rem_1fr]",
      ].join(" ")}
    >
      <p
        className={`col-span-full font-medium ${
          verified ? "text-emerald-200" : "text-amber-200"
        }`}
      >
        {t(`files.datMatch.${verified ? "ok" : "warning"}`)}
      </p>

      <span className="text-zinc-500">{t("files.datMatch.source")}</span>
      <span className="font-mono text-zinc-200">{dump.dat_source}</span>

      {hasEntry && (
        <>
          <span className="text-zinc-500">
            {t("files.datMatch.entryName")}
          </span>
          <span className="truncate text-zinc-200" title={dump.dat_entry_name ?? ""}>
            {dump.dat_entry_name}
          </span>

          <span className="text-zinc-500">
            {t("files.datMatch.entrySize")}
          </span>
          <span className="font-mono text-zinc-300">
            {formatBytes(dump.dat_entry_size_bytes)}
          </span>

          <span className="text-zinc-500">
            {t("files.datMatch.entryStatus")}
          </span>
          <span className="font-mono uppercase tracking-wide text-zinc-300">
            {statusLabel}
          </span>
        </>
      )}
    </div>
  );
}

function DumpRow(props: { dump: Dump }): ReactElement {
  const { t, i18n } = useTranslation("game");
  const { dump } = props;
  const importedAt = dump.imported_at
    ? new Date(dump.imported_at).toLocaleString(i18n.language)
    : null;

  return (
    <li
      className={[
        "flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-zinc-100">
            {dump.original_filename}
          </p>
          <p
            className="truncate font-mono text-[0.65rem] text-zinc-500"
            title={dump.path}
          >
            {dump.path}
          </p>
        </div>
        <DatVerifiedBadge
          verified={dump.dat_verified}
          source={dump.dat_source ?? null}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-zinc-500">
        <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono uppercase tracking-wider text-zinc-400">
          {dump.format}
        </span>
        <span>{formatBytes(dump.size_bytes)}</span>
        {importedAt && (
          <>
            <span>·</span>
            <span>
              {t("files.importedAt", {
                when: importedAt,
                via: dump.imported_via ?? "—",
              })}
            </span>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <HashBadge type="CRC32" value={dump.crc32} truncate={8} />
        <HashBadge type="MD5" value={dump.md5} truncate={12} />
        <HashBadge type="SHA1" value={dump.sha1} truncate={12} />
        {dump.sha256 && (
          <HashBadge type="SHA256" value={dump.sha256} truncate={12} />
        )}
      </div>

      <DatMatchPanel dump={dump} />
    </li>
  );
}

export function FilesTab(props: FilesTabProps): ReactElement {
  const { t } = useTranslation("game");
  const dumps = useDumpsForGame(props.gameId);

  if (dumps.isPending) return <ListSkeleton rows={3} />;
  if (dumps.isError) {
    return (
      <EmptyState
        title={t("files.loadError")}
        description={dumps.error.message}
      />
    );
  }
  if (dumps.data.length === 0) {
    return (
      <EmptyState
        title={t("files.empty.title")}
        description={t("files.empty.body")}
      />
    );
  }

  return (
    <ul className="space-y-2">
      {dumps.data.map((dump) => (
        <DumpRow key={dump.id} dump={dump} />
      ))}
    </ul>
  );
}
