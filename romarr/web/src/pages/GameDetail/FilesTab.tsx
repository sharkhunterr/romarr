/**
 * GameDetail > Files tab (slice 95).
 *
 * Lists every Dump owned by the game (joined through Releases)
 * via the new `GET /api/v3/game/{id}/dump` endpoint. Each row
 * surfaces the on-disk projection: filename, format, size,
 * imported_at, DAT verification badge, and the three guaranteed
 * hashes (CRC32, MD5, SHA-1) as copyable HashBadges. SHA-256
 * is rendered when present (it's optional per FR-014).
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

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KiB", "MiB", "GiB", "TiB"];
  const i = Math.min(
    sizes.length - 1,
    Math.floor(Math.log(bytes) / Math.log(k)),
  );
  return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 2)} ${sizes[i]}`;
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
          source={dump.dat_source ?? undefined}
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
