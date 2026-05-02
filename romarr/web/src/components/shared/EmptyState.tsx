/**
 * Empty-state placeholder (T022).
 *
 * Used by every list page when the underlying query returns
 * zero rows. Optional icon (defaults to a brand-tinted dot),
 * title + description, and an optional CTA.
 */

import { type ReactElement, type ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  cta?: ReactNode;
  className?: string;
}

function DefaultIcon(): ReactElement {
  return (
    <span
      aria-hidden="true"
      className={[
        "flex h-12 w-12 items-center justify-center rounded-full",
        "bg-brand/15 text-brand",
        "text-2xl",
      ].join(" ")}
    >
      ◌
    </span>
  );
}

export function EmptyState(props: EmptyStateProps): ReactElement {
  const className = [
    "flex flex-col items-center justify-center gap-3",
    "rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40",
    "px-6 py-12 text-center",
    props.className ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <div className={className}>
      {props.icon ?? <DefaultIcon />}
      <h2 className="text-base font-medium text-zinc-100">
        {props.title}
      </h2>
      {props.description && (
        <p className="max-w-sm text-sm text-zinc-400">
          {props.description}
        </p>
      )}
      {props.cta && <div className="mt-2">{props.cta}</div>}
    </div>
  );
}
