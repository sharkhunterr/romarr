/**
 * Language toggle button group (T117 / T119 partial).
 *
 * EN | FR pill buttons in the header. Clicking a code calls
 * `i18next.changeLanguage(...)`; the localStorage detector
 * persists the pick under the documented `romarr.lang` key.
 *
 * The canonical language switcher lands in /settings/ui (T119)
 * with a labeled control + the longer language list. The
 * header pill is the always-on switch for the operator who
 * picked the wrong default.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { setLanguage, SUPPORTED_LANGUAGES, type Language } from "@/lib/i18n";

const LABEL: Record<Language, string> = {
  en: "EN",
  fr: "FR",
};

function toggleClass(active: boolean): string {
  return [
    "rounded px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wider",
    "transition-colors",
    active
      ? "bg-zinc-800 text-zinc-100"
      : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
  ].join(" ");
}

export function LanguageToggle(): ReactElement {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage ?? "en") as Language;

  return (
    <div
      role="group"
      aria-label={t("language.label")}
      className="flex items-center gap-0.5 rounded-md bg-zinc-900/60 p-0.5"
    >
      {SUPPORTED_LANGUAGES.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => {
            void setLanguage(code);
          }}
          className={toggleClass(current === code)}
          aria-pressed={current === code}
        >
          {LABEL[code]}
        </button>
      ))}
    </div>
  );
}
