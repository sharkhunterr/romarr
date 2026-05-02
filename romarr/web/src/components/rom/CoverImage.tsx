/**
 * Lazy-loaded cover with skeleton + gradient fallback.
 *
 * When ``src`` is missing or fails to load, falls back to a
 * Game-Boy-LCD-green diagonal gradient placeholder bearing the
 * game title's first two letters. Browser-native lazy loading
 * via ``loading="lazy"``; no IntersectionObserver code to ship.
 *
 * The skeleton-while-loading state lands with the shadcn/ui
 * Skeleton primitive in a follow-up; today the unloaded state
 * shows the gradient (visually identical to the missing-cover
 * fallback, no flash of empty space).
 */

import { useState, type ReactElement } from "react";

export interface CoverImageProps {
  src?: string | null;
  alt: string;
  /** Width / height as Tailwind classes; defaults to ``h-32 w-24``. */
  sizeClassName?: string;
  className?: string;
}

function initialsOf(alt: string): string {
  return alt
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function CoverImage(props: CoverImageProps): ReactElement {
  const [failed, setFailed] = useState(false);
  const sizeClassName = props.sizeClassName ?? "h-32 w-24";

  const showFallback = !props.src || failed;

  if (showFallback) {
    return (
      <div
        className={[
          sizeClassName,
          "flex items-center justify-center rounded",
          "bg-gradient-to-br from-brand-700 via-brand-500 to-brand-300",
          "font-mono text-2xl font-bold text-zinc-900",
          "shadow-inner",
          props.className ?? "",
        ]
          .join(" ")
          .trim()}
        role="img"
        aria-label={props.alt}
      >
        {initialsOf(props.alt)}
      </div>
    );
  }

  return (
    <img
      src={props.src ?? ""}
      alt={props.alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={[
        sizeClassName,
        "rounded object-cover bg-zinc-800",
        props.className ?? "",
      ]
        .join(" ")
        .trim()}
    />
  );
}
