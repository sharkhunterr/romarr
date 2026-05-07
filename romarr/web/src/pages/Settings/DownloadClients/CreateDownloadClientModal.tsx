/**
 * CreateDownloadClientModal — also handles Edit (slice 356).
 *
 * Single component covering both flows:
 *   * ``editing`` undefined → POST /api/v3/downloadclient
 *   * ``editing`` set       → PUT  /api/v3/downloadclient/{id}
 *
 * The form embeds an in-modal ``Test`` button that probes the
 * current values via POST /api/v3/downloadclient/test (no
 * persistence) so the operator can iterate on host / port /
 * credentials before saving — slice 005's
 * ``?test=true`` flag on create only ran *after* persistence
 * decisions, which made password fixes a save-delete-save loop.
 *
 * Strings resolve through ``settings:downloadClients.create.*``
 * for the Add flow and ``settings:downloadClients.edit.*`` for
 * the Edit flow.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateDownloadClient,
  useProbeDownloadClient,
  useUpdateDownloadClient,
  type DownloadClient,
  type DownloadClientCreate,
  type DownloadClientType,
} from "@/lib/api/queries/download-clients";
import { useToastStore } from "@/lib/store/toast";

interface CreateDownloadClientModalProps {
  onClose: () => void;
  /** When set, the modal pre-fills + PUTs to this client's id. */
  editing?: DownloadClient;
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
  const update = useUpdateDownloadClient();
  const probe = useProbeDownloadClient();
  const pushToast = useToastStore((s) => s.push);
  const isEdit = props.editing !== undefined;

  const [type, setType] = useState<DownloadClientType>(
    (props.editing?.type as DownloadClientType | undefined) ?? "qbittorrent",
  );
  const [name, setName] = useState(props.editing?.name ?? "");
  const [host, setHost] = useState(props.editing?.host ?? "");
  const [port, setPort] = useState<number>(props.editing?.port ?? 8080);
  const [username, setUsername] = useState(props.editing?.username ?? "");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [useSsl, setUseSsl] = useState(props.editing?.use_ssl ?? false);
  const [enabled, setEnabled] = useState(props.editing?.enabled ?? true);
  const [enableTorrents, setEnableTorrents] = useState(
    props.editing?.enable_for_torrents ?? true,
  );
  const [enableUsenet, setEnableUsenet] = useState(
    props.editing?.enable_for_usenet ?? false,
  );

  // qBittorrent / Transmission / Deluge: username + password.
  // SAB / NZBGet (Newznab): api_key.
  const usesApiKey = type === "sabnzbd" || type === "nzbget";

  const submitting = create.isPending || update.isPending;
  const probing = probe.isPending;
  const canSubmit =
    name.trim().length > 0 &&
    host.trim().length > 0 &&
    Number.isFinite(port) &&
    port > 0 &&
    port <= 65535;

  // Build the same payload the backend's create / probe / update
  // endpoints all consume. For edit-without-secret-rewrite we
  // *omit* password / api_key from the PUT body (the backend's
  // contract: only re-encrypt when present), but the probe
  // payload still needs them — we don't have the plaintext
  // post-encryption, so the operator must retype the secret
  // before testing in edit mode. That's surfaced as a hint.
  function buildPayload(includeSecrets: boolean): DownloadClientCreate {
    return {
      name: name.trim(),
      type,
      host: host.trim(),
      port,
      use_ssl: useSsl,
      enabled,
      enable_for_torrents: enableTorrents,
      enable_for_usenet: enableUsenet,
      remove_completed_downloads: props.editing
        ? props.editing.remove_completed_downloads
        : false,
      remove_failed_downloads: props.editing
        ? props.editing.remove_failed_downloads
        : true,
      category_default: props.editing?.category_default ?? "romarr",
      priority: props.editing?.priority ?? 1,
      ssl_cert_validation: props.editing?.ssl_cert_validation ?? "enabled",
      api_key: includeSecrets && usesApiKey ? apiKey.trim() || null : null,
      username: !usesApiKey ? username.trim() || null : null,
      password:
        includeSecrets && !usesApiKey ? password.trim() || null : null,
    } as DownloadClientCreate;
  }

  function commit(): void {
    if (!canSubmit) return;
    if (isEdit && props.editing) {
      // Send a PUT with every editable field. ``type`` is
      // intentionally omitted — DownloadClientUpdate forbids
      // changing the implementation after creation, so the
      // select stays disabled in edit mode and we never put
      // it on the wire (extra='forbid' would 422 otherwise).
      // Secrets are only included when the operator re-typed
      // them so we don't null out the existing credentials.
      const payload: Record<string, unknown> = {
        name: name.trim(),
        host: host.trim(),
        port,
        use_ssl: useSsl,
        enabled,
        enable_for_torrents: enableTorrents,
        enable_for_usenet: enableUsenet,
        username: !usesApiKey ? username.trim() || null : null,
      };
      if (!usesApiKey && password.trim().length > 0) {
        payload.password = password.trim();
      }
      if (usesApiKey && apiKey.trim().length > 0) {
        payload.api_key = apiKey.trim();
      }
      update.mutate(
        { id: props.editing.id, payload: payload },
        {
          onSuccess: (updated) => {
            pushToast({
              kind: "success",
              title: t("downloadClients.edit.successTitle"),
              description: t("downloadClients.edit.successBody", {
                name: updated.name,
              }),
            });
            props.onClose();
          },
          onError: (err) => {
            pushToast({
              kind: "error",
              title: t("downloadClients.edit.errorTitle"),
              description: err.message,
            });
          },
        },
      );
      return;
    }
    create.mutate(buildPayload(true), {
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

  function runTest(): void {
    if (!canSubmit) return;
    probe.reset();
    probe.mutate(buildPayload(true));
  }

  const probeResult = probe.data;
  const probeError = probe.isError ? probe.error : null;
  const titleKey = isEdit
    ? "downloadClients.edit.modalTitle"
    : "downloadClients.create.modalTitle";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t(titleKey, { name: props.editing?.name ?? "" })}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t(titleKey, { name: props.editing?.name ?? "" })}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t(
              isEdit
                ? "downloadClients.edit.subhead"
                : "downloadClients.create.subhead",
            )}
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
              disabled={submitting || isEdit}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
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
                placeholder={
                  isEdit
                    ? t("downloadClients.edit.apiKeyPlaceholder")
                    : t("downloadClients.create.apiKeyPlaceholder")
                }
                disabled={submitting}
                className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
              />
              {isEdit && (
                <p className="mt-1 text-[0.6rem] text-zinc-500">
                  {t("downloadClients.edit.apiKeyHint")}
                </p>
              )}
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
                  placeholder={
                    isEdit
                      ? t("downloadClients.edit.passwordPlaceholder")
                      : ""
                  }
                  disabled={submitting}
                  className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
              {isEdit && (
                <p className="col-span-2 -mt-1 text-[0.6rem] text-zinc-500">
                  {t("downloadClients.edit.passwordHint")}
                </p>
              )}
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

          {(probeResult || probeError) && (
            <div
              className={[
                "rounded-md px-3 py-2 text-xs ring-1 ring-inset",
                probeError
                  ? "bg-red-950/30 text-red-200 ring-red-900/50"
                  : probeResult?.ok
                    ? "bg-emerald-950/30 text-emerald-200 ring-emerald-900/50"
                    : "bg-red-950/30 text-red-200 ring-red-900/50",
              ].join(" ")}
              role={probeResult?.ok && !probeError ? "status" : "alert"}
            >
              {probeError && (
                <span>{probeError.message}</span>
              )}
              {!probeError && probeResult?.ok && (
                <span>
                  {probeResult.client_version
                    ? t("downloadClients.test.success", {
                        version: probeResult.client_version,
                      })
                    : t("downloadClients.test.successNoVersion")}
                </span>
              )}
              {!probeError && probeResult && !probeResult.ok && (
                <span>
                  {probeResult.error_message ??
                    t(
                      `downloadClients.health.${probeResult.error_code ?? "internal"}`,
                    )}
                </span>
              )}
            </div>
          )}
        </div>

        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={runTest}
            disabled={!canSubmit || submitting || probing}
            className="mr-auto rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {probing
              ? t("downloadClients.test.running")
              : t("downloadClients.test.button")}
          </button>
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
              ? t(
                  isEdit
                    ? "downloadClients.edit.submitting"
                    : "downloadClients.create.submitting",
                )
              : t(
                  isEdit
                    ? "downloadClients.edit.submit"
                    : "downloadClients.create.submit",
                )}
          </button>
        </footer>
      </div>
    </div>
  );
}
