/**
 * GameDetail > Notes tab (slice 149).
 *
 * Operator-owned free-text notes — distinct from the
 * provider-owned ``summary``. Single big textarea, two
 * controls (Save / Cancel). Cmd/Ctrl+Enter saves, Esc reverts
 * to the persisted value. The form is intentionally implicit
 * about its dirty state: the Save button activates the moment
 * the draft diverges from the persisted notes.
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { useSetGameNotes, type Game } from "@/lib/api/queries/games";
import { useToastStore } from "@/lib/store/toast";

interface NotesTabProps {
  game: Game;
}

export function NotesTab(props: NotesTabProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const setNotes = useSetGameNotes();

  const persisted = props.game.notes ?? "";
  const [draft, setDraft] = useState(persisted);

  // When the underlying game refetches (e.g., after save) the
  // persisted notes change; re-sync the draft so we don't keep
  // showing a stale "dirty" state.
  useEffect(() => {
    setDraft(persisted);
  }, [persisted]);

  const dirty = draft !== persisted;

  function commit(): void {
    const trimmed = draft.trim();
    const next: string | null = trimmed.length === 0 ? null : trimmed;
    if (next === (props.game.notes ?? null)) return;
    setNotes.mutate(
      { gameId: props.game.id, notes: next },
      {
        onSuccess: () => {
          pushToast({
            kind: "success",
            title: t("notes.successTitle"),
            description: t("notes.successBody"),
          });
        },
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("notes.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  function revert(): void {
    setDraft(persisted);
  }

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-sm font-semibold text-zinc-100">
          {t("notes.heading")}
        </h2>
        <p className="text-[0.7rem] text-zinc-500">{t("notes.subhead")}</p>
      </header>

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            commit();
          }
          if (e.key === "Escape") {
            e.preventDefault();
            revert();
          }
        }}
        disabled={setNotes.isPending}
        rows={12}
        aria-label={t("notes.textareaAria")}
        placeholder={t("notes.placeholder")}
        className="w-full rounded-md bg-zinc-950 px-3 py-2 text-sm text-zinc-200 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      />

      <footer className="flex items-center justify-between gap-2">
        <p className="text-[0.6rem] text-zinc-500">
          {t("notes.hint")}
        </p>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={revert}
            disabled={!dirty || setNotes.isPending}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t("notes.revert")}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!dirty || setNotes.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {setNotes.isPending ? t("notes.saving") : t("notes.save")}
          </button>
        </div>
      </footer>
    </section>
  );
}
