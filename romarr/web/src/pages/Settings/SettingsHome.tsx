/**
 * Settings landing panel (T105, /settings index).
 *
 * Renders when the operator opens /settings without picking
 * a sub-page. Shows a compact welcome panel pointing at the
 * currently-shipped sub-pages — Tags is live; the rest land
 * in upcoming slices.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { Link } from "react-router-dom";

import { SETTINGS_NAV_ENTRIES } from "./SettingsNav";

export function SettingsHome(): ReactElement {
  const shipped = SETTINGS_NAV_ENTRIES.filter((entry) => entry.shipped === true);
  const pending = SETTINGS_NAV_ENTRIES.filter((entry) => entry.shipped !== true);

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="text-base font-medium text-zinc-100">
          Welcome to Settings
        </h2>
        <p className="mt-2 text-sm text-zinc-400">
          Pick a section from the side nav. Each sub-page configures one
          slice of the acquisition pipeline.
        </p>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-zinc-500">
          Available now
        </h3>
        <ul className="space-y-2">
          {shipped.map((entry) => (
            <li
              key={entry.to}
              className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3"
            >
              <Link
                to={entry.to}
                className="flex items-center gap-2 text-sm text-zinc-100 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <span aria-hidden="true">{entry.emoji}</span>
                <span className="font-medium">{entry.label}</span>
                <span className="ml-auto text-zinc-500" aria-hidden="true">
                  →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-zinc-500">
          Coming soon
        </h3>
        <ul className="grid gap-2 sm:grid-cols-2">
          {pending.map((entry) => (
            <li
              key={entry.to}
              className="flex items-center gap-2 rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 px-3 py-2 text-sm text-zinc-500"
            >
              <span aria-hidden="true">{entry.emoji}</span>
              <span>{entry.label}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
