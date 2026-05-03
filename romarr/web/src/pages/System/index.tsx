/**
 * System page (P-SYS, T099 partial).
 *
 * Four documented tabs:
 *   * Status — Sonarr-shape v3+v4 union from
 *     /api/v3/system/status.
 *   * Logs — file list + admin-only download from
 *     /api/v3/system/log/file.
 *   * Backup — file list + manual-trigger button from
 *     /api/v3/system/backup + POST /api/v3/command.
 *   * Tasks — scheduled jobs from /api/v3/system/tasks with
 *     manual-trigger per row.
 *
 * The Updates tab is deferred per the spec ("UI placeholder").
 *
 * Strings resolve through the `system` namespace (slice 69).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { BackupsTab } from "./BackupsTab";
import { LogsTab } from "./LogsTab";
import { StatusTab } from "./StatusTab";
import { TasksTab } from "./TasksTab";

type Tab = "status" | "tasks" | "logs" | "backup";

const TAB_SET: ReadonlySet<Tab> = new Set<Tab>([
  "status",
  "tasks",
  "logs",
  "backup",
]);

function parseSubParam(raw: string | undefined): Tab {
  return raw !== undefined && TAB_SET.has(raw as Tab)
    ? (raw as Tab)
    : "status";
}

interface TabButtonProps {
  tab: Tab;
  active: boolean;
  label: string;
  onClick: (tab: Tab) => void;
}

function TabButton(props: TabButtonProps): ReactElement {
  const { tab, active, label, onClick } = props;
  return (
    <button
      type="button"
      onClick={() => onClick(tab)}
      className={[
        "flex-1 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors",
        active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
      ].join(" ")}
      aria-pressed={active}
    >
      {label}
    </button>
  );
}

export function SystemPage(): ReactElement {
  const { t } = useTranslation("system");
  const navigate = useNavigate();
  const params = useParams<{ sub?: string }>();
  const tab = parseSubParam(params.sub);

  const setTab = (next: Tab): void => {
    navigate(next === "status" ? "/system" : `/system/${next}`);
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t("subtitle")}</p>
      </header>

      <div
        role="tablist"
        aria-label={t("tabs.ariaLabel")}
        className="mb-4 grid grid-cols-4 gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
      >
        <TabButton
          tab="status"
          active={tab === "status"}
          label={t("tabs.status")}
          onClick={setTab}
        />
        <TabButton
          tab="tasks"
          active={tab === "tasks"}
          label={t("tabs.tasks")}
          onClick={setTab}
        />
        <TabButton
          tab="logs"
          active={tab === "logs"}
          label={t("tabs.logs")}
          onClick={setTab}
        />
        <TabButton
          tab="backup"
          active={tab === "backup"}
          label={t("tabs.backup")}
          onClick={setTab}
        />
      </div>

      {tab === "status" && <StatusTab />}
      {tab === "tasks" && <TasksTab />}
      {tab === "logs" && <LogsTab />}
      {tab === "backup" && <BackupsTab />}
    </div>
  );
}
