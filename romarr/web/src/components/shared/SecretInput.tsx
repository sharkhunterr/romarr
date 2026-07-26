/**
 * SecretInput — a text input for secret values with an integrated
 * eye toggle to reveal / hide the content in place.
 *
 * Same props surface as a native ``<input>`` with strict typing on
 * value / onChange. The reveal state is component-local — safe to
 * drop into any form without extra plumbing. Rendered secrets stay
 * masked by default; the operator opts in each time.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

interface SecretInputProps {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  /** Sets the input's ``autocomplete`` attribute — defaults to
   * ``new-password`` so browsers don't autofill and don't offer
   * to save the value across sessions. */
  autoComplete?: string;
  className?: string;
  /** Optional aria-label. Defaults to the i18n string
   * ``settings:secretInput.aria``. */
  ariaLabel?: string;
}

export function SecretInput(props: SecretInputProps): ReactElement {
  const { t } = useTranslation("settings");
  const [revealed, setRevealed] = useState(false);

  const baseClass =
    props.className ??
    [
      "w-full rounded-md bg-zinc-900 pl-3 pr-10 py-2 text-sm text-zinc-100",
      "ring-1 ring-inset ring-zinc-700",
      "focus-visible:outline-none focus-visible:ring-2",
      "focus-visible:ring-brand",
      "disabled:cursor-not-allowed disabled:opacity-60",
    ].join(" ");

  return (
    <div className="relative">
      <input
        id={props.id}
        type={revealed ? "text" : "password"}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        disabled={props.disabled}
        autoComplete={props.autoComplete ?? "new-password"}
        spellCheck={false}
        aria-label={props.ariaLabel}
        // Use a monospace font ONLY when the value is revealed —
        // makes secrets easier to eyeball, keeps the masked view
        // consistent with the other text fields.
        className={
          revealed ? `${baseClass} font-mono tracking-tight` : baseClass
        }
      />
      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        disabled={props.disabled}
        aria-label={
          revealed
            ? t("secretInput.hide", "Hide value")
            : t("secretInput.show", "Show value")
        }
        aria-pressed={revealed}
        title={
          revealed
            ? t("secretInput.hide", "Hide value")
            : t("secretInput.show", "Show value")
        }
        className={[
          "absolute right-1 top-1/2 -translate-y-1/2",
          "rounded p-1.5 text-zinc-500 hover:text-zinc-100",
          "hover:bg-zinc-800 focus-visible:outline-none",
          "focus-visible:ring-2 focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-50",
        ].join(" ")}
      >
        {revealed ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  );
}

function EyeIcon(): ReactElement {
  // Inline SVG — no icon-lib dep for a 16px pictogram we control.
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon(): ReactElement {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-10-7-10-7a19.77 19.77 0 0 1 4.06-5.94" />
      <path d="M9.9 4.24A10.14 10.14 0 0 1 12 4c7 0 10 7 10 7a19.9 19.9 0 0 1-3.16 4.19" />
      <path d="M14.12 14.12A3 3 0 0 1 9.88 9.88" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}
