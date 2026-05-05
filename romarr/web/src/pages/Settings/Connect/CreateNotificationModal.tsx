/**
 * CreateNotificationModal (slice 281).
 *
 * Single-step Add-new flow for the Apprise notification surface.
 * Operator picks a name + Apprise URL, toggles which events
 * trigger the notification, and submits. Per-event Jinja
 * format strings are not exposed here — they default at the
 * backend; the full editor lands in a follow-up slice.
 *
 * Strings resolve through ``settings:connect.create.*``.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateNotification,
  type NotificationCreate,
} from "@/lib/api/queries/notifications";
import { useToastStore } from "@/lib/store/toast";

interface CreateNotificationModalProps {
  onClose: () => void;
}

interface ToggleSpec {
  field: keyof NotificationCreate;
  labelKey: string;
}

const _TOGGLES: ReadonlyArray<ToggleSpec> = [
  { field: "on_grab", labelKey: "connect.create.toggles.onGrab" },
  { field: "on_import", labelKey: "connect.create.toggles.onImport" },
  { field: "on_upgrade", labelKey: "connect.create.toggles.onUpgrade" },
  { field: "on_fail", labelKey: "connect.create.toggles.onFail" },
  {
    field: "on_health_issue",
    labelKey: "connect.create.toggles.onHealthIssue",
  },
  { field: "on_dat_update", labelKey: "connect.create.toggles.onDatUpdate" },
  { field: "on_game_added", labelKey: "connect.create.toggles.onGameAdded" },
];

export function CreateNotificationModal(
  props: CreateNotificationModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateNotification();
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState("");
  const [appriseUrl, setAppriseUrl] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [flags, setFlags] = useState<Record<string, boolean>>({
    on_grab: false,
    on_import: true,
    on_upgrade: true,
    on_fail: true,
    on_health_issue: true,
    on_dat_update: false,
    on_game_added: false,
  });

  const submitting = create.isPending;
  const canSubmit = name.trim().length > 0 && appriseUrl.trim().length > 0;

  function commit(): void {
    if (!canSubmit) return;
    const payload: NotificationCreate = {
      name: name.trim(),
      apprise_url: appriseUrl.trim(),
      enabled,
      on_grab: flags.on_grab ?? false,
      on_import: flags.on_import ?? false,
      on_upgrade: flags.on_upgrade ?? false,
      on_fail: flags.on_fail ?? false,
      on_health_issue: flags.on_health_issue ?? false,
      on_dat_update: flags.on_dat_update ?? false,
      on_game_added: flags.on_game_added ?? false,
      include_health_errors: true,
      include_health_warnings: true,
    };
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("connect.create.successTitle"),
          description: t("connect.create.successBody", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError: (err) => {
        pushToast({
          kind: "error",
          title: t("connect.create.errorTitle"),
          description: err.message,
        });
      },
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("connect.create.modalTitle")}
      className="fixed inset-0 z-50 flex items-start justify-center bg-zinc-950/70 px-4 pt-[8vh] backdrop-blur-sm"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            {t("connect.create.modalTitle")}
          </h2>
          <p className="mt-0.5 text-[0.65rem] text-zinc-500">
            {t("connect.create.subhead")}
          </p>
        </header>

        <div className="space-y-3 p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("connect.create.nameLabel")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("connect.create.namePlaceholder")}
              autoFocus
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("connect.create.urlLabel")}
            </span>
            <input
              type="text"
              value={appriseUrl}
              onChange={(e) => setAppriseUrl(e.target.value)}
              placeholder={t("connect.create.urlPlaceholder")}
              disabled={submitting}
              className="w-full rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1 text-[0.65rem] text-zinc-500">
              {t("connect.create.urlHint")}
            </p>
          </label>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("connect.create.eventsLabel")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2">
              <span className="text-xs text-zinc-200">
                {t("connect.create.toggles.enabled")}
              </span>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            {_TOGGLES.map((toggle) => (
              <label
                key={String(toggle.field)}
                className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2"
              >
                <span className="text-xs text-zinc-300">
                  {t(toggle.labelKey)}
                </span>
                <input
                  type="checkbox"
                  checked={Boolean(flags[String(toggle.field)])}
                  onChange={(e) =>
                    setFlags((prev) => ({
                      ...prev,
                      [String(toggle.field)]: e.target.checked,
                    }))
                  }
                  disabled={submitting}
                  className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
                />
              </label>
            ))}
          </fieldset>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("connect.create.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("connect.create.submitting")
              : t("connect.create.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}
