/**
 * Slice 402 — platform detail modal.
 *
 * Surfaces every field on ``PlatformRead``: identity (slug,
 * name, short_name, manufacturer, year, generation), aliases
 * used by the grab + manual-search detectors, metadata provider
 * IDs (IGDB / ScreenScraper / MobyGames / LaunchBox /
 * RetroAchievements), and the pack provenance (source +
 * version) that introduced the row.
 *
 * Also folds the former "Quality Definitions" catalogue in as a
 * ``Formats`` section — each recognised extension, its
 * ``format_type`` (cartridge / disc / …), size floor/ceiling,
 * and the pack it came from. Editing per-format lives under the
 * admin per-platform format CRUD.
 */

import { useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { Platform } from "@/lib/api/queries/platforms";
import {
  useQualityDefinitions,
  type QualityDefinitionFormat,
} from "@/lib/api/queries/quality-definitions";

interface PlatformDetailModalProps {
  platform: Platform;
  onClose: () => void;
}

const _MB = 1024 * 1024;

function _formatSize(bytes: number | null, unbounded: string): string {
  if (bytes === null) return unbounded;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < _MB) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * _MB) return `${(bytes / _MB).toFixed(1)} MB`;
  return `${(bytes / (1024 * _MB)).toFixed(2)} GB`;
}

export function PlatformDetailModal(
  props: PlatformDetailModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const { platform } = props;
  const aliases = platform.aliases ?? [];
  const qualityDefs = useQualityDefinitions();
  const formats: QualityDefinitionFormat[] = useMemo(() => {
    if (!qualityDefs.isSuccess) return [];
    const entry = qualityDefs.data.find(
      (p) => p.platform_id === platform.id,
    );
    return entry?.formats ?? [];
  }, [qualityDefs.isSuccess, qualityDefs.data, platform.id]);
  const unbounded = t("platforms.detail.unbounded");
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("platforms.detail.modalTitle", { name: platform.name })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-lg flex max-h-[92vh] flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="break-words text-sm font-semibold text-zinc-100">
            {platform.name}
          </h2>
          <p className="mt-0.5 font-mono text-[0.65rem] text-zinc-500">
            <code>{platform.slug}</code>
            {platform.short_name && ` · ${platform.short_name}`}
            {platform.manufacturer && ` · ${platform.manufacturer}`}
          </p>
        </header>

        <div className="max-h-[70vh] space-y-4 overflow-auto p-4 text-xs">
          {aliases.length > 0 && (
            <Section title={t("platforms.detail.sections.aliases")}>
              <div className="flex flex-wrap gap-1">
                {aliases.map((a) => (
                  <span
                    key={a}
                    className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.65rem] text-zinc-300"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </Section>
          )}

          <Section title={t("platforms.detail.sections.identity")}>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5">
              <Field
                label={t("platforms.detail.fields.slug")}
                value={platform.slug}
                mono
              />
              <Field
                label={t("platforms.detail.fields.name")}
                value={platform.name}
              />
              <Field
                label={t("platforms.detail.fields.shortName")}
                value={platform.short_name ?? null}
              />
              <Field
                label={t("platforms.detail.fields.manufacturer")}
                value={platform.manufacturer ?? null}
              />
              <Field
                label={t("platforms.detail.fields.releaseYear")}
                value={
                  platform.release_year ? String(platform.release_year) : null
                }
              />
              <Field
                label={t("platforms.detail.fields.pack")}
                value={`${platform.pack_source}${platform.pack_version ? ` · ${platform.pack_version}` : ""}`}
              />
            </dl>
          </Section>

          <Section title={t("platforms.detail.sections.providerIds")}>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5">
              <Field
                label="IGDB"
                value={platform.igdb_id ? String(platform.igdb_id) : null}
              />
              <Field
                label="ScreenScraper"
                value={
                  platform.screenscraper_id
                    ? String(platform.screenscraper_id)
                    : null
                }
              />
              <Field
                label="MobyGames"
                value={
                  platform.mobygames_id ? String(platform.mobygames_id) : null
                }
              />
              <Field
                label="LaunchBox"
                value={
                  platform.launchbox_id ? String(platform.launchbox_id) : null
                }
              />
              <Field
                label="RetroAchievements"
                value={
                  platform.retroachievements_id
                    ? String(platform.retroachievements_id)
                    : null
                }
              />
            </dl>
          </Section>

          <Section title={t("platforms.detail.sections.formats")}>
            {qualityDefs.isLoading && (
              <p className="text-[0.7rem] text-zinc-500">
                {t("platforms.detail.formats.loading")}
              </p>
            )}
            {qualityDefs.isError && (
              <p className="text-[0.7rem] text-red-400">
                {qualityDefs.error.message}
              </p>
            )}
            {qualityDefs.isSuccess && formats.length === 0 && (
              <p className="text-[0.7rem] text-zinc-500">
                {t("platforms.detail.formats.empty")}
              </p>
            )}
            {qualityDefs.isSuccess && formats.length > 0 && (
              <div className="-mx-4 overflow-x-auto sm:mx-0">
                <table className="min-w-full text-[0.7rem]">
                  <thead className="text-[0.6rem] uppercase tracking-widest text-zinc-500">
                    <tr>
                      <th className="px-2 py-1 text-left">
                        {t("platforms.detail.formats.extension")}
                      </th>
                      <th className="px-2 py-1 text-left">
                        {t("platforms.detail.formats.type")}
                      </th>
                      <th className="px-2 py-1 text-right">
                        {t("platforms.detail.formats.minSize")}
                      </th>
                      <th className="px-2 py-1 text-right">
                        {t("platforms.detail.formats.maxSize")}
                      </th>
                      <th className="px-2 py-1 text-left">
                        {t("platforms.detail.formats.source")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {formats.map((f) => (
                      <tr
                        key={f.id}
                        className="border-t border-zinc-800/60"
                      >
                        <td className="px-2 py-1 font-mono text-zinc-100">
                          {f.extension}
                        </td>
                        <td className="px-2 py-1 text-zinc-300">
                          {f.format_type}
                        </td>
                        <td className="px-2 py-1 text-right font-mono text-zinc-400">
                          {_formatSize(f.min_size_bytes, unbounded)}
                        </td>
                        <td className="px-2 py-1 text-right font-mono text-zinc-400">
                          {_formatSize(f.max_size_bytes, unbounded)}
                        </td>
                        <td className="px-2 py-1">
                          <span
                            className={[
                              "rounded px-1.5 py-0.5 text-[0.6rem]",
                              f.pack_source === "builtin"
                                ? "bg-zinc-800 text-zinc-300"
                                : "bg-emerald-700/30 text-emerald-200",
                            ].join(" ")}
                          >
                            {f.pack_source}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {platform.newznab_category_ids &&
            platform.newznab_category_ids.length > 0 && (
              <Section
                title={t("platforms.detail.sections.newznabCategories")}
              >
                <div className="flex flex-wrap gap-1">
                  {platform.newznab_category_ids.map((cat) => (
                    <span
                      key={cat}
                      className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.65rem] text-zinc-300"
                    >
                      {cat}
                    </span>
                  ))}
                </div>
              </Section>
            )}
        </div>

        <footer className="flex shrink-0 items-center justify-end border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("platforms.detail.close")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function Section(props: {
  title: string;
  children: React.ReactNode;
}): ReactElement {
  return (
    <section>
      <h3 className="mb-1.5 text-[0.6rem] uppercase tracking-widest text-zinc-500">
        {props.title}
      </h3>
      {props.children}
    </section>
  );
}

function Field(props: {
  label: string;
  value: string | null;
  mono?: boolean;
}): ReactElement | null {
  if (props.value === null || props.value === "") return null;
  return (
    <>
      <dt className="font-mono text-[0.6rem] uppercase tracking-widest text-zinc-500">
        {props.label}
      </dt>
      <dd
        className={[
          "min-w-0 break-words text-zinc-200",
          props.mono ? "font-mono text-[0.65rem]" : "",
        ]
          .join(" ")
          .trim()}
      >
        {props.value}
      </dd>
    </>
  );
}
