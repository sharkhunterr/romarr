/**
 * System > Status tab.
 *
 * Renders the full Sonarr-shape v3+v4 union (version /
 * isProduction / instanceName / urlBase / osName /
 * runtimeVersion / appData / startTime / databaseType /
 * databaseVersion / migrationVersion / runtimeName) per the
 * spec 013 status endpoint authenticated tier.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/shared/LoadingSkeleton";
import { useSystemStatus } from "@/lib/api/queries/system";

interface RowProps {
  label: string;
  value: string | undefined;
}

function StatusRow(props: RowProps): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-3 border-b border-zinc-800 py-2 last:border-b-0">
      <dt className="text-[0.7rem] uppercase tracking-wider text-zinc-500">
        {props.label}
      </dt>
      <dd className="font-mono text-xs text-zinc-200">
        {props.value ?? "—"}
      </dd>
    </div>
  );
}

export function StatusTab(): ReactElement {
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
        title="Couldn't load system status"
        description={error.message}
      />
    );
  }

  return (
    <dl className="rounded-md border border-zinc-800 bg-zinc-900/40 px-4">
      <StatusRow label="Version" value={data.version} />
      <StatusRow label="Instance" value={data.instanceName} />
      <StatusRow
        label="Production"
        value={data.isProduction ? "true" : "false"}
      />
      <StatusRow label="OS" value={data.osName} />
      <StatusRow label="Runtime" value={data.runtimeName} />
      <StatusRow label="Runtime version" value={data.runtimeVersion} />
      <StatusRow label="App data" value={data.appData} />
      <StatusRow label="URL base" value={data.urlBase || "(empty)"} />
      <StatusRow label="Database type" value={data.databaseType} />
      <StatusRow
        label="Database version"
        value={data.databaseVersion || "(unset)"}
      />
      <StatusRow
        label="Migration version"
        value={data.migrationVersion || "(unset)"}
      />
      <StatusRow label="Started at" value={data.startTime} />
    </dl>
  );
}
