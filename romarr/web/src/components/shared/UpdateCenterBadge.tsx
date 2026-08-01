/**
 * Update Center badge in the header — replaces the legacy
 * VersionBadge with an aggregated view over every registered
 * community source AND the Romarr release check.
 *
 * Three visual states:
 *   * green (⬤)   — everything up to date; renders the current
 *                    version compact, tooltip explains "all up to
 *                    date across N sources"
 *   * amber (⬤ N) — N updates available; opens a popover listing
 *                    each pending update with a one-click Apply /
 *                    Voir la release action
 *   * red   (⚠)   — at least one source's last check failed; the
 *                    tooltip lists which
 */

import {
  useEffect,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  useApplyCommunitySource,
  useCommunityUpdatesFeed,
  type CommunitySource,
} from "@/lib/api/queries/community";
import { useToastStore } from "@/lib/store/toast";

type State = "loading" | "ok" | "updates" | "error";

function resolveState(
  feed: ReturnType<typeof useCommunityUpdatesFeed>,
): State {
  if (feed.isPending) return "loading";
  if (feed.isError || !feed.data) return "error";
  const anyErr =
    (feed.data.romarr.error && feed.data.romarr.error.length > 0) ||
    feed.data.sources.some((s) => s.last_status === "error");
  if (feed.data.total_updates > 0) return "updates";
  if (anyErr) return "error";
  return "ok";
}

export function UpdateCenterBadge(): ReactElement | null {
  const { t } = useTranslation("common");
  const feed = useCommunityUpdatesFeed();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent): void {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const state = resolveState(feed);

  if (state === "loading") {
    return (
      <span className="rounded-md bg-zinc-800 px-2 py-0.5 font-mono text-[0.6rem] text-zinc-500">
        …
      </span>
    );
  }

  const data = feed.data;

  if (state === "ok" && data) {
    return (
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 font-mono text-[0.6rem] text-zinc-400 hover:bg-zinc-700"
        title={t("updateCenter.upToDate", {
          version: data.romarr.current,
          sources: data.sources.length,
        })}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
        <span>v{data.romarr.current}</span>
      </button>
    );
  }

  const chipClass =
    state === "updates"
      ? "inline-flex items-center gap-1 rounded-md border border-amber-700/50 bg-amber-950/40 px-2 py-0.5 font-mono text-[0.6rem] text-amber-300 hover:bg-amber-950/60"
      : "inline-flex items-center gap-1 rounded-md border border-red-800/60 bg-red-950/40 px-2 py-0.5 font-mono text-[0.6rem] text-red-300 hover:bg-red-950/60";

  const dotClass =
    state === "updates" ? "bg-amber-400" : "bg-red-400";

  return (
    <div className="relative" ref={popoverRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={chipClass}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} aria-hidden="true" />
        {state === "updates" && data ? (
          <>
            <span>v{data.romarr.current}</span>
            <span aria-hidden="true">·</span>
            <span className="font-semibold">
              {t("updateCenter.count", { count: data.total_updates })}
            </span>
          </>
        ) : (
          <span>{t("updateCenter.error")}</span>
        )}
      </button>

      {open && data && (
        <UpdatePopover
          feed={data}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Popover
// ---------------------------------------------------------------------------

interface UpdatePopoverProps {
  feed: NonNullable<ReturnType<typeof useCommunityUpdatesFeed>["data"]>;
  onClose: () => void;
}

function UpdatePopover(props: UpdatePopoverProps): ReactElement {
  const { t } = useTranslation("common");
  const { feed, onClose } = props;
  const apply = useApplyCommunitySource();
  const pushToast = useToastStore((s) => s.push);

  function handleApply(src: CommunitySource): void {
    apply.mutate(src.id, {
      onSuccess: (res) => {
        if (res.error) {
          pushToast({
            kind: "error",
            title: t("updateCenter.applyErrorTitle"),
            description: res.error,
          });
        } else {
          pushToast({
            kind: "success",
            title: t("updateCenter.applySuccessTitle"),
            description: t("updateCenter.applySuccessBody", {
              name: src.name,
              count: res.applied_count,
            }),
          });
        }
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("updateCenter.applyErrorTitle"),
          description: err.message,
        });
      },
    });
  }

  const sourcesWithUpdates = feed.sources.filter((s) => s.update_available);

  return (
    <div
      role="dialog"
      aria-label={t("updateCenter.popoverTitle")}
      className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-zinc-800 bg-zinc-950 shadow-2xl"
    >
      <header className="border-b border-zinc-800 px-3 py-2">
        <h2 className="text-xs font-semibold text-zinc-100">
          {t("updateCenter.popoverTitle")}
        </h2>
      </header>

      <div className="max-h-96 overflow-y-auto">
        {/* Romarr release */}
        <section className="border-b border-zinc-900 px-3 py-2">
          <h3 className="mb-1 text-[0.6rem] uppercase tracking-widest text-zinc-500">
            Romarr
          </h3>
          {feed.romarr.update_available ? (
            <a
              href={feed.romarr.release_url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between rounded px-1 py-1 text-xs text-amber-300 hover:bg-amber-950/30"
            >
              <span>
                v{feed.romarr.current} → v{feed.romarr.latest}
              </span>
              <span className="text-[0.6rem] text-amber-400 underline">
                {t("updateCenter.viewRelease")}
              </span>
            </a>
          ) : (
            <p className="px-1 py-1 text-xs text-zinc-400">
              v{feed.romarr.current} ·{" "}
              <span className="text-emerald-400">
                {t("updateCenter.upToDateShort")}
              </span>
            </p>
          )}
          {feed.romarr.error && (
            <p className="px-1 py-1 text-[0.65rem] text-red-400">
              {feed.romarr.error}
            </p>
          )}
        </section>

        {/* Community sources */}
        <section className="px-3 py-2">
          <h3 className="mb-1 text-[0.6rem] uppercase tracking-widest text-zinc-500">
            {t("updateCenter.communitySection")}
          </h3>
          {sourcesWithUpdates.length === 0 ? (
            <p className="px-1 py-1 text-xs text-zinc-500">
              {t("updateCenter.noCommunityUpdates")}
            </p>
          ) : (
            <ul className="space-y-1">
              {sourcesWithUpdates.map((src) => (
                <li
                  key={src.id}
                  className="flex items-start justify-between gap-2 rounded px-1 py-1 text-xs hover:bg-zinc-900"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-zinc-100">
                      {src.name}
                    </p>
                    <p className="truncate text-[0.65rem] text-zinc-500">
                      {src.installed_version ?? "—"} → {src.last_seen_version}
                    </p>
                    <p className="truncate text-[0.6rem] uppercase text-zinc-600">
                      {src.resource_type}
                      {src.trust_status === "pending" && (
                        <span className="ml-1 text-amber-500">
                          · {t("updateCenter.trustPending")}
                        </span>
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleApply(src)}
                    disabled={
                      apply.isPending || src.trust_status === "pending"
                    }
                    className="shrink-0 rounded border border-brand/60 bg-brand/10 px-2 py-0.5 text-[0.65rem] font-medium text-brand hover:bg-brand/20 disabled:cursor-not-allowed disabled:opacity-50"
                    title={
                      src.trust_status === "pending"
                        ? t("updateCenter.trustPendingHint")
                        : t("updateCenter.applyHint")
                    }
                  >
                    {t("updateCenter.apply")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <footer className="flex items-center justify-between gap-2 border-t border-zinc-800 px-3 py-2">
        <Link
          to="/settings/updates"
          onClick={onClose}
          className="text-[0.65rem] text-brand underline hover:text-brand-300"
        >
          {t("updateCenter.manageSources")}
        </Link>
        <button
          type="button"
          onClick={onClose}
          className="text-[0.65rem] text-zinc-500 hover:text-zinc-300"
        >
          {t("updateCenter.close")}
        </button>
      </footer>
    </div>
  );
}
