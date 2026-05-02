/**
 * Dashboard page (T062, P-DASH).
 *
 * The operator's first page after login: at-a-glance system
 * status, current health, recent activity, and the three
 * documented quick actions. Stats cards that need backend
 * endpoints we haven't shipped yet (total games / total
 * releases / disk per platform) are deferred until those
 * endpoints land in their owning specs; today's slice ships
 * the system-status cards plus the cross-spec aggregates
 * that ARE available.
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";

import { useSystemStatus } from "@/lib/api/queries/system";

import { ActivityFeed } from "./ActivityFeed";
import { HealthPanel } from "./HealthPanel";
import { QuickActions } from "./QuickActions";
import { StatCard } from "./StatCard";

function formatUptime(startTime: string | undefined): string {
  if (!startTime) return "—";
  const start = new Date(startTime);
  if (Number.isNaN(start.getTime())) return "—";
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - start.getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

export function DashboardPage(): ReactElement {
  const status = useSystemStatus();

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Overview of system health, recent activity, and quick
          actions.
        </p>
      </header>

      <HealthPanel />

      <section className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Version"
          value={status.data?.version ?? "—"}
          loading={status.isPending}
          hint={status.data?.databaseType ?? null}
        />
        <StatCard
          label="Instance"
          value={status.data?.instanceName ?? "Romarr"}
          loading={status.isPending}
          hint={status.data?.runtimeName ?? null}
        />
        <StatCard
          label="Uptime"
          value={formatUptime(status.data?.startTime)}
          loading={status.isPending}
          hint="since process boot"
        />
        <StatCard
          label="Runtime"
          value={status.data?.runtimeVersion ?? "—"}
          loading={status.isPending}
          hint={status.data?.osName ?? null}
        />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          Quick actions
        </h2>
        <QuickActions />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          Recent activity
        </h2>
        <ActivityFeed />
      </section>
    </div>
  );
}
