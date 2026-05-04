/**
 * ErrorFallback — visual half of PageErrorBoundary.
 *
 * Split into its own functional component so it can use hooks
 * (``useTranslation``) — class components can't.
 */

import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

interface ErrorFallbackProps {
  error: Error;
  errorId: string;
  onRetry: () => void;
}

export function ErrorFallback(props: ErrorFallbackProps): ReactElement {
  const { error, errorId, onRetry } = props;
  const { t } = useTranslation("errors");
  const [copied, setCopied] = useState(false);

  function handleCopy(): void {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(errorId).then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      });
    }
  }

  return (
    <div
      role="alert"
      aria-live="polite"
      className="mx-auto my-8 max-w-md rounded-lg border border-red-700/40 bg-zinc-900/80 p-5 text-zinc-100"
    >
      <h2 className="text-lg font-semibold">{t("boundary.title")}</h2>
      <p className="mt-2 text-sm text-zinc-300">{t("boundary.body")}</p>
      <p className="mt-3 break-words font-mono text-xs text-zinc-500">
        {error.message}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
        >
          {t("boundary.retry")}
        </button>
        <Link
          to="/"
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          {t("boundary.dashboard")}
        </Link>
        <button
          type="button"
          onClick={handleCopy}
          className="ml-auto rounded-md px-2 py-1 text-xs text-zinc-400 hover:text-zinc-100"
          aria-label={t("boundary.copyAria", { id: errorId })}
        >
          {copied ? t("boundary.copied") : `#${errorId}`}
        </button>
      </div>
    </div>
  );
}
