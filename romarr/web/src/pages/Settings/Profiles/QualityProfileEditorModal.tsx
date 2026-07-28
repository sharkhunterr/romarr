/**
 * QualityProfileEditorModal — Radarr-style editor for Quality
 * Profiles. Replaces the freeform ``allowed_formats`` textarea
 * with a fixed catalogue of ``format_type`` values (cartridge /
 * disc / compressed / archive / package) that operators toggle
 * in / out and reorder with up/down buttons. Preferred +
 * Upgrade-Until picks are radios scoped to the current allowed
 * subset.
 *
 * Handles both create and edit flows via the optional ``profile``
 * prop. Cross-field validation mirrors the backend:
 *   * at least one allowed format
 *   * preferred_format ∈ allowed_formats
 *   * upgrade_until_format ∈ allowed_formats
 */

import { ArrowDown, ArrowUp } from "lucide-react";
import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateQualityProfile,
  useUpdateQualityProfile,
  type QualityProfile,
  type QualityProfileCreate,
} from "@/lib/api/queries/quality-profiles";
import { useToastStore } from "@/lib/store/toast";

interface QualityProfileEditorModalProps {
  onClose: () => void;
  /** Present when editing; absent when creating a new profile. */
  profile?: QualityProfile;
}

// Canonical format types recognised by the platform-pack schema.
// Kept in the UX ordering operators expect (best → worst quality).
const _FORMAT_TYPES = [
  "cartridge",
  "disc",
  "package",
  "compressed",
  "archive",
] as const;

type FormatType = (typeof _FORMAT_TYPES)[number];

function _isKnownFormat(f: string): f is FormatType {
  return (_FORMAT_TYPES as readonly string[]).includes(f);
}

/**
 * Merge stored ``allowed_formats`` (may include custom / legacy
 * strings) into the canonical ordering. Known formats come first
 * in their stored order; unknown formats trail (preserved so
 * editing a legacy profile doesn't silently drop entries).
 */
function _initialAllowed(stored: readonly string[]): string[] {
  const known = stored.filter(_isKnownFormat);
  const unknown = stored.filter((f) => !_isKnownFormat(f));
  return [...known, ...unknown];
}

export function QualityProfileEditorModal(
  props: QualityProfileEditorModalProps,
): ReactElement {
  const { t } = useTranslation("settings");
  const create = useCreateQualityProfile();
  const update = useUpdateQualityProfile();
  const pushToast = useToastStore((s) => s.push);
  const isEdit = props.profile !== undefined;
  const busy = create.isPending || update.isPending;

  const [name, setName] = useState(props.profile?.name ?? "");
  const [allowedOrdered, setAllowedOrdered] = useState<string[]>(
    props.profile ? _initialAllowed(props.profile.allowed_formats) : ["cartridge"],
  );
  const [preferredFormat, setPreferredFormat] = useState(
    props.profile?.preferred_format ?? "cartridge",
  );
  const [upgradeUntilFormat, setUpgradeUntilFormat] = useState(
    props.profile?.upgrade_until_format ?? "cartridge",
  );
  const [requireDatVerified, setRequireDatVerified] = useState(
    props.profile?.require_dat_verified ?? false,
  );
  const [allowArchive, setAllowArchive] = useState(
    props.profile?.allow_archive_double_compression ?? false,
  );
  const [autoGrabMinScore, setAutoGrabMinScore] = useState<number>(
    props.profile?.auto_grab_min_score ?? 0,
  );

  // Keep preferred + upgrade_until in sync when the allowed set
  // shrinks. If the current pick is no longer allowed, fall back
  // to the first allowed entry.
  useEffect(() => {
    if (allowedOrdered.length === 0) return;
    const first = allowedOrdered[0]!;
    if (!allowedOrdered.includes(preferredFormat)) {
      setPreferredFormat(first);
    }
    if (!allowedOrdered.includes(upgradeUntilFormat)) {
      setUpgradeUntilFormat(first);
    }
  }, [allowedOrdered, preferredFormat, upgradeUntilFormat]);

  function _toggle(fmt: string): void {
    setAllowedOrdered((prev) =>
      prev.includes(fmt) ? prev.filter((f) => f !== fmt) : [...prev, fmt],
    );
  }

  function _move(fmt: string, dir: -1 | 1): void {
    setAllowedOrdered((prev) => {
      const idx = prev.indexOf(fmt);
      if (idx === -1) return prev;
      const swap = idx + dir;
      if (swap < 0 || swap >= prev.length) return prev;
      const next = [...prev];
      const a = next[idx]!;
      const b = next[swap]!;
      next[idx] = b;
      next[swap] = a;
      return next;
    });
  }

  const validationError: string | null = (() => {
    if (name.trim().length === 0)
      return t("profiles.quality.editor.errorNameEmpty");
    if (allowedOrdered.length === 0)
      return t("profiles.quality.editor.errorAllowedEmpty");
    if (!allowedOrdered.includes(preferredFormat))
      return t("profiles.quality.editor.errorPreferredNotAllowed");
    if (!allowedOrdered.includes(upgradeUntilFormat))
      return t("profiles.quality.editor.errorUpgradeNotAllowed");
    return null;
  })();
  const canSubmit = validationError === null && !busy;

  function commit(): void {
    if (!canSubmit) return;
    const payload: QualityProfileCreate = {
      name: name.trim(),
      allowed_formats: allowedOrdered,
      preferred_format: preferredFormat,
      upgrade_until_format: upgradeUntilFormat,
      require_dat_verified: requireDatVerified,
      allow_archive_double_compression: allowArchive,
      auto_grab_min_score: Math.max(0, Math.floor(autoGrabMinScore || 0)),
    };
    const onError = (err: { message: string }): void => {
      pushToast({
        kind: "error",
        title: isEdit
          ? t("profiles.quality.editor.updateError")
          : t("profiles.quality.editor.createError"),
        description: err.message,
      });
    };
    if (isEdit && props.profile) {
      update.mutate(
        { id: props.profile.id, payload },
        {
          onSuccess: (saved) => {
            pushToast({
              kind: "success",
              title: t("profiles.quality.editor.updateSuccess", {
                name: saved.name,
              }),
            });
            props.onClose();
          },
          onError,
        },
      );
      return;
    }
    create.mutate(payload, {
      onSuccess: (created) => {
        pushToast({
          kind: "success",
          title: t("profiles.quality.editor.createSuccess", {
            name: created.name,
          }),
        });
        props.onClose();
      },
      onError,
    });
  }

  // Build the render list: allowed formats in their operator-set
  // order first, then the remaining canonical formats as
  // "available to add".
  const availableFormats = _FORMAT_TYPES.filter(
    (f) => !allowedOrdered.includes(f),
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="qp-editor-title"
      onClick={props.onClose}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-950/70 px-4 py-[4vh] backdrop-blur-sm sm:items-center"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[92vh] w-full max-w-xl flex-col rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <div>
            <h2
              id="qp-editor-title"
              className="text-sm font-semibold text-zinc-100"
            >
              {isEdit
                ? t("profiles.quality.editor.editTitle", {
                    name: props.profile?.name ?? "",
                  })
                : t("profiles.quality.editor.createTitle")}
            </h2>
            <p className="mt-0.5 text-[0.65rem] text-zinc-500">
              {t("profiles.quality.editor.subhead")}
            </p>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            aria-label={t("profiles.quality.editor.close")}
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <label className="block">
            <span className="mb-1 block text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.quality.editor.name")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
              placeholder={t("profiles.quality.editor.namePlaceholder")}
              autoFocus
              className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
            />
          </label>

          <section className="space-y-2">
            <header className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-zinc-200">
                  {t("profiles.quality.editor.formatsTitle")}
                </p>
                <p className="text-[0.65rem] text-zinc-500">
                  {t("profiles.quality.editor.formatsHint")}
                </p>
              </div>
            </header>

            <ul className="space-y-1">
              {allowedOrdered.map((fmt, idx) => (
                <li
                  key={fmt}
                  className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-1.5"
                >
                  <span className="rounded bg-brand/20 px-1.5 py-0.5 font-mono text-[0.6rem] text-brand">
                    {idx + 1}
                  </span>
                  <span className="font-mono text-xs text-zinc-100">
                    {fmt}
                  </span>
                  <div className="flex items-center gap-1">
                    <label
                      className="flex items-center gap-1 text-[0.65rem] text-zinc-400"
                      title={t("profiles.quality.editor.preferredHint")}
                    >
                      <input
                        type="radio"
                        name="preferred"
                        checked={preferredFormat === fmt}
                        onChange={() => setPreferredFormat(fmt)}
                        disabled={busy}
                        className="h-3 w-3"
                      />
                      P
                    </label>
                    <label
                      className="flex items-center gap-1 text-[0.65rem] text-zinc-400"
                      title={t("profiles.quality.editor.upgradeHint")}
                    >
                      <input
                        type="radio"
                        name="upgrade"
                        checked={upgradeUntilFormat === fmt}
                        onChange={() => setUpgradeUntilFormat(fmt)}
                        disabled={busy}
                        className="h-3 w-3"
                      />
                      U
                    </label>
                  </div>
                  <div className="flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => _move(fmt, -1)}
                      disabled={busy || idx === 0}
                      aria-label={t("profiles.quality.editor.moveUp")}
                      className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <ArrowUp size={12} strokeWidth={2.4} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => _move(fmt, 1)}
                      disabled={busy || idx === allowedOrdered.length - 1}
                      aria-label={t("profiles.quality.editor.moveDown")}
                      className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <ArrowDown size={12} strokeWidth={2.4} aria-hidden="true" />
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => _toggle(fmt)}
                    disabled={busy}
                    aria-label={t("profiles.quality.editor.remove")}
                    className="rounded border border-red-900/50 px-2 py-0.5 text-[0.65rem] text-red-400 hover:bg-red-950/40 disabled:opacity-40"
                  >
                    −
                  </button>
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap gap-1 rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-2">
              <span className="pr-2 text-[0.65rem] uppercase tracking-wider text-zinc-500">
                {t("profiles.quality.editor.available")}:
              </span>
              {availableFormats.length === 0 && (
                <span className="text-[0.65rem] text-zinc-600">—</span>
              )}
              {availableFormats.map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => _toggle(fmt)}
                  disabled={busy}
                  className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 font-mono text-[0.65rem] text-zinc-200 hover:border-brand hover:bg-zinc-800 disabled:opacity-40"
                >
                  + {fmt}
                </button>
              ))}
            </div>

            <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-900/20 p-2 text-[0.65rem] text-zinc-500">
              <b className="text-zinc-400">P</b>{" "}
              {t("profiles.quality.editor.preferredLegend")} ·{" "}
              <b className="text-zinc-400">U</b>{" "}
              {t("profiles.quality.editor.upgradeLegend")}
            </p>
          </section>

          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[0.65rem] uppercase tracking-widest text-zinc-500">
              {t("profiles.quality.editor.flagsTitle")}
            </legend>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("profiles.quality.editor.requireDat")}
              </span>
              <input
                type="checkbox"
                checked={requireDatVerified}
                onChange={(e) => setRequireDatVerified(e.target.checked)}
                disabled={busy}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="text-xs text-zinc-300">
                {t("profiles.quality.editor.allowArchive")}
              </span>
              <input
                type="checkbox"
                checked={allowArchive}
                onChange={(e) => setAllowArchive(e.target.checked)}
                disabled={busy}
                className="h-4 w-4 cursor-pointer rounded border-zinc-700 bg-zinc-900 text-brand focus:ring-brand"
              />
            </label>
            <label className="flex flex-col gap-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2">
              <span className="flex items-center justify-between gap-2">
                <span className="text-xs text-zinc-300">
                  {t("profiles.quality.editor.autoGrabMinScore")}
                </span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={autoGrabMinScore}
                  onChange={(e) =>
                    setAutoGrabMinScore(
                      Number.isFinite(e.target.valueAsNumber)
                        ? e.target.valueAsNumber
                        : 0,
                    )
                  }
                  disabled={busy}
                  className="w-24 rounded-md bg-zinc-900 px-2 py-1 text-right text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                />
              </span>
              <span className="text-[0.65rem] text-zinc-500">
                {t("profiles.quality.editor.autoGrabMinScoreHint")}
              </span>
            </label>
          </fieldset>

          {validationError !== null && name.length > 0 && (
            <p
              role="status"
              className="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-1.5 text-[0.65rem] text-amber-200"
            >
              {validationError}
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button
            type="button"
            onClick={props.onClose}
            disabled={busy}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("profiles.quality.editor.cancel")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canSubmit}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy
              ? t("profiles.quality.editor.saving")
              : isEdit
                ? t("profiles.quality.editor.update")
                : t("profiles.quality.editor.save")}
          </button>
        </footer>
      </div>
    </div>
  );
}
