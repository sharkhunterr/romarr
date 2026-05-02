/**
 * Quick-action buttons (T062 part 4).
 *
 * Three documented actions: trigger missing search, trigger
 * backup, open Wanted. The first two POST to the unified
 * Sonarr-compat command bus; the third navigates.
 *
 * The mutation surfaces a brief inline state on the firing
 * button — full toast feedback lands with the shadcn/ui
 * useToast slice.
 *
 * Strings resolve through `dashboard:quickActions.*`
 * (slice 67).
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useTriggerCommand } from "@/lib/api/queries/system";

interface ActionButtonProps {
  label: string;
  hint: string;
  busyLabel: string;
  onClick: () => void;
  busy?: boolean;
  disabled?: boolean;
}

function ActionButton(props: ActionButtonProps): ReactElement {
  const { label, hint, busyLabel, onClick, busy, disabled } = props;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      className={[
        "rounded-lg border border-zinc-800 bg-zinc-900/60",
        "px-4 py-3 text-left",
        "hover:border-brand/40 hover:bg-zinc-900",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "transition-colors",
      ].join(" ")}
    >
      <p className="text-sm font-medium text-zinc-100">
        {busy ? busyLabel : label}
      </p>
      <p className="mt-1 text-[0.7rem] text-zinc-500">{hint}</p>
    </button>
  );
}

export function QuickActions(): ReactElement {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const trigger = useTriggerCommand();

  const fire = (name: string): void => {
    trigger.mutate({ name });
  };

  const busyLabel = t("quickActions.working");

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
      <ActionButton
        label={t("quickActions.missingSearch.label")}
        hint={t("quickActions.missingSearch.hint")}
        busyLabel={busyLabel}
        onClick={() => fire("MissingSearch")}
        busy={
          trigger.isPending && trigger.variables?.name === "MissingSearch"
        }
      />
      <ActionButton
        label={t("quickActions.backup.label")}
        hint={t("quickActions.backup.hint")}
        busyLabel={busyLabel}
        onClick={() => fire("Backup")}
        busy={trigger.isPending && trigger.variables?.name === "Backup"}
      />
      <ActionButton
        label={t("quickActions.openWanted.label")}
        hint={t("quickActions.openWanted.hint")}
        busyLabel={busyLabel}
        onClick={() => navigate("/wanted")}
      />
    </div>
  );
}
