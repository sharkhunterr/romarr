/**
 * Settings > ROM Pack Defaults (slice 464).
 *
 * Global defaults for the ROM-pack subsystem — the operational
 * page lives at the top-level ``/rom-packs`` route; this is just
 * the tunable defaults behind it:
 *
 *   - **Download directory** — where url-sourced pack archives
 *     stream to disk and extract under.
 *   - **Default size cap** — the per-pack download ceiling a
 *     pack inherits when it doesn't pin its own.
 *
 * Strings resolve through ``settings:romPackSettings.*``.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import {
  useRomPackConfig,
  useUpdateRomPackConfig,
} from "@/lib/api/queries/rom-packs";
import { useToastStore } from "@/lib/store/toast";

const _GIB = 1024 ** 3;

export function RomPackSettingsPage(): ReactElement {
  const { t } = useTranslation("settings");
  const config = useRomPackConfig();
  const update = useUpdateRomPackConfig();
  const pushToast = useToastStore((s) => s.push);

  const [downloadDir, setDownloadDir] = useState("");
  const [maxGib, setMaxGib] = useState("");

  // Hydrate the form once the config query resolves.
  useEffect(() => {
    if (config.data === undefined) return;
    setDownloadDir(config.data.download_dir);
    setMaxGib(
      config.data.default_max_size_bytes != null
        ? String(config.data.default_max_size_bytes / _GIB)
        : "",
    );
  }, [config.data]);

  function onSave(): void {
    const parsed = Number.parseFloat(maxGib);
    const default_max_size_bytes =
      Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * _GIB) : null;
    update.mutate(
      { download_dir: downloadDir.trim(), default_max_size_bytes },
      {
        onSuccess: () =>
          pushToast({
            kind: "success",
            title: t("romPackSettings.savedToast"),
          }),
        onError: (err) =>
          pushToast({
            kind: "error",
            title: t("romPackSettings.saveErrorToast"),
            description: err.message,
          }),
      },
    );
  }

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("romPackSettings.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("romPackSettings.subtitle")}
        </p>
      </header>

      {config.isLoading && <ListSkeleton rows={2} />}

      {config.isError && (
        <p className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {config.error.message}
        </p>
      )}

      {config.isSuccess && (
        <section className="max-w-lg space-y-3">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("romPackSettings.downloadDirLabel")}
            </span>
            <input
              type="text"
              value={downloadDir}
              onChange={(e) => setDownloadDir(e.target.value)}
              placeholder="/downloads/rom_packs"
              disabled={update.isPending}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("romPackSettings.downloadDirHint")}
            </p>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("romPackSettings.maxSizeLabel")}
            </span>
            <input
              type="number"
              min="0"
              step="1"
              value={maxGib}
              onChange={(e) => setMaxGib(e.target.value)}
              placeholder="50"
              disabled={update.isPending}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("romPackSettings.maxSizeHint")}
            </p>
          </label>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={onSave}
              disabled={update.isPending || downloadDir.trim().length === 0}
              className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {update.isPending
                ? t("romPackSettings.saving")
                : t("romPackSettings.save")}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
