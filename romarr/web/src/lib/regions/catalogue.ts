/**
 * Region catalogue (slice 350).
 *
 * The pipeline normalises every region (filename-parsed or
 * indexer-extended-attr) to a two-letter ISO code via the backend's
 * ``normalize_region`` (see
 * ``src/romarr/indexers/parser/extended_attrs.py``). This catalogue
 * is the operator-facing surface: the multi-select shows the
 * label, stores the canonical code on the profile, and surfaces
 * the known aliases as a hint so the operator can see *what*
 * filename or attr inputs map to this bucket.
 *
 * Order matches the typical preservation operator's priority list
 * (Europe → Worldwide → USA → Japan → minor regions). The "extra"
 * column at the end (``UK``, ``CHN``, etc.) is rarely used as a
 * priority but appears so it can be picked when relevant.
 */
export interface RegionCatalogueEntry {
  /** ISO 3166-1 alpha-2 code (or ``WW`` for worldwide), as
   * stored in ``RegionProfile.priorities`` and consumed by the
   * pipeline's region evaluator. */
  code: string;
  /** Localisation key under ``settings:profiles.region.catalogue``;
   * keeps the English/French label in the i18n bundle. */
  i18nKey: string;
  /** Filename / extended-attr inputs the backend's
   * ``normalize_region`` knows how to fold into this code. Shown as
   * a hint so the operator understands what the bucket contains. */
  aliases: readonly string[];
}

export const REGION_CATALOGUE: readonly RegionCatalogueEntry[] = [
  {
    code: "EU",
    i18nKey: "europe",
    aliases: ["EU", "EUR", "Europe", "European"],
  },
  {
    code: "WW",
    i18nKey: "worldwide",
    aliases: ["WW", "WORLD", "World", "Worldwide"],
  },
  { code: "US", i18nKey: "usa", aliases: ["US", "USA", "United States", "America"] },
  { code: "JP", i18nKey: "japan", aliases: ["JP", "JA", "JPN", "Japan", "Japanese"] },
  { code: "FR", i18nKey: "france", aliases: ["FR", "FRA", "France"] },
  { code: "DE", i18nKey: "germany", aliases: ["DE", "GER", "DEU", "Germany"] },
  { code: "IT", i18nKey: "italy", aliases: ["IT", "ITA", "Italy"] },
  { code: "ES", i18nKey: "spain", aliases: ["ES", "SPA", "Spain"] },
  { code: "UK", i18nKey: "uk", aliases: ["UK", "GB", "United Kingdom"] },
  { code: "BR", i18nKey: "brazil", aliases: ["BR", "BRA", "Brazil"] },
  { code: "AU", i18nKey: "australia", aliases: ["AU", "AUS", "Australia"] },
  { code: "KR", i18nKey: "korea", aliases: ["KR", "KOR", "Korea"] },
  { code: "CN", i18nKey: "china", aliases: ["CN", "CHN", "China"] },
  { code: "TW", i18nKey: "taiwan", aliases: ["TW", "TWN", "Taiwan"] },
] as const;

export const REGION_BY_CODE: Readonly<
  Record<string, RegionCatalogueEntry>
> = Object.fromEntries(REGION_CATALOGUE.map((r) => [r.code, r]));

/** Look up a region's i18n key from a stored code; falls back to
 * the code itself for legacy data the catalogue doesn't list (so
 * the UI never crashes on an unrecognised code). */
export function regionLabelKey(code: string): string {
  return REGION_BY_CODE[code]?.i18nKey ?? code;
}
