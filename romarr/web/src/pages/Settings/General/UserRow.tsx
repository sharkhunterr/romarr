/**
 * Admin user row (slice 107).
 *
 * Read-only audit surface today: username, role pill, active
 * dot, email, last-login timestamp. Per-row delete with
 * double-confirm; the row hides the delete button when the
 * user is the currently-authenticated principal (the API
 * 400s on self-delete, but masking the button avoids the
 * round-trip).
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useDeleteUser,
  type User,
} from "@/lib/api/queries/users";

interface RowProps {
  user: User;
  isSelf: boolean;
}

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(locale);
}

export function UserRow(props: RowProps): ReactElement {
  const { t, i18n } = useTranslation("settings");
  const { user, isSelf } = props;
  const del = useDeleteUser();
  const [confirming, setConfirming] = useState(false);

  const roleTone =
    user.role === "admin"
      ? "bg-emerald-950/40 text-emerald-300"
      : user.role === "service"
        ? "bg-amber-950/40 text-amber-300"
        : "bg-zinc-800 text-zinc-300";

  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-zinc-100">
              {user.username}
            </p>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider ${roleTone}`}
            >
              {t(`general.users.role.${user.role}`, {
                defaultValue: user.role,
              })}
            </span>
            <span
              aria-hidden="true"
              className={[
                "h-2 w-2 rounded-full",
                user.is_active ? "bg-emerald-500" : "bg-zinc-600",
              ].join(" ")}
              title={
                user.is_active
                  ? t("general.users.active")
                  : t("general.users.inactive")
              }
            />
            {isSelf && (
              <span className="rounded bg-brand/20 px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wider text-brand">
                {t("general.users.you")}
              </span>
            )}
          </div>
          {user.email && (
            <p className="truncate text-[0.7rem] text-zinc-400">
              {user.email}
            </p>
          )}
          <p className="text-[0.65rem] text-zinc-500">
            {t("general.users.lastLogin", {
              when: user.last_login_at
                ? formatDate(user.last_login_at, i18n.language)
                : t("general.users.never"),
            })}
          </p>
        </div>
        {!isSelf && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className={[
              "shrink-0 rounded-md border border-red-900/50 px-3 py-1",
              "text-xs font-medium text-red-400 hover:bg-red-950/40",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
            ].join(" ")}
          >
            {t("general.users.delete.button")}
          </button>
        )}
      </div>

      {confirming && (
        <div className="mt-3 rounded-md border border-red-900/50 bg-red-950/20 p-3">
          <p className="text-sm font-medium text-zinc-100">
            {t("general.users.delete.confirmTitle")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {t("general.users.delete.confirmBody", {
              username: user.username,
            })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={() => del.mutate(user.id)}
              disabled={del.isPending}
              className={[
                "min-h-[36px] rounded-md bg-red-600 px-3 text-xs font-medium text-white",
                "hover:bg-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500",
                "disabled:cursor-not-allowed disabled:opacity-60",
              ].join(" ")}
            >
              {t("general.users.delete.confirm")}
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
              {t("general.users.delete.cancel")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
