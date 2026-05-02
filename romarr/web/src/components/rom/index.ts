/**
 * Barrel export for the 10 ROM-specific components.
 *
 * Pages import from ``@/components/rom`` rather than the
 * individual files so a future refactor (e.g. extracting the
 * components into their own package) is a single-line change.
 */

export { ConventionBadge } from "./ConventionBadge";
export type { ConventionBadgeProps, NamingConvention } from "./ConventionBadge";

export { CoverImage } from "./CoverImage";
export type { CoverImageProps } from "./CoverImage";

export { DatVerifiedBadge } from "./DatVerifiedBadge";
export type { DatVerifiedBadgeProps } from "./DatVerifiedBadge";

export { DumpStatusIcon } from "./DumpStatusIcon";
export type { DumpStatus, DumpStatusIconProps } from "./DumpStatusIcon";

export { HashBadge } from "./HashBadge";
export type { HashBadgeProps, HashType } from "./HashBadge";

export { LanguagePills } from "./LanguagePills";
export type { LanguagePillsProps } from "./LanguagePills";

export { MultiDiscAccordion } from "./MultiDiscAccordion";
export type { MultiDiscAccordionProps } from "./MultiDiscAccordion";

export { PlatformIcon } from "./PlatformIcon";
export type { PlatformIconProps } from "./PlatformIcon";

export { RegionBadge } from "./RegionBadge";
export type { RegionBadgeProps } from "./RegionBadge";

export { ScoreBadge } from "./ScoreBadge";
export type { ScoreBadgeProps, ScoreBreakdownEntry } from "./ScoreBadge";
