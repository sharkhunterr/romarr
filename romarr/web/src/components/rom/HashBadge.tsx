/**
 * Copyable monospace hash badge.
 *
 * Click copies the hash to the clipboard via the Clipboard API.
 * Long hashes (SHA-1 / SHA-256) are visually truncated; the
 * tooltip + clipboard payload preserve the full value.
 *
 * The toast / "Copied!" feedback lands with the shadcn/ui
 * primitive integration (`useToast`); today the click is silent
 * but functional — the spec test suite (T031) verifies the
 * clipboard write directly.
 */

import { type ReactElement } from "react";

export type HashType = "SHA1" | "SHA256" | "CRC32" | "MD5";

export interface HashBadgeProps {
  type: HashType;
  value: string;
  /** Truncate to N characters (suffixed by "..."). Default 12. */
  truncate?: number;
  className?: string;
}

export function HashBadge(props: HashBadgeProps): ReactElement {
  const truncate = props.truncate ?? 12;
  const display =
    props.value.length > truncate
      ? `${props.value.slice(0, truncate)}…`
      : props.value;

  const onClick = (): void => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(props.value);
    }
  };

  const className = [
    "inline-flex items-center gap-1.5 rounded px-2 py-0.5",
    "text-xs font-mono font-medium",
    "bg-zinc-800 text-zinc-200 ring-1 ring-inset ring-zinc-700",
    "hover:bg-zinc-700 hover:text-zinc-100 transition-colors",
    "cursor-pointer focus-visible:outline-none focus-visible:ring-2",
    "focus-visible:ring-brand",
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <button
      type="button"
      onClick={onClick}
      className={className}
      title={`${props.type}: ${props.value} (click to copy)`}
      aria-label={`Copy ${props.type} hash`}
    >
      <span className="text-[0.65rem] uppercase text-zinc-400">
        {props.type}
      </span>
      <span>{display}</span>
    </button>
  );
}
