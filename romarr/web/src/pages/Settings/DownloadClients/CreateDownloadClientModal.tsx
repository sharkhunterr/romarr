/**
 * CreateDownloadClientModal (slice 283).
 *
 * Single-step Add-new flow for the spec 005 download-client
 * surface. Operator picks the implementation type, host, port,
 * and either an API key (qBittorrent / SAB) or
 * username/password (qBit). Submits a ``DownloadClientCreate``
 * payload to ``POST /api/v3/downloadclient``.
 *
 * The remaining ``DownloadClientCreate`` fields (priority,
 * remove-completed/failed flags, SSL cert validation,
 * url_base, tags) inherit the documented schema defaults so
 * the form stays focused on the bare minimum the operator
 * needs to wire a fresh client; full edit lives in the
 * follow-up edit-modal slice.
 *
 * Strings resolve through ``settings:downloadClients.create.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateDownloadClient,
  type DownloadClientCreate,
  type DownloadClientType,
} from "@/lib/api/queries/download-clients";
import { useToastStore } from "@/lib/store/toast";

interface CreateDownloadClientModalProps {
  onClose: () => void;
}

const _CLIENT_TYPES: ReadonlyArray<DownloadClientType> = [
  "qbittorrent",
  "sabnzbd",
  "transmission",
  "deluge",
  "nzbget",
];

export function CreateDownloadClientModal(
  props: CreateDownloadClientModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateDownloadClient();
  const pushToast = useToastStore((s) => s.push);

  const [type, setType] = useState<DownloadClientType>("qbittorrent");
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState<number>(8080);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [useSsl, setUseSsl] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [enableTorrents, setEnableTorrents] = useState(true);
  const [enableUsenet, setEnableUsenet] = useState(false);

  // Show the API-key field for SAB / NZBGet (Newznab clients);
  // show username + password for qBit / Transmission / Deluge.
  const usesApiKey = type === "sabnzbd" || type === "nzbget";

  const submitting = create.isPending;
  const canSubmit =
    name.trim().length > 0 &&
    host.trim().length > 0 &&
    Number.isFinite(port) &&
    port > 0 &&
    port <= 65535;

  function commit(): void {
    if (!canSubmit) return;
    const payload: DownloadClientCreate = {
      name: name.trim(),
      type,
      host: host.trim(),
      port,
      use_ssl: useSsl,
      enabled,
      enable_for_torrents: enableTorrents,
      enable_for_usenet: enableUsenet,
      remove_completed_downloads: false,
      remove_failed_downloads: true,
      category_default: "romarr",
      priority: 1,
      ssl_cert_validation: "enabled",
      api_key: usesApiKey ? (apiKey.trim() || null) : null,
      username: !usesApiKey ? (username.trim() || null) : null,
      password: !usesApiKey ? (password.trim() || null) : null,
    } as DownloadClientCreate;
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("downloadClients.create.successTitle"),
          description: t("downloadClients.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("downloadClients.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("downloadClients.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("downloadClients.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("downloadClients.create.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("downloadClients.create.typeLabel")}
            </span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as DownloadClientType)}
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {_CLIENT_TYPES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("downloadClients.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("downloadClients.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <div className="grid grid-cols-3 gap-2">
            <label className="col-span-2 block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("downloadClients.create.hostLabel")}
              </span>
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="localhost"
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("downloadClients.create.portLabel")}
              </span>
              <input
                type="number"
                value={port}
                onChange={(e) =>
                  setPort(Number.parseInt(e.target.value, 10) || 0)
                }
                min={1}
                max={65535}
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          </div>

          {usesApiKey ? (
            <label className="block">
              <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                {t("downloadClients.create.apiKeyLabel")}
              </span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={t("downloadClients.create.apiKeyPlaceholder")}
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                  {t("downloadClients.create.usernameLabel")}
                </span>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={submitting}
                  className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
                  {t("downloadClients.create.passwordLabel")}
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                  className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
            </div>
          )}

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("downloadClients.create.flagsLabel")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2">
              <span className="text-xs text-zinc-200">
                {t("downloadClients.create.flags.enabled")}
              </span>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("downloadClients.create.flags.useSsl")}
              </span>
              <input
                type="checkbox"
                checked={useSsl}
                onChange={(e) => setUseSsl(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("downloadClients.create.flags.enableTorrents")}
              </span>
              <input
                type="checkbox"
                checked={enableTorrents}
                onChange={(e) => setEnableTorrents(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("downloadClients.create.flags.enableUsenet")}
              </span>
              <input
                type="checkbox"
                checked={enableUsenet}
                onChange={(e) => setEnableUsenet(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
          </fieldset>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("downloadClients.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("downloadClients.create.submitting")
              : t("downloadClients.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
