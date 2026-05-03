/**
 * Lazy-loaded cover with skeleton + gradient fallback (slice 159).
 *
 * When ``gameId`` is supplied AND the Game has a cover stored,
 * the component sources the bytes from
 * ``GET /api/v3/cover/{gameId}``. Without ``gameId``, the
 * legacy ``src`` prop is honoured directly so callers that
 * already pass a URL (or want to render a non-game cover) keep
 * working unchanged.
 *
 * When the cover is missing (no ``gameId`` AND no ``src``, or
 * the Game has no stored cover, or the load fails), falls back
 * to a Game-Boy-LCD-green diagonal gradient bearing the
 * title's first two letters. Browser-native lazy loading via
 * ``loading="lazy"``.
 */

import { useState, type ReactElement } from "react";

export interface CoverImageProps {
  /** Legacy: a fully-formed URL (or remote path). Use ``gameId``
   * for Romarr-stored covers — it auto-resolves to the
   * cover-serving endpoint. */
  src?: string | null;
  /**
   * Slice 159: when supplied alongside a non-empty ``src`` (any
   * truthy value, since the Game.cover_path field is opaque to
   * the frontend now) the component fetches the bytes from
   * ``/api/v3/cover/{gameId}``. ``cacheKey`` (typically the
   * Game's ``updated_at``) is appended as ``?v=`` for the
   * spec-prescribed cache-busting.
   */
  gameId?: number;
  /** Optional cache-bust token for the gameId path. */
  cacheKey?: string | null;
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

function buildSrc(props: CoverImageProps): string | null {
  if (props.gameId !== undefined && props.src) {
    // Romarr-stored cover. The src value is the opaque
    // cover_path string from the Game row; presence is what
    // matters here, not its content.
    const v =
      props.cacheKey !== null && props.cacheKey !== undefined && props.cacheKey
        ? `?v=${encodeURIComponent(props.cacheKey)}`
        : "";
    return `/api/v3/cover/${props.gameId}${v}`;
  }
  return props.src ?? null;
}

export function CoverImage(props: CoverImageProps): ReactElement {
  const [failed, setFailed] = useState(false);
  const sizeClassName = props.sizeClassName ?? "h-32 w-24";

  const resolvedSrc = buildSrc(props);
  const showFallback = !resolvedSrc || failed;

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
      src={resolvedSrc ?? ""}
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
