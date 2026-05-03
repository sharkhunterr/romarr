/**
 * Settings > Profiles (slice 64).
 *
 * Six tabs per the spec:
 *   * Quality      — placeholder until /api/v3/qualityprofile
 *                    UI lands (slice 65 fills this in).
 *   * Region       — placeholder; spec'd backend pending.
 *   * Dump         — placeholder; spec'd backend pending.
 *   * Language     — placeholder; spec'd backend pending.
 *   * Naming       — placeholder; spec'd backend pending.
 *   * Custom Formats — REAL: list / inspect / delete against
 *                      /api/v3/customformat. Visual builder
 *                      ships in a follow-up slice.
 *
 * Default tab on first paint is "custom-formats" since it's
 * the only one with a real backend wired up; the operator
 * landing on /settings/profiles immediately sees something
 * actionable.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { CustomFormatsTab } from "./CustomFormatsTab";
import { DumpTab } from "./DumpTab";
import { LanguageTab } from "./LanguageTab";
import { NamingTab } from "./NamingTab";
import { QualityTab } from "./QualityTab";
import { RegionTab } from "./RegionTab";

type Tab =
  | "quality"
  | "region"
  | "dump"
  | "language"
  | "naming"
  | "custom-formats";

const TAB_SET: ReadonlySet<Tab> = new Set<Tab>([
  "quality",
  "region",
  "dump",
  "language",
  "naming",
  "custom-formats",
]);

function parseTabParam(raw: string | null): Tab {
  return raw !== null && TAB_SET.has(raw as Tab) ? (raw as Tab) : "quality";
}

const TABS: readonly Tab[] = [
  "quality",
  "region",
  "dump",
  "language",
  "naming",
  "custom-formats",
];

const SHIPPED_TABS: ReadonlySet<Tab> = new Set<Tab>([
  "quality",
  "region",
  "dump",
  "language",
  "naming",
  "custom-formats",
]);

interface TabButtonProps {
  tab: Tab;
  active: boolean;
  shipped: boolean;
  onClick: (tab: Tab) => void;
  label: string;
}

function TabButton(props: TabButtonProps): ReactElement {
  return (
    <button
      type="button"
      onClick={() => props.onClick(props.tab)}
      className={[
        "min-h-[36px] rounded-md px-3 py-1.5 text-xs font-medium",
        "transition-colors",
        props.active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
      ].join(" ")}
      aria-pressed={props.active}
    >
      <span>{props.label}</span>
      {!props.shipped && (
        <span
          aria-hidden="true"
          className="ml-1.5 rounded-full bg-zinc-800 px-1 text-[0.55rem] font-medium uppercase tracking-wider text-zinc-500"
        >
          ·
        </span>
      )}
    </button>
  );
}

export function ProfilesPage(): ReactElement {
  const { t } = useTranslation("settings");
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTabParam(searchParams.get("tab"));

  const setTab = (next: Tab): void => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === "quality") params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: false },
    );
  };

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-base font-medium text-zinc-100">
          {t("profiles.title")}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{t("profiles.subtitle")}</p>
      </header>

      <div
        role="tablist"
        aria-label={t("profiles.title")}
        className="flex flex-wrap gap-1 rounded-md border border-zinc-800 bg-zinc-900/40 p-1"
      >
        {TABS.map((id) => (
          <TabButton
            key={id}
            tab={id}
            active={tab === id}
            shipped={SHIPPED_TABS.has(id)}
            onClick={setTab}
            label={t(`profiles.tabs.${id}`)}
          />
        ))}
      </div>

      {tab === "quality" && <QualityTab />}
      {tab === "region" && <RegionTab />}
      {tab === "dump" && <DumpTab />}
      {tab === "language" && <LanguageTab />}
      {tab === "naming" && <NamingTab />}
      {tab === "custom-formats" && <CustomFormatsTab />}
    </div>
  );
}
