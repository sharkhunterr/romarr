/**
 * Settings sub-page placeholder (T105).
 *
 * Renders for any /settings/:sub route that doesn't yet have a
 * shipped implementation. The active nav entry stays
 * highlighted; the right column shows a "coming soon" panel
 * resolved against the SETTINGS_NAV_ENTRIES catalogue.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { useParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";

import { SETTINGS_NAV_ENTRIES } from "./SettingsNav";

export function SettingsPlaceholder(): ReactElement {
  const { sub } = useParams<{ sub: string }>();
  const entry = SETTINGS_NAV_ENTRIES.find(
    (e) => e.to === `/settings/${sub ?? ""}`,
  );

  const title = entry ? entry.label : "Unknown section";
  const description = entry
    ? "This Settings sub-page is documented in the spec but hasn't shipped yet. The slice that wires it up against its REST surface is coming."
    : "No Settings section is registered at this path. Pick another from the side nav.";

  return (
    <EmptyState title={title} description={description} />
  );
}
