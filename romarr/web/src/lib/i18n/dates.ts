/**
 * Locale-aware date formatting helpers (T118, slice 170).
 *
 * Wraps :pkg:`date-fns` so consumers don't have to import the
 * locale dynamically themselves. The locale picked tracks the
 * active i18next language via the spec-014 ``romarr.lang``
 * localStorage key + the ``SUPPORTED_LANGUAGES`` whitelist
 * exported from the i18next bootstrap.
 *
 * The exported helpers stay narrow — every other place that
 * formats a date in the app should funnel through this module
 * so a future locale toggle (Cmd+L?) only has to invalidate
 * one cache.
 */

import {
  format,
  formatDistanceToNow,
  formatRelative,
  parseISO,
} from "date-fns";
import { enUS, fr } from "date-fns/locale";
import type { Locale } from "date-fns/locale";

import {
  FALLBACK_LANGUAGE,
  type Language,
} from "@/lib/i18n";

const _LOCALES: Record<Language, Locale> = {
  en: enUS,
  fr,
};

/** Turn a Romarr ``Language`` code into the matching date-fns
 * ``Locale`` object. Falls back to the spec-default English
 * locale on unknown input — the i18next setup already
 * normalises before getting here, but defence-in-depth never
 * hurts when the value passes through localStorage. */
export function localeFor(lang: string | undefined): Locale {
  if (lang && lang in _LOCALES) {
    return _LOCALES[lang as Language];
  }
  return _LOCALES[FALLBACK_LANGUAGE];
}

/** Coerce ``input`` to a ``Date`` regardless of whether it
 * arrived as a Date, an ISO-8601 string, a millis epoch, or a
 * null/undefined. Returns ``null`` on the latter two and on
 * anything that fails to parse — callers render a placeholder
 * (typically ``"—"``) on null. */
export function coerceDate(
  input: Date | string | number | null | undefined,
): Date | null {
  if (input === null || input === undefined) return null;
  if (input instanceof Date) {
    return Number.isNaN(input.getTime()) ? null : input;
  }
  if (typeof input === "number") {
    const d = new Date(input);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  // string — accept ISO-8601 (the spec-013 envelope shape).
  // ``parseISO`` handles ``2026-05-03T12:34:56Z`` and
  // ``2026-05-03T12:34:56+02:00`` cleanly; bare YYYY-MM-DD too.
  try {
    const d = parseISO(input);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

/** Locale-aware short date — e.g. ``"03/05/2026"`` (en-US:
 * ``05/03/2026``). Used for "Recently added" and "Release
 * date" columns. Returns ``""`` for null input so callers can
 * use the value directly inside a ``{value || "—"}`` ternary. */
export function formatShortDate(
  input: Date | string | number | null | undefined,
  lang: string | undefined,
): string {
  const d = coerceDate(input);
  if (d === null) return "";
  return format(d, "P", { locale: localeFor(lang) });
}

/** Locale-aware full date+time — e.g.
 * ``"3 mai 2026 14:32"``. Used for History rows / Activity. */
export function formatDateTime(
  input: Date | string | number | null | undefined,
  lang: string | undefined,
): string {
  const d = coerceDate(input);
  if (d === null) return "";
  return format(d, "Pp", { locale: localeFor(lang) });
}

/** Locale-aware "X minutes ago" / "in 2 hours" — used by
 * Activity feed and Recent Additions where short relative
 * timestamps read better than absolute ones. ``addSuffix`` is
 * always ``true`` so the operator gets the prefix word. */
export function formatRelativeTime(
  input: Date | string | number | null | undefined,
  lang: string | undefined,
  options?: { now?: Date },
): string {
  const d = coerceDate(input);
  if (d === null) return "";
  return formatDistanceToNow(d, {
    addSuffix: true,
    locale: localeFor(lang),
    ...(options?.now !== undefined ? { now: options.now } : {}),
  });
}

/** Locale-aware "yesterday at 14:32" / "last Tuesday at …". */
export function formatRelativeDate(
  input: Date | string | number | null | undefined,
  lang: string | undefined,
  baseDate: Date = new Date(),
): string {
  const d = coerceDate(input);
  if (d === null) return "";
  return formatRelative(d, baseDate, { locale: localeFor(lang) });
}
