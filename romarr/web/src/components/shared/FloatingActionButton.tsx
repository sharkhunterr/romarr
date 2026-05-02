/**
 * Mobile primary-action button (T025).
 *
 * Floats above the bottom navigation; pages declare the
 * page-specific primary action (Add on Library, Trigger
 * Search on Wanted, …). Hit target ≥ 44 × 44 px (FR-002).
 */

import { type ButtonHTMLAttributes, type ReactElement, type ReactNode } from "react";

export interface FloatingActionButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  /** Icon or short label rendered inside the FAB. */
  children: ReactNode;
  /** Accessible label — required because the icon alone
   * isn't always screen-reader-friendly. */
  label: string;
}

export function FloatingActionButton(
  props: FloatingActionButtonProps,
): ReactElement {
  const { children, label, className: extraClass, ...rest } = props;
  const className = [
    "fixed right-4 z-30 md:hidden",
    // Sit above the BottomNav (h-14) plus safe-area inset.
    "bottom-[calc(theme(spacing.20)+env(safe-area-inset-bottom))]",
    "h-14 w-14 rounded-full",
    "bg-brand text-zinc-900 shadow-lg shadow-black/40",
    "flex items-center justify-center text-2xl font-bold",
    "hover:bg-brand-300 active:scale-95 transition-all",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
    extraClass ?? "",
  ]
    .join(" ")
    .trim();

  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      title={label}
      {...rest}
    >
      {children}
    </button>
  );
}
