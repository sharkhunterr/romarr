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
 *
 * Strings resolve through the `dashboard` namespace
 * (slice 67).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useSystemStatus } from "@/lib/api/queries/system";

import { ActivityFeed } from "./ActivityFeed";
import { HealthPanel } from "./HealthPanel";
import { QuickActions } from "./QuickActions";
import { StatCard } from "./StatCard";

function useFormatUptime(): (startTime: string | undefined) => string {
  const { t } = useTranslation("dashboard");
  return (startTime) => {
    if (!startTime) return t("stats.uptimeDash");
    const start = new Date(startTime);
    if (Number.isNaN(start.getTime())) return t("stats.uptimeDash");
    const seconds = Math.max(
      0,
      Math.floor((Date.now() - start.getTime()) / 1000),
    );
    if (seconds < 60) return t("stats.uptimeSeconds", { count: seconds });
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return t("stats.uptimeMinutes", { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return t("stats.uptimeHours", { hours, minutes: minutes % 60 });
    }
    const days = Math.floor(hours / 24);
    return t("stats.uptimeDays", { days, hours: hours % 24 });
  };
}

export function DashboardPage(): ReactElement {
  const { t } = useTranslation("dashboard");
  const status = useSystemStatus();
  const formatUptime = useFormatUptime();

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
      </header>

      <HealthPanel />

      <section className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={t("stats.version")}
          value={status.data?.version ?? t("stats.uptimeDash")}
          loading={status.isPending}
          hint={status.data?.databaseType ?? null}
        />
        <StatCard
          label={t("stats.instance")}
          value={status.data?.instanceName ?? "Romarr"}
          loading={status.isPending}
          hint={status.data?.runtimeName ?? null}
        />
        <StatCard
          label={t("stats.uptime")}
          value={formatUptime(status.data?.startTime)}
          loading={status.isPending}
          hint={t("stats.uptimeHint")}
        />
        <StatCard
          label={t("stats.runtime")}
          value={status.data?.runtimeVersion ?? t("stats.uptimeDash")}
          loading={status.isPending}
          hint={status.data?.osName ?? null}
        />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          {t("sections.quickActions")}
        </h2>
        <QuickActions />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-zinc-500">
          {t("sections.recentActivity")}
        </h2>
        <ActivityFeed />
      </section>
    </div>
  );
}
