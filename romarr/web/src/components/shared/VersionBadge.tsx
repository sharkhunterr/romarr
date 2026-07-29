/**
 * Compact version badge for the app header.
 *
 * Shows the running version. When a GitHub release newer than the
 * running one is available, the badge turns amber and links to the
 * release page — same pattern as Sonarr / Radarr's "Update available"
 * chip in the top-right nav.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useVersionCheck } from "@/lib/api/queries/version-check";

export function VersionBadge(): ReactElement | null {
  const { t } = useTranslation("common");
  const v = useVersionCheck();
  if (!v.isSuccess) return null;
  const data = v.data;
  const upToDate = !data.updateAvailable;
  if (upToDate) {
    return (
      <span
        className="rounded-md bg-zinc-800 px-2 py-0.5 font-mono text-[0.6rem] text-zinc-400"
        title={t("versionBadge.upToDate", { version: data.current })}
      >
        v{data.current}
      </span>
    );
  }
  return (
    <a
      href={data.releaseUrl ?? "#"}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-amber-700/50 bg-amber-950/40 px-2 py-0.5 font-mono text-[0.6rem] text-amber-300 hover:bg-amber-950/60"
      title={t("versionBadge.updateAvailableTooltip", {
        current: data.current,
        latest: data.latest,
      })}
    >
      <span>v{data.current}</span>
      <span aria-hidden="true">→</span>
      <span className="font-semibold">v{data.latest}</span>
    </a>
  );
}
