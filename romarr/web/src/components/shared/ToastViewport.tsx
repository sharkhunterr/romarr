/**
 * Toast viewport (slice 73).
 *
 * Mounted once from AppLayout. Renders the live toast queue
 * fixed to the bottom-right on md+ and to the top of the
 * viewport on mobile (so the BottomNav doesn't cover them).
 *
 * Each toast auto-dismisses after its `durationMs` unless
 * the durationMs is 0 (sticky). Hovering a toast pauses its
 * timer — the documented behavior for shadcn/ui's Toast
 * primitive.
 */

import {
  useEffect,
  useRef,
  type ReactElement,
} from "react";
import { useTranslation } from "react-i18next";

import {
  useToastStore,
  type Toast,
  type ToastKind,
} from "@/lib/store/toast";

const KIND_BORDER: Record<ToastKind, string> = {
  info: "border-zinc-700",
  success: "border-emerald-700/60",
  warning: "border-amber-700/60",
  error: "border-red-700/60",
};

const KIND_DOT: Record<ToastKind, string> = {
  info: "bg-zinc-500",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  error: "bg-red-400",
};

interface ToastNodeProps {
  toast: Toast;
}

function ToastNode(props: ToastNodeProps): ReactElement {
  const { t } = useTranslation("common");
  const { toast } = props;
  const dismiss = useToastStore((s) => s.dismiss);
  const timerRef = useRef<number | null>(null);
  const pausedRef = useRef(false);

  useEffect(() => {
    if (toast.durationMs <= 0) return;
    function arm(): void {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(() => {
        if (!pausedRef.current) dismiss(toast.id);
      }, toast.durationMs);
    }
    arm();
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [toast.id, toast.durationMs, dismiss]);

  function onMouseEnter(): void {
    pausedRef.current = true;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  function onMouseLeave(): void {
    pausedRef.current = false;
    if (toast.durationMs > 0) {
      timerRef.current = window.setTimeout(
        () => dismiss(toast.id),
        toast.durationMs,
      );
    }
  }

  return (
    <li
      role="status"
      aria-live="polite"
      aria-atomic="true"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={[
        "pointer-events-auto flex items-start gap-2 rounded-md border bg-zinc-900",
        "px-3 py-2 shadow-lg",
        KIND_BORDER[toast.kind],
      ].join(" ")}
    >
      <span
        aria-label={t(`toast.kindAria.${toast.kind}`)}
        className={[
          "mt-1 inline-block h-2 w-2 shrink-0 rounded-full",
          KIND_DOT[toast.kind],
        ].join(" ")}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-100">
          {toast.title}
        </p>
        {toast.description && (
          <p className="mt-0.5 text-xs text-zinc-400">
            {toast.description}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => dismiss(toast.id)}
        aria-label={t("toast.dismiss")}
        title={t("toast.dismiss")}
        className={[
          "shrink-0 rounded-md px-1 text-zinc-500 hover:text-zinc-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        ].join(" ")}
      >
        <span aria-hidden="true">×</span>
      </button>
    </li>
  );
}

export function ToastViewport(): ReactElement {
  const { t } = useTranslation("common");
  const toasts = useToastStore((s) => s.toasts);

  return (
    <ol
      aria-label={t("toast.viewportLabel")}
      className={[
        "pointer-events-none fixed z-50 flex w-full flex-col gap-2",
        "p-3 sm:max-w-sm",
        // Mobile: top-center so the BottomNav doesn't cover.
        "top-[env(safe-area-inset-top)] left-0 right-0 mx-auto",
        // Desktop: bottom-right.
        "md:bottom-3 md:left-auto md:right-3 md:top-auto",
      ].join(" ")}
    >
      {toasts.map((toast) => (
        <ToastNode key={toast.id} toast={toast} />
      ))}
    </ol>
  );
}
