/**
 * Health panel — surfaces the spec 011 HealthEngine snapshot.
 *
 * Anonymous shape ``{status}`` is filtered out; we only render
 * when the authenticated tier carries a per-category breakdown.
 * The colour bar at the top reflects the worst entry: ``ok``
 * (green) → ``warning`` (amber) → ``error`` (red).
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { useHealth, type HealthEntry } from "@/lib/api/queries/system";

const LEVEL_BADGE: Record<string, string> = {
  ok: "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40",
  warning: "bg-amber-700/30 text-amber-200 ring-amber-500/40",
  error: "bg-red-700/30 text-red-200 ring-red-500/40",
  info: "bg-sky-700/30 text-sky-200 ring-sky-500/40",
};

function levelClass(level: string | undefined): string {
  return LEVEL_BADGE[level ?? "info"] ?? LEVEL_BADGE["info"]!;
}

function entryKey(entry: HealthEntry, index: number): string {
  return `${entry.category ?? "unknown"}-${index}`;
}

const STATUS_BORDER: Record<string, string> = {
  ok: "border-emerald-700/40",
  warning: "border-amber-700/40",
  error: "border-red-700/40",
};

export function HealthPanel(): ReactElement | null {
  const { data, isPending, isError } = useHealth();

  if (isPending || isError || !data) {
    return null;
  }

  const entries = Array.isArray(data.entries) ? data.entries : [];

  // Hide the panel when everything is green AND there are no
  // entries to surface — keeps the dashboard quiet when the
  // operator has nothing to act on.
  if (data.status === "ok" && entries.length === 0) {
    return null;
  }

  const borderColour =
    STATUS_BORDER[data.status] ?? "border-zinc-700";

  return (
    <section
      className={[
        "rounded-lg border bg-zinc-900/50",
        borderColour,
        "p-4",
      ].join(" ")}
      aria-label={`Health: ${data.status}`}
    >
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">
          System health
        </h2>
        <span
          className={[
            "rounded-full px-2 py-0.5 text-[0.65rem] font-medium",
            "ring-1 ring-inset",
            levelClass(data.status),
          ].join(" ")}
        >
          {data.status}
        </span>
      </header>
      {entries.length > 0 && (
        <ul className="mt-3 space-y-2">
          {entries.map((entry, index) => (
            <li
              key={entryKey(entry, index)}
              className="flex items-start gap-2 text-sm text-zinc-300"
            >
              <span
                className={[
                  "mt-0.5 inline-block h-1.5 w-1.5 rounded-full",
                  entry.level === "error"
                    ? "bg-red-400"
                    : entry.level === "warning"
                      ? "bg-amber-400"
                      : "bg-emerald-400",
                ].join(" ")}
                aria-hidden="true"
              />
              <span className="flex-1">
                <span className="font-mono text-[0.7rem] uppercase text-zinc-500">
                  {entry.category ?? "system"}
                </span>
                <span className="ml-2">
                  {entry.message ?? "(no message)"}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
