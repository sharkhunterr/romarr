/**
 * One row in the Download Clients list (slice 61).
 *
 * Mirrors the IndexerRow contract (slice 60) — name + host +
 * type pill + protocol pills + health dot, with Test +
 * double-confirm Delete actions. The DownloadClient
 * ConnectivityTestResult shape differs from the indexer one
 * (error_code: connection / auth / tls / version / internal),
 * so the health interpretation lives here, not shared.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteDownloadClient,
  useTestDownloadClient,
  useToggleDownloadClient,
  type DownloadClient,
  type DownloadClientTestResult,
  type ToggleDownloadClientVariables,
} from "@/lib/api/queries/download-clients";

import { CreateDownloadClientModal } from "./CreateDownloadClientModal";

type Health =
  | "ok"
  | "auth"
  | "connection"
  | "tls"
  | "version"
  | "internal"
  | "untested";

function deriveHealth(client: DownloadClient): Health {
  if (
    client.last_health_at === null ||
    client.last_health_at === undefined
  ) {
    return "untested";
  }
  if (client.last_health_ok === true) {
    return "ok";
  }
  const error = client.last_health_error ?? "";
  if (error.includes("auth")) return "auth";
  if (error.includes("tls")) return "tls";
  if (error.includes("version")) return "version";
  if (error.includes("connection")) return "connection";
  return "internal";
}

const HEALTH_DOT: Record<Health, string> = {
  ok: "bg-brand",
  untested: "bg-zinc-600",
  auth: "bg-red-500",
  connection: "bg-amber-500",
  tls: "bg-red-500",
  version: "bg-amber-500",
  internal: "bg-red-500",
};

type ToggleField =
  | "enabled"
  | "enable_for_torrents"
  | "enable_for_usenet";

const PROTOCOL_LABEL: Record<ToggleField, string> = {
  enabled: "downloadClients.toggle.enabled",
  enable_for_torrents: "downloadClients.protocol.torrent",
  enable_for_usenet: "downloadClients.protocol.usenet",
};

interface DownloadClientRowProps {
  client: DownloadClient;
}

export function DownloadClientRow(props: DownloadClientRowProps): ReactElement {
  const { client } = props;
  const { t } = useTranslation("settings");
  const test = useTestDownloadClient();
  const del = useDeleteDownloadClient();
  const toggle = useToggleDownloadClient();

  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<
    DownloadClientTestResult | null
  >(null);

  const health = deriveHealth(client);
  const typeLabel =
    t(`downloadClients.type.${client.type}`, { defaultValue: client.type });

  function flip(field: ToggleField): void {
    const variables: ToggleDownloadClientVariables = {
      id: client.id,
      [field]: !client[field],
    };
    toggle.mutate(variables);
  }

  function ToggleChip({ field }: { field: ToggleField }): ReactElement {
    const active = client[field];
    return (
      <button
        type="button"
        onClick={() => flip(field)}
        disabled={toggle.isPending}
        aria-pressed={active}
        className={[
          "rounded px-1.5 py-0.5 text-[0.6rem] font-medium uppercase tracking-wider",
          "ring-1 ring-inset transition-colors",
          active
            ? "bg-brand/20 text-brand ring-brand/40 hover:bg-brand/30"
            : "bg-zinc-800 text-zinc-500 ring-zinc-700 hover:bg-zinc-700 hover:text-zinc-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          "disabled:cursor-not-allowed disabled:opacity-60",
        ].join(" ")}
      >
        {active ? "✓ " : ""}
        {t(PROTOCOL_LABEL[field])}
      </button>
    );
  }

  function runTest(): void {
    setTestResult(null);
    test.mutate(client.id, {
      onSuccess: (result) => setTestResult(result),
      onError: () => setTestResult(null),
    });
  }

  function confirmDelete(): void {
    del.mutate(client.id);
  }

  const successLabel = (() => {
    if (testResult === null || !testResult.ok) return null;
    const version = testResult.client_version;
    if (version) {
      return t("downloadClients.test.success", { version });
    }
    return t("downloadClients.test.successNoVersion");
  })();

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-1.5 inline-block h-2 w-2 rounded-full ${HEALTH_DOT[health]}`}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {client.name}
            </p>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
              {typeLabel}
            </span>
          </div>
          <p className="truncate font-mono text-xs text-zinc-500">
            {client.host}
            {client.port !== 0 && `:${client.port}`}
            {client.url_base && client.url_base !== "" && client.url_base}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
              {t(`downloadClients.health.${health}`)}
            </span>
            <ToggleChip field="enabled" />
            <ToggleChip field="enable_for_torrents" />
            <ToggleChip field="enable_for_usenet" />
            {client.category_default !== "" && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-zinc-400">
                {t("downloadClients.category")}: {client.category_default}
              </span>
            )}
          </div>
          {toggle.isError && (
            <p className="text-[0.7rem] text-red-300">
              {toggle.error?.message ??
                t("downloadClients.toggle.errorFallback")}
            </p>
          )}
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
            ? `✓ ${successLabel ?? ""}`
            : `✗ ${
                testResult.error_message ??
                t(
                  `downloadClients.health.${
                    testResult.error_code ?? "internal"
                  }`,
                )
              }`}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => flip("enabled")}
          disabled={toggle.isPending}
          aria-pressed={client.enabled}
          className={[
            "min-h-[36px] rounded-md px-3 text-xs font-medium",
            client.enabled
              ? "border border-zinc-700 bg-brand/15 text-brand hover:bg-brand/25"
              : "border border-zinc-700 bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {client.enabled
            ? t("downloadClients.action.disable")
            : t("downloadClients.action.enable")}
        </button>
        <button
          type="button"
          onClick={runTest}
          disabled={test.isPending}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {test.isPending
            ? t("downloadClients.test.running")
            : t("downloadClients.test.button")}
        </button>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className={[
            "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
            "text-zinc-200 hover:bg-zinc-900",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
          ].join(" ")}
        >
          {t("downloadClients.edit.button")}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={[
            "min-h-[36px] rounded-md border border-red-900/50 px-3 text-xs font-medium",
            "text-red-400 hover:bg-red-950/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
          ].join(" ")}
        >
          {t("downloadClients.delete.button")}
        </button>
      </div>

      {editing && (
        <CreateDownloadClientModal
          editing={client}
          onClose={() => setEditing(false)}
        />
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("downloadClients.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("downloadClients.delete.confirmBody", { name: client.name })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={confirmDelete}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("downloadClients.delete.confirm")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={[
                "min-h-[36px] rounded-md border border-zinc-700 px-3 text-xs font-medium",
                "text-zinc-300 hover:bg-zinc-900",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              ].join(" ")}
            >
              {t("downloadClients.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
