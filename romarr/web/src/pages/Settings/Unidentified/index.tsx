/**
 * Settings > Unidentified — operator triage view (slice 87).
 *
 * Lists every row from /api/v3/rom/unidentified with a Match…
 * action that opens the manual-match modal (game-search →
 * release-pick → POST /api/v3/rom/unidentified/{id}/match).
 *
 * Mounted under the SettingsLayout shell — visited
 * occasionally for triage, not a daily-use page (so the
 * BottomNav and Header don't surface it).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { ListSkeleton } from "@/components/shared/LoadingSkeleton";
import { useUnidentified } from "@/lib/api/queries/unidentified";

import { UnidentifiedRow } from "./UnidentifiedRow";

export function UnidentifiedPage(): ReactElement {
  const { t } = useTranslation("settings");
  const list = useUnidentified();

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("unidentified.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          {t("unidentified.subtitle")}
        </p>
      </header>

      {list.isLoading && <ListSkeleton rows={4} />}
      {list.isError && (
        <EmptyState
          title={t("unidentified.empty.title")}
          description={list.error.message}
        />
      )}
      {list.isSuccess && list.data.length === 0 && (
        <EmptyState
          title={t("unidentified.empty.title")}
          description={t("unidentified.empty.body")}
        />
      )}
      {list.isSuccess && list.data.length > 0 && (
        <ul className="space-y-2">
          {list.data.map((row) => (
            <UnidentifiedRow key={row.id} unidentified={row} />
          ))}
        </ul>
      )}
    </div>
  );
}
