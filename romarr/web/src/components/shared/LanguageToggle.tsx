/**
 * Language picker (T117 / T119 partial).
 *
 * Compact dropdown in the header: native ``<select>`` styled to
 * blend with the rest of the chrome, each option prefixed by the
 * country flag emoji + ISO code. Operator picks a language;
 * the localStorage detector persists the choice under the
 * documented ``romarr.lang`` key.
 *
 * The full UI-settings picker (T119) ships in /settings/ui with
 * a fuller layout; this is the always-on header switch.
 */

import { Languages } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { setLanguage, SUPPORTED_LANGUAGES, type Language } from "@/lib/i18n";

const LANGUAGE_FLAG: Record<Language, string> = {
  en: "🇬🇧",
  fr: "🇫🇷",
};

const LANGUAGE_LABEL: Record<Language, string> = {
  en: "English",
  fr: "Français",
};

export function LanguageToggle(): ReactElement {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage ?? "en") as Language;

  return (
    <label
      className={[
        "relative inline-flex h-9 items-center gap-1.5 rounded-md",
        "border border-zinc-800 bg-zinc-900/60 pl-2 pr-7",
        "text-sm text-zinc-200",
        "hover:bg-zinc-900 focus-within:ring-2 focus-within:ring-brand",
      ].join(" ")}
      aria-label={t("language.label")}
    >
      <Languages
        size={14}
        strokeWidth={2}
        aria-hidden="true"
        className="text-zinc-400"
      />
      <span aria-hidden="true" className="text-base leading-none">
        {LANGUAGE_FLAG[current]}
      </span>
      <select
        value={current}
        onChange={(e) => {
          void setLanguage(e.target.value as Language);
        }}
        className={[
          "absolute inset-0 cursor-pointer appearance-none bg-transparent",
          "text-transparent",
          "focus:outline-none",
        ].join(" ")}
        aria-label={t("language.label")}
      >
        {SUPPORTED_LANGUAGES.map((code) => (
          <option key={code} value={code} className="bg-zinc-900 text-zinc-100">
            {LANGUAGE_FLAG[code]} {LANGUAGE_LABEL[code]}
          </option>
        ))}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-2 text-zinc-500"
      >
        ▾
      </span>
    </label>
  );
}
