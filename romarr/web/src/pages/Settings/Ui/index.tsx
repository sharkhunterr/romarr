/**
 * Settings > UI sub-page (T119).
 *
 * Canonical operator surface for the two persistent display
 * preferences: theme (dark / light / auto) and language
 * (EN / FR). Header carries a lightweight always-on toggle for
 * each; this page is the documented home with labels +
 * inline help.
 *
 * Persistence:
 *   * theme  → zustand-persist under `romarr.theme`
 *     (slice 44, ThemeProvider applies the class on <html>).
 *   * language → i18next-browser-languagedetector under
 *     `romarr.lang` (slice 55).
 *
 * Date / time / number-format prefs are deferred to the
 * spec 014 T118 dates.ts slice.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  setLanguage,
  SUPPORTED_LANGUAGES,
  type Language,
} from "@/lib/i18n";
import { useThemeStore, type Theme } from "@/lib/store/theme";

const THEMES: readonly Theme[] = ["dark", "light", "auto"];

const LANGUAGE_LABEL_KEY: Record<Language, string> = {
  en: "language.english",
  fr: "language.french",
};

interface PillProps {
  active: boolean;
  onClick: () => void;
  children: ReactElement | string;
  ariaLabel?: string;
}

function Pill(props: PillProps): ReactElement {
  return (
    <button
      type="button"
      onClick={props.onClick}
      aria-pressed={props.active}
      aria-label={props.ariaLabel}
      className={[
        "min-h-[44px] flex-1 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors",
        props.active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
      ].join(" ")}
    >
      {props.children}
    </button>
  );
}

export function SettingsUiPage(): ReactElement {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const currentLang = (i18n.resolvedLanguage ?? "en") as Language;

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("settings:ui.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("settings:ui.subtitle")}
        </p>
      </header>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h3 className="text-sm font-medium text-zinc-100">
          {t("settings:ui.theme.label")}
        </h3>
        <p className="mt-1 text-xs text-zinc-500">
          {t("settings:ui.theme.help")}
        </p>
        <div
          role="group"
          aria-label={t("settings:ui.theme.label")}
          className="mt-3 flex gap-1 rounded-md bg-zinc-950 p-1"
        >
          {THEMES.map((mode) => (
            <Pill
              key={mode}
              active={theme === mode}
              onClick={() => setTheme(mode)}
            >
              {t(`common:theme.modes.${mode}`)}
            </Pill>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h3 className="text-sm font-medium text-zinc-100">
          {t("settings:ui.language.label")}
        </h3>
        <p className="mt-1 text-xs text-zinc-500">
          {t("settings:ui.language.help")}
        </p>
        <div
          role="group"
          aria-label={t("settings:ui.language.label")}
          className="mt-3 flex gap-1 rounded-md bg-zinc-950 p-1"
        >
          {SUPPORTED_LANGUAGES.map((code) => (
            <Pill
              key={code}
              active={currentLang === code}
              onClick={() => {
                void setLanguage(code);
              }}
            >
              {t(`common:${LANGUAGE_LABEL_KEY[code]}`)}
            </Pill>
          ))}
        </div>
      </section>
    </div>
  );
}
