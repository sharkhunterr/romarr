/**
 * System > Status tab.
 *
 * Renders the full Sonarr-shape v3+v4 union (version /
 * isProduction / instanceName / urlBase / osName /
 * runtimeVersion / appData / startTime / databaseType /
 * databaseVersion / migrationVersion / runtimeName) per the
 * spec 013 status endpoint authenticated tier.
 *
 * Strings resolve through `system:status.*` (slice 69).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/shared/LoadingSkeleton";
import { useSystemStatus } from "@/lib/api/queries/system";

interface RowProps {
  label: string;
  value: string | undefined;
  fallback: string;
}

function StatusRow(props: RowProps): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-3 border-b border-zinc-800 py-2 last:border-b-0">
      <dt className="text-[0.7rem] uppercase tracking-wider text-zinc-500">
        {props.label}
      </dt>
      <dd className="font-mono text-xs text-zinc-200">
        {props.value ?? props.fallback}
      </dd>
    </div>
  );
}

export function StatusTab(): ReactElement {
  const { t } = useTranslation("system");
  const { data, isPending, isError, error } = useSystemStatus();

  if (isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        title={t("status.loadError")}
        description={error.message}
      />
    );
  }

  const dash = t("status.dash");
  const empty = t("status.empty");
  const unset = t("status.unset");

  return (
    <dl className="rounded-md border border-zinc-800 bg-zinc-900/40 px-4">
      <StatusRow
        label={t("status.labels.version")}
        value={data.version}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.instance")}
        value={data.instanceName}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.production")}
        value={
          data.isProduction === undefined
            ? undefined
            : data.isProduction
              ? t("status.true")
              : t("status.false")
        }
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.os")}
        value={data.osName}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.runtime")}
        value={data.runtimeName}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.runtimeVersion")}
        value={data.runtimeVersion}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.appData")}
        value={data.appData}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.urlBase")}
        value={data.urlBase || empty}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.databaseType")}
        value={data.databaseType}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.databaseVersion")}
        value={data.databaseVersion || unset}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.migrationVersion")}
        value={data.migrationVersion || unset}
        fallback={dash}
      />
      <StatusRow
        label={t("status.labels.startTime")}
        value={data.startTime}
        fallback={dash}
      />
    </dl>
  );
}
