/**
 * "Install Romarr" button (T056).
 *
 * Renders only when:
 *   * the browser fired `beforeinstallprompt` (captured in the
 *     install store), AND
 *   * the app isn't already running standalone.
 *
 * Used today on the Settings > UI sub-page; the spec also
 * documents a Dashboard banner on first login that lands with
 * the dashboard slice.
 */

import { Download } from "lucide-react";
import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useInstallPrompt } from "@/lib/pwa/install";

export function InstallButton(): ReactElement | null {
  const { t } = useTranslation("settings");
  const { canInstall, promptInstall } = useInstallPrompt();

  if (!canInstall) {
    return null;
  }

  return (
    <button
      type="button"
      onClick={() => {
        void promptInstall();
      }}
      className={[
        "inline-flex h-10 items-center gap-2 rounded-md px-4",
        "bg-brand text-sm font-medium text-zinc-900",
        "hover:bg-brand-300",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
      ].join(" ")}
    >
      <Download size={16} aria-hidden="true" />
      <span>{t("ui.install.button")}</span>
    </button>
  );
}
