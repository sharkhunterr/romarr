/**
 * Admin user-create form (slice 108).
 *
 * Inline form on Settings > General. Username + password +
 * email + role + active flag. Password is required client-side
 * (the server accepts password=null only for OIDC-only accounts
 * that arrive through SSO; today's slice covers the common
 * password-flow case).
 *
 * On success the list-query is invalidated and the form
 * fields clear so the operator can mint another account
 * straight away.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import {
  useCreateUser,
  type UserRole,
} from "@/lib/api/queries/users";

const ROLES: readonly UserRole[] = ["user", "admin", "service"];

export function CreateUserForm(): ReactElement {
  const { t } = useTranslation("settings");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [isActive, setIsActive] = useState(true);
  const create = useCreateUser();

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (username.trim().length === 0 || password.length === 0) return;
    create.mutate(
      {
        username: username.trim(),
        password,
        email: email.trim() || null,
        role,
        isActive,
      },
      {
        onSuccess: () => {
          setUsername("");
          setPassword("");
          setEmail("");
          setRole("user");
          setIsActive(true);
        },
      },
    );
  };

  return (
    <form
      onSubmit={onSubmit}
      className={[
        "flex flex-col gap-2 rounded-md border border-zinc-800",
        "bg-zinc-900/40 p-3",
      ].join(" ")}
    >
      <h4 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
        {t("general.users.create.title")}
      </h4>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.users.create.usernameLabel")}
          </span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
        </label>

        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.users.create.passwordLabel")}
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
        </label>

        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.users.create.emailLabel")}
          </span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder={t("general.users.create.emailPlaceholder")}
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          />
        </label>

        <label className="block">
          <span className="text-[0.7rem] text-zinc-400">
            {t("general.users.create.roleLabel")}
          </span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className={[
              "mt-1 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-100",
              "ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            ].join(" ")}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`general.users.role.${r}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex items-center gap-2 text-xs text-zinc-300">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 accent-brand"
        />
        <span>{t("general.users.create.activeLabel")}</span>
      </label>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={
            create.isPending ||
            username.trim().length === 0 ||
            password.length === 0
          }
          className={[
            "rounded-md bg-brand/20 px-3 py-1.5 text-xs font-medium",
            "text-brand ring-1 ring-inset ring-brand/40",
            "hover:bg-brand/30",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {create.isPending
            ? t("general.users.create.pending")
            : t("general.users.create.submit")}
        </button>
      </div>
      {create.isError && (
        <p className="text-[0.7rem] text-red-300">{create.error.message}</p>
      )}
      {create.isSuccess && (
        <p className="text-[0.7rem] text-emerald-300">
          {t("general.users.create.success", {
            username: create.data.username,
          })}
        </p>
      )}
    </form>
  );
}
