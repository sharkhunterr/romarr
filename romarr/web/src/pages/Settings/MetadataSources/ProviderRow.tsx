/**
 * One row in the Metadata Sources list (slice 63).
 *
 * Shows provider name (resolved against the i18n catalogue) +
 * configured/credentials badge + health dot + global priority
 * stepper + enable toggle + test button. Updates flow through
 * `useUpdateMetadataProvider` (PUT replaces the row) so a
 * happy-path mutation surfaces immediately on success.
 */

import {
  BookOpen,
  Clock,
  Database,
  Image as ImageIcon,
  KeyRound,
  Monitor,
  Package,
  Puzzle,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useTestMetadataProvider,
  useUpdateMetadataProvider,
  type MetadataProvider,
  type MetadataProviderTestResult,
} from "@/lib/api/queries/metadata-sources";

import { ConfigureProviderModal } from "./ConfigureProviderModal";

const PROVIDER_ICON: Record<string, LucideIcon> = {
  igdb: Database,
  screenscraper: Monitor,
  mobygames: BookOpen,
  launchbox: Package,
  steamgriddb: ImageIcon,
  retroachievements: Trophy,
  howlongtobeat: Clock,
  hasheous: KeyRound,
  playmatch: Puzzle,
};

type Health = "ok" | "fail" | "untested";

function deriveHealth(p: MetadataProvider): Health {
  if (
    p.last_health_check_at === null ||
    p.last_health_check_at === undefined
  ) {
    return "untested";
  }
  return p.last_health_check_ok === true ? "ok" : "fail";
}

const HEALTH_DOT: Record<Health, string> = {
  ok: "bg-brand",
  fail: "bg-red-500",
  untested: "bg-zinc-600",
};

interface ProviderRowProps {
  provider: MetadataProvider;
}

export function ProviderRow(props: ProviderRowProps): ReactElement {
  const { provider } = props;
  const { t } = useTranslation("settings");
  const update = useUpdateMetadataProvider();
  const test = useTestMetadataProvider();

  const [testResult, setTestResult] =
    useState<MetadataProviderTestResult | null>(null);
  const [priorityDraft, setPriorityDraft] = useState<number>(
    provider.priority_global,
  );
  const [configureOpen, setConfigureOpen] = useState(false);

  const displayName = t(
    `metadataSources.providerName.${provider.provider_name}`,
    { defaultValue: provider.provider_name },
  );
  const Icon = PROVIDER_ICON[provider.provider_name] ?? Database;
  const health = deriveHealth(provider);

  function onToggle(): void {
    update.mutate({
      providerName: provider.provider_name,
      payload: { enabled: !provider.enabled },
    });
  }

  function commitPriority(): void {
    if (priorityDraft === provider.priority_global) return;
    update.mutate({
      providerName: provider.provider_name,
      payload: { priority_global: priorityDraft },
    });
  }

  function runTest(): void {
    setTestResult(null);
    test.mutate(provider.provider_name, {
      onSuccess: (result) => setTestResult(result),
      onError: () => setTestResult(null),
    });
  }

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <div
          aria-hidden="true"
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-zinc-800/60 text-zinc-300"
        >
          <Icon size={14} />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {displayName}
            </p>
            <span
              aria-hidden="true"
              className={`inline-block h-2 w-2 rounded-full ${HEALTH_DOT[health]}`}
            />
            {!provider.is_configured && (
              <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-amber-400">
                {t("metadataSources.needsCredentials")}
              </span>
            )}
            {!provider.enabled && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-500">
                {t("metadataSources.disabled")}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <label className="flex items-center gap-2">
              <span>{t("metadataSources.priority.label")}</span>
              <input
                type="number"
                min={1}
                max={999}
                value={priorityDraft}
                onChange={(e) =>
                  setPriorityDraft(Number(e.target.value) || 1)
                }
                onBlur={commitPriority}
                aria-label={t("metadataSources.priority.label")}
                className={[
                  "w-16 rounded-md bg-zinc-950 px-2 py-1",
                  "text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700",
                  "focus-visible:outline-none focus-visible:ring-2",
                  "focus-visible:ring-brand",
                ].join(" ")}
              />
            </label>
            <span className="text-[0.65rem] text-zinc-600">
              {t("metadataSources.priority.help")}
            </span>
          </div>
        </div>
      </div>

      {testResult !== null && (
        <p
          className={`mt-2 text-xs ${
            testResult.ok ? "text-zinc-400" : "text-red-400"
          }`}
          role={testResult.ok ? undefined : "alert"}
        >
          {testResult.ok
            ? `✓ ${t("metadataSources.test.success")}`
            : `✗ ${
                testResult.error ??
                t("metadataSources.test.failure", { message: "" })
              }`}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onToggle}
          disabled={update.isPending}
          className={[
            "min-h-[36px] rounded-md border px-3 text-xs font-medium",
            provider.enabled
              ? "border-zinc-700 text-zinc-200 hover:bg-zinc-900"
              : "border-brand bg-brand text-zinc-900 hover:bg-brand-300",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {provider.enabled
            ? t("metadataSources.toggle.disable")
            : t("metadataSources.toggle.enable")}
        </button>
        <button
          type="button"
          onClick={() => setConfigureOpen(true)}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {t("metadataSources.configure.button")}
        </button>
        <button
          type="button"
          onClick={runTest}
          disabled={test.isPending || !provider.is_configured}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {test.isPending
            ? t("metadataSources.test.running")
            : t("metadataSources.test.button")}
        </button>
      </div>

      {configureOpen && (
        <ConfigureProviderModal
          provider={provider}
          onClose={() => setConfigureOpen(false)}
        />
      )}
    </li>
  );
}
