/**
 * Placeholder pages (ROUTING phase).
 *
 * Each page is a stub that proves the route resolves and shows
 * the operator the title + a "coming soon" indicator. Real
 * implementations land in the per-page phases (P-DASH /
 * P-LIB / P-ADD / P-GAME / P-WANT / P-ACT / P-CAL / P-SET /
 * P-SYS / P-AUTH / P-SETUP).
 *
 * Login + Setup are the only public pages today (no AuthGuard);
 * the rest sit behind the guard in the route table.
 */

/* eslint-disable react/jsx-no-literals */

import { type FormEvent, useState, type ReactElement } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useLogin } from "@/lib/api/queries/auth";

function PageShell(props: {
  title: string;
  subtitle?: string;
}): ReactElement {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto max-w-md px-4 py-12">
        <h1 className="font-mono text-2xl font-semibold text-brand">
          {props.title}
        </h1>
        {props.subtitle && (
          <p className="mt-3 text-sm text-zinc-400">{props.subtitle}</p>
        )}
        <p className="mt-8 font-mono text-xs uppercase tracking-widest text-zinc-600">
          coming soon · placeholder
        </p>
      </div>
    </main>
  );
}

export function DashboardPage(): ReactElement {
  return (
    <PageShell
      title="Dashboard"
      subtitle="Stats, health, and recent activity (P-DASH phase)."
    />
  );
}

export function LibraryPage(): ReactElement {
  return (
    <PageShell
      title="Library"
      subtitle="Game grid with filtering / bulk select (P-LIB phase)."
    />
  );
}

export function AddNewPage(): ReactElement {
  return (
    <PageShell
      title="Add New"
      subtitle="IGDB/SS metadata search + add (P-ADD phase)."
    />
  );
}

export function GameDetailPage(): ReactElement {
  return (
    <PageShell
      title="Game"
      subtitle="Tabbed detail (Overview / Releases / History / Files / Manual Search / Notes) — P-GAME phase."
    />
  );
}

export function WantedPage(): ReactElement {
  return (
    <PageShell
      title="Wanted"
      subtitle="Missing | Cutoff tabs (P-WANT phase)."
    />
  );
}

export function ActivityPage(): ReactElement {
  return (
    <PageShell
      title="Activity"
      subtitle="Queue | History tabs (P-ACT phase)."
    />
  );
}

export function CalendarPage(): ReactElement {
  return (
    <PageShell
      title="Calendar"
      subtitle="Preservation events month view (P-CAL phase)."
    />
  );
}

export function SettingsPage(): ReactElement {
  return (
    <PageShell
      title="Settings"
      subtitle="Profiles / Indexers / Download Clients / etc. (P-SET phase)."
    />
  );
}

export function SystemPage(): ReactElement {
  return (
    <PageShell
      title="System"
      subtitle="Status / Logs / Tasks / Backup / Updates (P-SYS phase)."
    />
  );
}

export function LoginPage(): ReactElement {
  const [params] = useSearchParams();
  const returnTo = params.get("returnTo") ?? "/";
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
          // Decode the returnTo so the redirect lands on the
          // operator's intended page rather than a doubly-
          // encoded URL.
          let target = "/";
          try {
            target = decodeURIComponent(returnTo) || "/";
          } catch {
            target = "/";
          }
          navigate(target, { replace: true });
        },
      },
    );
  }

  const errorMessage =
    login.error?.errorCode === "unauthenticated"
      ? "Invalid username or password."
      : login.error?.message;

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-50">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6"
      >
        <h1 className="font-mono text-xl font-semibold text-brand">
          Sign in to Romarr
        </h1>

        <div className="space-y-1.5">
          <label
            htmlFor="login-username"
            className="block text-xs font-medium text-zinc-400"
          >
            Username
          </label>
          <input
            id="login-username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
            className={[
              "w-full rounded-md bg-zinc-950 px-3 py-2",
              "text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="login-password"
            className="block text-xs font-medium text-zinc-400"
          >
            Password
          </label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            className={[
              "w-full rounded-md bg-zinc-950 px-3 py-2",
              "text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700",
              "focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-brand",
            ].join(" ")}
          />
        </div>

        {errorMessage && (
          <p
            role="alert"
            className="text-xs text-red-400"
          >
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
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>

        <p className="font-mono text-[0.65rem] text-zinc-600">
          returnTo: {returnTo}
        </p>
      </form>
    </main>
  );
}

export function SetupPage(): ReactElement {
  return (
    <PageShell
      title="Welcome to Romarr"
      subtitle="First-boot wizard (P-SETUP phase)."
    />
  );
}

export function NotFoundPage(): ReactElement {
  return (
    <PageShell
      title="404 — Not found"
      subtitle="The route you followed doesn't exist."
    />
  );
}
