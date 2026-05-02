/**
 * Settings sub-page placeholder (T105).
 *
 * Renders for any /settings/:sub route that doesn't yet have a
 * shipped implementation. The active nav entry stays
 * highlighted; the right column shows a "coming soon" panel
 * resolved against the SETTINGS_NAV_ENTRIES catalogue.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";

import { SETTINGS_NAV_ENTRIES } from "./SettingsNav";

export function SettingsPlaceholder(): ReactElement {
  const { t } = useTranslation("settings");
  const { sub } = useParams<{ sub: string }>();
  const entry = SETTINGS_NAV_ENTRIES.find(
    (e) => e.to === `/settings/${sub ?? ""}`,
  );

  const title = entry
    ? t("placeholder.knownTitle", { section: t(`nav.${entry.slug}`) })
    : t("placeholder.unknownTitle");
  const description = entry
    ? t("placeholder.knownBody")
    : t("placeholder.unknownBody");

  return <EmptyState title={title} description={description} />;
}
