/**
 * Language pills — flag emoji + ISO 639-1 code per language.
 *
 * Falls through to a globe icon for unknown codes. The full
 * BCP-47 locale resolution lands with the i18n phase; today
 * we map the most common single-language ROM codes.
 */

import { type ReactElement } from "react";

export interface LanguagePillsProps {
  codes: readonly string[];
  /** Maximum pills to render before collapsing into "+N more". */
  max?: number;
  className?: string;
  /** When true, skip flag emoji and only render the ISO code. */
  noEmoji?: boolean;
}

const LANGUAGE_FLAGS: Record<string, string> = {
  en: "🇬🇧",
  fr: "🇫🇷",
  de: "🇩🇪",
  es: "🇪🇸",
  it: "🇮🇹",
  ja: "🇯🇵",
  ko: "🇰🇷",
  zh: "🇨🇳",
  pt: "🇵🇹",
  ru: "🇷🇺",
  nl: "🇳🇱",
  sv: "🇸🇪",
  no: "🇳🇴",
  da: "🇩🇰",
  fi: "🇫🇮",
};

function pillClass(): string {
  return [
    "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5",
    "text-[0.7rem] font-mono font-medium",
    "bg-zinc-800 text-zinc-200 ring-1 ring-inset ring-zinc-700",
  ].join(" ");
}

export function LanguagePills(
  props: LanguagePillsProps,
): ReactElement {
  const max = props.max ?? 5;
  const visible = props.codes.slice(0, max);
  const overflow = Math.max(0, props.codes.length - max);
  const className = [
    "inline-flex flex-wrap items-center gap-1",
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <span className={className}>
      {visible.map((code) => {
        const lower = code.toLowerCase();
        const flag = LANGUAGE_FLAGS[lower] ?? "🌐";
        return (
          <span
            key={lower}
            className={pillClass()}
            aria-label={`Language ${lower}`}
          >
            {!props.noEmoji && <span aria-hidden="true">{flag}</span>}
            <span>{lower}</span>
          </span>
        );
      })}
      {overflow > 0 && (
        <span
          className={pillClass()}
          aria-label={`${overflow} more languages`}
          title={props.codes.slice(max).join(", ")}
        >
          +{overflow}
        </span>
      )}
    </span>
  );
}
