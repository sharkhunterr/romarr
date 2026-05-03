/**
 * Floating Action Button (T072 / spec D).
 *
 * Mobile-first primary-action button positioned at the bottom-
 * right of the viewport, clearing the BottomNav (4rem tall +
 * env safe-area). On desktop the FAB stays in the same spot
 * (bottom-right) but the BottomNav is hidden so the offset
 * just preserves the corner padding.
 *
 * Two flavours:
 *   * ``LinkFAB`` — wraps a ``react-router`` ``<Link>`` (used
 *     by the Library "Add" FAB pointing at ``/add``).
 *   * ``ButtonFAB`` — wraps a plain ``<button>`` (used by the
 *     Wanted "Trigger Search" FAB which fires a system command).
 *
 * Both share the visual treatment so the operator's mental
 * model is consistent across pages.
 */

import { type ReactElement, type ReactNode } from "react";
import { Link } from "react-router-dom";

const _SHARED = [
  // Mobile: above the BottomNav (h-16 = 4rem) plus a 1rem gap.
  // Desktop: BottomNav is hidden; the bottom offset just keeps
  // the FAB out of the corner.
  "fixed right-4 bottom-20 md:bottom-6 z-40",
  "inline-flex items-center gap-2 rounded-full",
  "px-5 py-3 text-sm font-medium",
  "bg-brand text-zinc-900 shadow-lg shadow-brand/30",
  "hover:bg-brand-300 hover:shadow-brand/50",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
  "transition-all",
].join(" ");

const _DISABLED = "disabled:cursor-not-allowed disabled:opacity-60";

export interface FABBaseProps {
  ariaLabel: string;
  /** Icon-only inner content; text label appears in the
   * adjacent ``<span>`` so screen readers + sighted users
   * both get the action name. */
  icon: ReactNode;
  label: string;
}

export interface LinkFABProps extends FABBaseProps {
  to: string;
}

export function LinkFAB(props: LinkFABProps): ReactElement {
  return (
    <Link
      to={props.to}
      aria-label={props.ariaLabel}
      className={_SHARED}
    >
      <span aria-hidden="true">{props.icon}</span>
      <span>{props.label}</span>
    </Link>
  );
}

export interface ButtonFABProps extends FABBaseProps {
  onClick: () => void;
  disabled?: boolean;
}

export function ButtonFAB(props: ButtonFABProps): ReactElement {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      aria-label={props.ariaLabel}
      className={[_SHARED, _DISABLED].join(" ")}
    >
      <span aria-hidden="true">{props.icon}</span>
      <span>{props.label}</span>
    </button>
  );
}
