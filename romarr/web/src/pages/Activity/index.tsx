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
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { useState, type ReactElement } from "react";

import { HistoryList } from "./HistoryList";
import { QueueList } from "./QueueList";

type Tab = "queue" | "history";

const TAB_LABEL: Record<Tab, string> = {
  queue: "Queue",
  history: "History",
};

const TAB_HINT: Record<Tab, string> = {
  queue: "Active downloads, polled every 5 s.",
  history:
    "Imports, searches, and scheduled tasks across the whole audit trail.",
};

interface TabButtonProps {
  tab: Tab;
  active: boolean;
  onClick: (tab: Tab) => void;
}

function TabButton(props: TabButtonProps): ReactElement {
  const { tab, active, onClick } = props;
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
      {TAB_LABEL[tab]}
    </button>
  );
}

export function ActivityPage(): ReactElement {
  const [tab, setTab] = useState<Tab>("queue");

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-8">
      <header className="mb-6">
        <h1 className="font-mono text-xl font-semibold text-brand">
          Activity
        </h1>
        <p className="mt-1 text-sm text-zinc-400">{TAB_HINT[tab]}</p>
      </header>

      <div
        role="tablist"
        aria-label="Activity tabs"
        className="mb-4 flex gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
      >
        <TabButton
          tab="queue"
          active={tab === "queue"}
          onClick={setTab}
        />
        <TabButton
          tab="history"
          active={tab === "history"}
          onClick={setTab}
        />
      </div>

      {tab === "queue" ? <QueueList /> : <HistoryList />}
    </div>
  );
}
