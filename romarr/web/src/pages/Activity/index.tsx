/**
 * Activity page (P-ACT, T093 partial).
 *
 * Two tabs: Queue | History.
 *   * Queue — live download list, polled every 5s. Per-row
 *     pause/resume/remove action lands when the spec 005
 *     download-client integration ships.
 *   * History — paginated audit trail (UNION across
 *     import_history / search_history / job_run from
 *     spec 013 T058). Filter chips deferred.
 *
 * Strings resolve through the `activity` namespace (slice 68).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { ActiveTasksBanner } from "./ActiveTasksBanner";
import { HistoryList } from "./HistoryList";
import { QueueList } from "./QueueList";

type Tab = "queue" | "history";

function parseTabParam(raw: string | null): Tab {
  return raw === "history" ? "history" : "queue";
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

export function ActivityPage(): ReactElement {
  const { t } = useTranslation("activity");
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTabParam(searchParams.get("tab"));

  const setTab = (next: Tab): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "queue") params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: false },
    );
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{t(`tabHint.${tab}`)}</p>
      </header>

      <ActiveTasksBanner />

      <div
        role="tablist"
        aria-label={t("tabs.ariaLabel")}
        className="mb-4 flex gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
      >
        <TabButton
          tab="queue"
          active={tab === "queue"}
          label={t("tabs.queue")}
          onClick={setTab}
        />
        <TabButton
          tab="history"
          active={tab === "history"}
          label={t("tabs.history")}
          onClick={setTab}
        />
      </div>

      {tab === "queue" ? <QueueList /> : <HistoryList />}
    </div>
  );
}
