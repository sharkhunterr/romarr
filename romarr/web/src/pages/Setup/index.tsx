/**
 * Setup wizard (P-SETUP, T109).
 *
 * Three-step first-boot flow against POST /api/v3/auth/setup
 * (spec 011 + 013):
 *
 *   1. Welcome — intro + a "where do I find the token?"
 *      explainer.
 *   2. Admin — operator pastes the X-Setup-Token + picks
 *      a username + password (min 8). The mutation creates
 *      the admin atomically and sets the session cookie.
 *   3. Done — confirms; surfaces "configure later" links to
 *      the Settings sub-pages that handle the parts the
 *      backend setup endpoint doesn't yet provision
 *      (libraries / indexers / download clients).
 *
 * The original spec's 5-step variant (Welcome / CreateAdmin /
 * Library / DownloadClient / Indexer / Done) collapses to
 * 3 because spec 013 only ships /api/v3/auth/setup. The other
 * steps are deferred until the relevant Settings sub-pages
 * land — the wizard surfaces them as deferred next-actions
 * on the Done screen.
 *
 * Strings resolve through the `setup` namespace.
 */

import { useState, type FormEvent, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { useSetup } from "@/lib/api/queries/setup";

type Step = "welcome" | "admin" | "done";
const TOTAL_STEPS = 3;
const STEP_INDEX: Record<Step, number> = { welcome: 1, admin: 2, done: 3 };

const FIELD_CLASS = [
  "w-full rounded-md bg-zinc-950 px-3 py-2",
  "text-sm text-zinc-100 ring-1 ring-inset ring-zinc-700",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-brand",
].join(" ");

const PRIMARY_BUTTON = [
  "inline-flex h-10 items-center justify-center rounded-md px-4",
  "bg-brand text-sm font-medium text-zinc-900",
  "hover:bg-brand-300 focus-visible:outline-none",
  "focus-visible:ring-2 focus-visible:ring-brand",
  "disabled:cursor-not-allowed disabled:opacity-60",
].join(" ");

const SECONDARY_BUTTON = [
  "inline-flex h-10 items-center justify-center rounded-md px-4",
  "border border-zinc-700 bg-transparent text-sm font-medium text-zinc-200",
  "hover:bg-zinc-900 focus-visible:outline-none",
  "focus-visible:ring-2 focus-visible:ring-brand",
].join(" ");

interface ShellProps {
  step: Step;
  children: ReactElement | ReactElement[];
}

function WizardShell(props: ShellProps): ReactElement {
  const { t } = useTranslation("setup");
  const stepIndex = STEP_INDEX[props.step];
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 py-10 text-zinc-50">
      <div className="w-full max-w-md space-y-4">
        <header className="space-y-1 text-center">
          <p className="font-mono text-xs uppercase tracking-widest text-zinc-500">
            {t("stepLabel", { current: stepIndex, total: TOTAL_STEPS })}
          </p>
          <h1 className="font-mono text-xl font-semibold text-brand">
            {t("title")}
          </h1>
        </header>
        <section className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6">
          {props.children}
        </section>
      </div>
    </main>
  );
}

function WelcomeStep(props: { onNext: () => void }): ReactElement {
  const { t } = useTranslation("setup");
  return (
    <WizardShell step="welcome">
      <h2 className="text-base font-medium text-zinc-100">
        {t("welcome.heading")}
      </h2>
      <p className="text-sm text-zinc-400">{t("welcome.body")}</p>
      <p className="rounded-md border border-dashed border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-500">
        {t("welcome.tokenHint")}
      </p>
      <div className="flex justify-end">
        <button type="button" onClick={props.onNext} className={PRIMARY_BUTTON}>
          {t("next")}
        </button>
      </div>
    </WizardShell>
  );
}

interface AdminStepProps {
  onBack: () => void;
  onSuccess: () => void;
}

function AdminStep(props: AdminStepProps): ReactElement {
  const { t } = useTranslation("setup");
  const setup = useSetup();
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setup.mutate(
      { token: token.trim(), username, password },
      { onSuccess: () => props.onSuccess() },
    );
  }

  let errorMessage: string | null = null;
  if (setup.error !== null) {
    const code = setup.error.errorCode;
    if (code === "setup_token_invalid") {
      errorMessage = t("errors.setupTokenInvalid");
    } else if (code === "setup_already_done") {
      errorMessage = t("errors.setupAlreadyDone");
    } else if (setup.error.status === 422) {
      errorMessage = t("errors.validation");
    } else {
      errorMessage = setup.error.message || t("errors.fallback");
    }
  }

  return (
    <WizardShell step="admin">
      <h2 className="text-base font-medium text-zinc-100">
        {t("admin.heading")}
      </h2>
      <p className="text-sm text-zinc-400">{t("admin.body")}</p>

      <form onSubmit={onSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <label
            htmlFor="setup-token"
            className="block text-xs font-medium text-zinc-400"
          >
            {t("admin.token")}
          </label>
          <input
            id="setup-token"
            type="text"
            autoComplete="off"
            value={token}
            placeholder={t("admin.tokenPlaceholder")}
            onChange={(event) => setToken(event.target.value)}
            required
            className={`${FIELD_CLASS} font-mono`}
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="setup-username"
            className="block text-xs font-medium text-zinc-400"
          >
            {t("admin.username")}
          </label>
          <input
            id="setup-username"
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
            htmlFor="setup-password"
            className="block text-xs font-medium text-zinc-400"
          >
            {t("admin.password")}
          </label>
          <input
            id="setup-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
            className={FIELD_CLASS}
          />
          <p className="text-[0.65rem] text-zinc-500">
            {t("admin.passwordHelp")}
          </p>
        </div>

        {errorMessage !== null && (
          <p role="alert" className="text-xs text-red-400">
            {errorMessage}
          </p>
        )}

        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={props.onBack}
            className={SECONDARY_BUTTON}
          >
            {t("back")}
          </button>
          <button
            type="submit"
            disabled={setup.isPending}
            className={PRIMARY_BUTTON}
          >
            {setup.isPending ? t("admin.submitting") : t("admin.submit")}
          </button>
        </div>
      </form>
    </WizardShell>
  );
}

interface DoneCardProps {
  to: string;
  emoji: string;
  label: string;
}

function DoneCard(props: DoneCardProps): ReactElement {
  return (
    <Link
      to={props.to}
      className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      <span aria-hidden="true">{props.emoji}</span>
      <span className="flex-1">{props.label}</span>
      <span aria-hidden="true" className="text-zinc-500">→</span>
    </Link>
  );
}

function DoneStep(): ReactElement {
  const { t } = useTranslation("setup");
  const navigate = useNavigate();

  return (
    <WizardShell step="done">
      <h2 className="text-base font-medium text-zinc-100">
        {t("done.heading")}
      </h2>
      <p className="text-sm text-zinc-400">{t("done.body")}</p>

      <button
        type="button"
        onClick={() => navigate("/", { replace: true })}
        className={`${PRIMARY_BUTTON} w-full`}
      >
        {t("done.openDashboard")}
      </button>

      <div className="space-y-2">
        <p className="text-[0.65rem] uppercase tracking-widest text-zinc-500">
          {t("done.configureLater")}
        </p>
        <ul className="space-y-2">
          <li>
            <DoneCard
              to="/settings/media-management"
              emoji="📁"
              label={t("done.configureMediaManagement")}
            />
          </li>
          <li>
            <DoneCard
              to="/settings/indexers"
              emoji="🔍"
              label={t("done.configureIndexers")}
            />
          </li>
          <li>
            <DoneCard
              to="/settings/download-clients"
              emoji="⬇️"
              label={t("done.configureDownloadClients")}
            />
          </li>
        </ul>
      </div>
    </WizardShell>
  );
}

export function SetupPage(): ReactElement {
  const [step, setStep] = useState<Step>("welcome");

  if (step === "welcome") {
    return <WelcomeStep onNext={() => setStep("admin")} />;
  }
  if (step === "admin") {
    return (
      <AdminStep
        onBack={() => setStep("welcome")}
        onSuccess={() => setStep("done")}
      />
    );
  }
  return <DoneStep />;
}
