/**
 * Collapsible multi-disc release group.
 *
 * Header reads "Disc 1/N — <title>"; expanding renders the
 * supplied children (typically the disc-2..N detail rows). Uses
 * the native `<details>` element — accessible by default,
 * keyboard-navigable, no extra runtime weight.
 */

import { type ReactElement, type ReactNode } from "react";

export interface MultiDiscAccordionProps {
  parentTitle: string;
  totalDiscs: number;
  /** When true, the accordion starts open. */
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}

export function MultiDiscAccordion(
  props: MultiDiscAccordionProps,
): ReactElement {
  const className = [
    "rounded-md border border-zinc-700 bg-zinc-900/60",
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <details className={className} open={props.defaultOpen}>
      <summary
        className={[
          "flex cursor-pointer items-center justify-between",
          "px-3 py-2 text-sm font-medium text-zinc-200",
          "hover:bg-zinc-800/60 rounded-t-md",
        ].join(" ")}
      >
        <span className="truncate">{props.parentTitle}</span>
        <span className="ml-3 shrink-0 text-xs font-mono text-zinc-400">
          Disc 1/{props.totalDiscs}
        </span>
      </summary>
      <div className="border-t border-zinc-700 px-3 py-2">
        {props.children}
      </div>
    </details>
  );
}
