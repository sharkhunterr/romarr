/**
 * Login page (P-AUTH, T108).
 *
 * Username / password sign-in against POST /api/v3/auth/login
 * (spec 011 + spec 013). On success the backend sets the
 * session cookie consumed by the rest of the SPA and the
 * WebSocket bridge.
 *
 * `returnTo` is read from the query string (set by AuthGuard
 * when it bounces an unauthenticated nav). The redirect after
 * sign-in decodes it before navigating so the operator lands
 * on their intended page rather than a doubly-encoded URL.
 *
 * Strings resolve through the `auth` namespace; rate-limit /
 * unauthenticated errors get dedicated messages, every other
 * `ApiError` falls through to a generic "try again" line.
 *
 * The OIDC "Sign in with SSO" button (T101) is gated on the
 * backend exposing /api/v3/auth/oidc/start + a status probe;
 * deferred until that lands.
 */

import { useState, type FormEvent, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useLogin } from "@/lib/api/queries/auth";

function decodeReturnTo(raw: string): string {
  try {
    const decoded = decodeURIComponent(raw);
    return decoded.length > 0 ? decoded : "/";
  } catch {
    return "/";
  }
}

const FIELD_CLASS = [
  "w-full rounded-md bg-zinc-950 px-3 py-2",
  "text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-brand",
].join(" ");

export function LoginPage(): ReactElement {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const returnToRaw = params.get("returnTo") ?? "/";
  const returnTo = decodeReturnTo(returnToRaw);
  const navigate = useNavigate();
  const login = useLogin();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    login.mutate(
      { username, password },
      {
        onSuccess: () => {
          navigate(returnTo, { replace: true });
        },
      },
    );
  }

  // Map ApiError onto an i18n key under `login.errors.*`. Falls
  // back to the generic message so operators always see
  // something actionable.
  let errorMessage: string | null = null;
  if (login.error !== null) {
    const code = login.error.errorCode;
    if (code === "unauthenticated") {
      errorMessage = t("login.errors.unauthenticated");
    } else if (code === "rate_limited") {
      errorMessage = t("login.errors.rate_limited");
    } else {
      errorMessage = login.error.message || t("login.errors.fallback");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-50">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6"
      >
        <h1 className="font-mono text-xl font-semibold text-brand">
          {t("login.title")}
        </h1>

        <div className="space-y-1.5">
          <label
            htmlFor="login-username"
            className="block text-xs font-medium text-zinc-400"
          >
            {t("login.username")}
          </label>
          <input
            id="login-username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
            className={FIELD_CLASS}
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="login-password"
            className="block text-xs font-medium text-zinc-400"
          >
            {t("login.password")}
          </label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            className={FIELD_CLASS}
          />
        </div>

        {errorMessage !== null && (
          <p role="alert" className="text-xs text-red-400">
            {errorMessage}
          </p>
        )}

        <button
          type="submit"
          disabled={login.isPending}
          className={[
            "w-full rounded-md bg-brand px-3 py-2",
            "text-sm font-medium text-zinc-900",
            "hover:bg-brand-300 focus-visible:outline-none",
            "focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:cursor-not-allowed disabled:opacity-60",
          ].join(" ")}
        >
          {login.isPending ? t("login.submitting") : t("login.submit")}
        </button>

        {returnTo !== "/" && (
          <p className="font-mono text-[0.65rem] text-zinc-600">
            {t("login.returnToHint", { path: returnTo })}
          </p>
        )}

        <p className="text-[0.65rem] text-zinc-600">
          {t("login.setupHint")}{" "}
          <Link
            to="/setup"
            className="text-brand hover:underline focus-visible:outline-none focus-visible:underline"
          >
            {t("setupLink")}
          </Link>
          .
        </p>
      </form>
    </main>
  );
}
