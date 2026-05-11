/**
 * Slice 402 — platform detail modal.
 *
 * Surfaces every field on ``PlatformRead``: identity (slug,
 * name, short_name, manufacturer, year, generation), aliases
 * used by the grab + manual-search detectors, on-disk format
 * extensions, metadata provider IDs (IGDB / ScreenScraper /
 * MobyGames / LaunchBox / RetroAchievements), and the pack
 * provenance (source + version) that introduced the row.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { Platform } from "@/lib/api/queries/platforms";

interface PlatformDetailModalProps {
  platform: Platform;
  onClose: () => void;
}

export function PlatformDetailModal(
  props: PlatformDetailModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const { platform } = props;
  const aliases = platform.aliases ?? [];
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("platforms.detail.modalTitle", { name: platform.name })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[6vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
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

        <footer className="flex items-center justify-end border-t border-zinc-800 px-4 py-3">
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
