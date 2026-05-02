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
 */

/* eslint-disable react/jsx-no-literals -- replaced by i18n in
   the I18N phase. */

import { type ReactElement } from "react";
import { useNavigate } from "react-router-dom";

import { useTriggerCommand } from "@/lib/api/queries/system";

interface ActionButtonProps {
  label: string;
  hint: string;
  onClick: () => void;
  busy?: boolean;
  disabled?: boolean;
}

function ActionButton(props: ActionButtonProps): ReactElement {
  const { label, hint, onClick, busy, disabled } = props;
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
        {busy ? "Working…" : label}
      </p>
      <p className="mt-1 text-[0.7rem] text-zinc-500">{hint}</p>
    </button>
  );
}

export function QuickActions(): ReactElement {
  const navigate = useNavigate();
  const trigger = useTriggerCommand();

  const fire = (name: string): void => {
    trigger.mutate({ name });
  };

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
      <ActionButton
        label="Missing search"
        hint="Search every wanted release."
        onClick={() => fire("MissingSearch")}
        busy={
          trigger.isPending && trigger.variables?.name === "MissingSearch"
        }
      />
      <ActionButton
        label="Backup now"
        hint="Trigger an immediate backup."
        onClick={() => fire("Backup")}
        busy={trigger.isPending && trigger.variables?.name === "Backup"}
      />
      <ActionButton
        label="Open wanted"
        hint="Drill into missing + cutoff lists."
        onClick={() => navigate("/wanted")}
      />
    </div>
  );
}
