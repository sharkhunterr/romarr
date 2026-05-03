/**
 * i18next configuration (T117, FR-011, FR-012, FR-013).
 *
 * Constitutional requirement: French and English from day one.
 * The bundle catalogues live under public/locales/{lng}/{ns}.json
 * and are fetched lazily via i18next-http-backend.
 *
 * Language resolution order:
 *   1. The `romarr.lang` localStorage key (operator override —
 *      written by the language switcher).
 *   2. The browser's `navigator.language` (or first preference
 *      via the navigator detector).
 *   3. English fallback.
 *
 * The detector is configured to ONLY look at localStorage +
 * navigator. We don't fall through to cookies / query strings /
 * the html `lang` attribute — those would let any of those
 * sources silently override the operator's explicit pick.
 */

import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import HttpBackend from "i18next-http-backend";
import { initReactI18next } from "react-i18next";

export const SUPPORTED_LANGUAGES = ["en", "fr"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const FALLBACK_LANGUAGE: Language = "en";
export const LANG_STORAGE_KEY = "romarr.lang";

export const NAMESPACES = [
  "common",
  "errors",
  "settings",
  "auth",
  "setup",
  "dashboard",
  "wanted",
  "activity",
  "system",
  "calendar",
  "search",
  "library",
] as const;
export type Namespace = (typeof NAMESPACES)[number];

void i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: FALLBACK_LANGUAGE,
    supportedLngs: [...SUPPORTED_LANGUAGES],
    nonExplicitSupportedLngs: true,
    load: "languageOnly",
    ns: [...NAMESPACES],
    defaultNS: "common",
    backend: {
      loadPath: "/locales/{{lng}}/{{ns}}.json",
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: LANG_STORAGE_KEY,
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: true,
    },
  });

export function setLanguage(lng: Language): Promise<unknown> {
  return i18n.changeLanguage(lng);
}

export default i18n;
