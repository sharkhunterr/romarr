/**
 * GameDetail > Overview tab (slices 89, 146, 147, 148).
 *
 * Metadata view: cover (CoverImage with gradient fallback),
 * title, summary, key facts. Each FactRow with a known
 * :data:`ProviderField` carries a lock toggle — locking a
 * field tells the aggregator to skip it on every refresh.
 * Text-shaped FactRows (developer / publisher / age_rating)
 * are also click-to-edit, alongside the title heading and the
 * summary paragraph; saving auto-locks the field so the
 * operator's edit survives the next refresh. Together these
 * are the constitutional anti-RomM-#1770 mechanism.
 */

import { useEffect, useRef, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { CoverImage } from "@/components/rom";
import { CoverEditModal } from "./CoverEditModal";
import {
  useEditGameField,
  useRefreshGameMetadata,
  useToggleFieldLock,
  useToggleGameMonitor,
  type EditableTextField,
  type Game,
  type ProviderField,
} from "@/lib/api/queries/games";
import { usePlatformsById } from "@/lib/api/queries/platforms";
import { useTagsById } from "@/lib/api/queries/tags";
import { useToastStore } from "@/lib/store/toast";

interface OverviewTabProps {
  game: Game;
}

interface FactRowProps {
  label: string;
  value: string | null | undefined;
  field?: ProviderField;
  lockedFields: readonly string[];
  gameId: number;
}

function FieldLockButton(props: {
  field: ProviderField;
  locked: boolean;
  gameId: number;
}): ReactElement {
  const { t } = useTranslation("game");
  const toggle = useToggleFieldLock();
  const onClick = (): void => {
    toggle.mutate({
      gameId: props.gameId,
      field: props.field,
      locked: !props.locked,
    });
  };
  const ariaLabel = props.locked
    ? t("overview.lock.unlockAria", { field: props.field })
    : t("overview.lock.lockAria", { field: props.field });
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={toggle.isPending}
      aria-pressed={props.locked}
      aria-label={ariaLabel}
      title={ariaLabel}
      className={[
        "shrink-0 rounded p-0.5 text-[0.7rem] leading-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        props.locked
          ? "text-amber-400 hover:text-amber-300"
          : "text-zinc-600 hover:text-zinc-400",
      ].join(" ")}
    >
      <span aria-hidden="true">{props.locked ? "🔒" : "🔓"}</span>
    </button>
  );
}

function FactRow(props: FactRowProps): ReactElement {
  const locked =
    props.field !== undefined && props.lockedFields.includes(props.field);
  return (
    <div className="grid grid-cols-2 gap-3 border-b border-zinc-800 py-2 last:border-b-0">
      <dt className="flex items-center gap-1.5 text-[0.65rem] uppercase tracking-wider text-zinc-500">
        <span>{props.label}</span>
        {props.field !== undefined && (
          <FieldLockButton
            field={props.field}
            locked={locked}
            gameId={props.gameId}
          />
        )}
      </dt>
      <dd className="text-xs text-zinc-200">{props.value ?? "—"}</dd>
    </div>
  );
}

interface EditableFactRowProps {
  label: string;
  field: EditableTextField;
  rawValue: string | null;
  lockedFields: readonly string[];
  gameId: number;
}

function EditableFactRow(props: EditableFactRowProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const edit = useEditGameField();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(props.rawValue ?? "");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const locked = props.lockedFields.includes(props.field);

  useEffect(() => {
    if (isEditing) {
      setDraft(props.rawValue ?? "");
      // Defer focus until after the input mounts.
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [isEditing, props.rawValue]);

  function commit(): void {
    const trimmed = draft.trim();
    const next = trimmed.length === 0 ? null : trimmed;
    if (next === (props.rawValue ?? null)) {
      setIsEditing(false);
      return;
    }
    edit.mutate(
      {
        gameId: props.gameId,
        field: props.field,
        value: next,
      },
      {
        onSuccess: () => setIsEditing(false),
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("overview.edit.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  function cancel(): void {
    setIsEditing(false);
    setDraft(props.rawValue ?? "");
  }

  return (
    <div className="grid grid-cols-2 gap-3 border-b border-zinc-800 py-2 last:border-b-0">
      <dt className="flex items-center gap-1.5 text-[0.65rem] uppercase tracking-wider text-zinc-500">
        <span>{props.label}</span>
        <FieldLockButton
          field={props.field}
          locked={locked}
          gameId={props.gameId}
        />
      </dt>
      {isEditing ? (
        <dd className="flex items-center gap-1.5">
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") cancel();
            }}
            disabled={edit.isPending}
            aria-label={t("overview.edit.inputAria", { field: props.label })}
            className="min-w-0 flex-1 rounded-md bg-zinc-950 px-2 py-1 text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          />
          <button
            type="button"
            onClick={commit}
            disabled={edit.isPending}
            aria-label={t("overview.edit.save")}
            className="rounded p-1 text-emerald-400 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
          >
            <span aria-hidden="true">✓</span>
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={edit.isPending}
            aria-label={t("overview.edit.cancel")}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </dd>
      ) : (
        <dd className="group flex items-center gap-1.5 text-xs text-zinc-200">
          <span className="min-w-0 flex-1 truncate">
            {props.rawValue ?? "—"}
          </span>
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            aria-label={t("overview.edit.openAria", { field: props.label })}
            className="rounded p-0.5 text-zinc-600 opacity-0 transition-opacity hover:text-zinc-300 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <span aria-hidden="true">✎</span>
          </button>
        </dd>
      )}
    </div>
  );
}

function formatPlayers(
  game: Game,
  t: (k: string, opts?: Record<string, unknown>) => string,
): string | null {
  const min = game.players_min ?? null;
  const max = game.players_max ?? null;
  if (min === null && max === null) return null;
  if (min !== null && max !== null && min !== max) {
    return t("overview.playersRange", { min, max });
  }
  return t("overview.playersSolo", { count: max ?? min });
}

function formatReleaseDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function formatList(items: readonly string[] | undefined): string | null {
  if (!items || items.length === 0) return null;
  return items.join(", ");
}

interface EditableHeadingProps {
  game: Game;
}

/**
 * Click-to-edit heading for the Game's title.
 *
 * Single-line input shaped like the surrounding ``<h2>``. The
 * backend rejects clearing the title (NOT NULL); we mirror that
 * by ignoring an empty submit. Auto-locks on save.
 */
function EditableTitle(props: EditableHeadingProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const edit = useEditGameField();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(props.game.title);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const locked = (props.game.locked_fields ?? []).includes("title");

  useEffect(() => {
    if (isEditing) {
      setDraft(props.game.title);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [isEditing, props.game.title]);

  function commit(): void {
    const trimmed = draft.trim();
    if (trimmed.length === 0) {
      // Title is NOT NULL — silently treat empty as cancel.
      setIsEditing(false);
      return;
    }
    if (trimmed === props.game.title) {
      setIsEditing(false);
      return;
    }
    edit.mutate(
      { gameId: props.game.id, field: "title", value: trimmed },
      {
        onSuccess: () => setIsEditing(false),
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("overview.edit.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  if (isEditing) {
    return (
      <div className="flex flex-wrap items-start gap-1.5">
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setIsEditing(false);
          }}
          disabled={edit.isPending}
          aria-label={t("overview.edit.titleAria")}
          className="min-w-0 flex-1 rounded-md bg-zinc-950 px-2 py-1 text-lg font-semibold text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        />
        <button
          type="button"
          onClick={commit}
          disabled={edit.isPending}
          aria-label={t("overview.edit.save")}
          className="rounded p-1 text-emerald-400 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
        >
          <span aria-hidden="true">✓</span>
        </button>
        <button
          type="button"
          onClick={() => setIsEditing(false)}
          disabled={edit.isPending}
          aria-label={t("overview.edit.cancel")}
          className="rounded p-1 text-zinc-400 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-1.5">
      <h2 className="min-w-0 flex-1 text-lg font-semibold text-zinc-100">
        {props.game.title}
      </h2>
      {locked && (
        <span
          aria-hidden="true"
          title={t("overview.lock.lockedHint")}
          className="text-amber-400"
        >
          🔒
        </span>
      )}
      <button
        type="button"
        onClick={() => setIsEditing(true)}
        aria-label={t("overview.edit.openAria", { field: t("overview.fields.title") })}
        className="rounded p-0.5 text-zinc-600 opacity-0 transition-opacity hover:text-zinc-300 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span aria-hidden="true">✎</span>
      </button>
    </div>
  );
}

/**
 * Click-to-edit summary paragraph.
 *
 * Multiline ``<textarea>`` swap. The empty case shows the
 * placeholder summary string but the operator can still click
 * to start writing one. Auto-locks on save; clearing wipes the
 * field but keeps the lock so the aggregator stops trying.
 */
function EditableSummary(props: EditableHeadingProps): ReactElement {
  const { t } = useTranslation("game");
  const pushToast = useToastStore((s) => s.push);
  const edit = useEditGameField();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(props.game.summary ?? "");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const locked = (props.game.locked_fields ?? []).includes("summary");

  useEffect(() => {
    if (isEditing) {
      setDraft(props.game.summary ?? "");
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [isEditing, props.game.summary]);

  function commit(): void {
    const trimmed = draft.trim();
    const next = trimmed.length === 0 ? null : trimmed;
    if (next === (props.game.summary ?? null)) {
      setIsEditing(false);
      return;
    }
    edit.mutate(
      { gameId: props.game.id, field: "summary", value: next },
      {
        onSuccess: () => setIsEditing(false),
        onError: (err) => {
          pushToast({
            kind: "error",
            title: t("overview.edit.errorTitle"),
            description: err.message,
          });
        },
      },
    );
  }

  if (isEditing) {
    return (
      <div className="mt-2 space-y-1.5">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Cmd/Ctrl+Enter submits — plain Enter inserts a
            // newline so multi-paragraph summaries work.
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) commit();
            if (e.key === "Escape") setIsEditing(false);
          }}
          disabled={edit.isPending}
          rows={4}
          aria-label={t("overview.edit.summaryAria")}
          className="w-full rounded-md bg-zinc-950 px-2 py-1.5 text-sm text-zinc-200 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        />
        <div className="flex items-center justify-between gap-2">
          <p className="text-[0.6rem] text-zinc-500">
            {t("overview.edit.summaryHint")}
          </p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              disabled={edit.isPending}
              className="rounded-md border border-zinc-700 px-2 py-1 text-[0.65rem] font-medium text-zinc-200 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
            >
              {t("overview.edit.cancel")}
            </button>
            <button
              type="button"
              onClick={commit}
              disabled={edit.isPending}
              className="rounded-md bg-brand px-2 py-1 text-[0.65rem] font-medium text-zinc-900 hover:bg-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
            >
              {edit.isPending ? t("overview.edit.saving") : t("overview.edit.save")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const hasSummary =
    props.game.summary !== undefined &&
    props.game.summary !== null &&
    props.game.summary.trim().length > 0;

  return (
    <div className="group mt-2 flex items-start gap-1.5">
      <p
        className={[
          "min-w-0 flex-1 whitespace-pre-line text-sm",
          hasSummary ? "text-zinc-400" : "text-zinc-600 italic",
        ].join(" ")}
      >
        {hasSummary ? props.game.summary : t("overview.noSummary")}
      </p>
      {locked && (
        <span
          aria-hidden="true"
          title={t("overview.lock.lockedHint")}
          className="shrink-0 text-amber-400"
        >
          🔒
        </span>
      )}
      <button
        type="button"
        onClick={() => setIsEditing(true)}
        aria-label={t("overview.edit.openAria", {
          field: t("overview.fields.summary"),
        })}
        className="shrink-0 rounded p-0.5 text-zinc-600 opacity-0 transition-opacity hover:text-zinc-300 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span aria-hidden="true">✎</span>
      </button>
    </div>
  );
}

function RefreshMetadataButton(props: { game: Game }): ReactElement {
  const { t } = useTranslation("game");
  const { game } = props;
  const refresh = useRefreshGameMetadata();
  const onClick = (): void => {
    refresh.mutate({ gameId: game.id });
  };
  const label = refresh.isPending
    ? t("overview.refresh.pending")
    : refresh.isSuccess
      ? t("overview.refresh.success", {
          changed: Object.keys(refresh.data.fields).length,
          skipped: refresh.data.skipped_locked.length,
        })
      : t("overview.refresh.idle");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={refresh.isPending}
      className={[
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5",
        "text-xs font-medium ring-1 ring-inset",
        "bg-zinc-800 text-zinc-200 ring-zinc-700",
        "transition-colors hover:bg-zinc-700",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
      ].join(" ")}
      title={
        refresh.isError && refresh.error?.message
          ? refresh.error.message
          : undefined
      }
    >
      <span aria-hidden="true">{refresh.isPending ? "⏳" : "🔄"}</span>
      <span>{label}</span>
    </button>
  );
}

function MonitorToggle(props: { game: Game }): ReactElement {
  const { t } = useTranslation("game");
  const { game } = props;
  const toggle = useToggleGameMonitor();
  const onClick = (): void => {
    toggle.mutate({ gameId: game.id, monitored: !game.monitored });
  };
  const tone = game.monitored
    ? "bg-emerald-700/30 text-emerald-200 ring-emerald-500/40"
    : "bg-zinc-800 text-zinc-400 ring-zinc-700";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={toggle.isPending}
      aria-pressed={game.monitored}
      className={[
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5",
        "text-xs font-medium ring-1 ring-inset",
        "transition-colors hover:brightness-110",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        tone,
      ].join(" ")}
      title={
        toggle.isError && toggle.error?.message
          ? toggle.error.message
          : undefined
      }
    >
      <span aria-hidden="true">{game.monitored ? "👁️" : "💤"}</span>
      <span>
        {game.monitored
          ? t("overview.monitor.on")
          : t("overview.monitor.off")}
      </span>
    </button>
  );
}

export function OverviewTab(props: OverviewTabProps): ReactElement {
  const { t } = useTranslation("game");
  const { game } = props;
  const byId = usePlatformsById();
  const platform = byId.get(game.platform_id);
  const platformLabel = platform
    ? platform.name
    : `#${game.platform_id}`;
  const tagsById = useTagsById();
  const tagPills = (game.tags ?? [])
    .map((id) => tagsById.get(id))
    .filter((tag): tag is NonNullable<typeof tag> => tag !== undefined);

  const [coverEditOpen, setCoverEditOpen] = useState(false);
  const coverLocked = (game.locked_fields ?? []).includes("cover");

  return (
    <div className="grid gap-4 md:grid-cols-[10rem_minmax(0,1fr)]">
      <div className="md:sticky md:top-20 md:self-start">
        <button
          type="button"
          onClick={() => setCoverEditOpen(true)}
          aria-label={t("overview.cover.changeAria")}
          className="group relative block w-full rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <CoverImage
            gameId={game.id}
            src={game.cover_path ?? null}
            cacheKey={game.updated_at ?? null}
            alt={game.title}
            sizeClassName="aspect-[3/4] w-full md:w-40"
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center rounded-b bg-zinc-950/70 py-1 text-[0.65rem] text-zinc-300 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            ✎ {t("overview.cover.changeShort")}
          </span>
          {coverLocked && (
            <span
              aria-hidden="true"
              title={t("overview.lock.lockedHint")}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-zinc-950/80 text-[0.7rem] text-amber-400 ring-1 ring-inset ring-zinc-700 backdrop-blur-sm"
            >
              🔒
            </span>
          )}
        </button>
      </div>

      {coverEditOpen && (
        <CoverEditModal
          game={game}
          onClose={() => setCoverEditOpen(false)}
        />
      )}

      <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <EditableTitle game={game} />
            <EditableSummary game={game} />
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <RefreshMetadataButton game={game} />
            <MonitorToggle game={game} />
          </div>
        </div>

        <dl className="rounded-md border border-zinc-800 bg-zinc-900/40 px-4">
          <EditableFactRow
            label={t("overview.fields.developer")}
            field="developer"
            rawValue={game.developer ?? null}
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <EditableFactRow
            label={t("overview.fields.publisher")}
            field="publisher"
            rawValue={game.publisher ?? null}
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.releaseDate")}
            value={formatReleaseDate(game.release_date)}
            field="release_date"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.platform")}
            value={platformLabel}
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.rating")}
            value={
              game.rating !== null && game.rating !== undefined
                ? game.rating.toFixed(1)
                : null
            }
            field="rating"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <EditableFactRow
            label={t("overview.fields.ageRating")}
            field="age_rating"
            rawValue={game.age_rating ?? null}
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.players")}
            value={formatPlayers(game, t)}
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.hltb")}
            value={
              game.hltb_main !== null && game.hltb_main !== undefined
                ? t("overview.hltbHours", { hours: game.hltb_main })
                : null
            }
            field="hltb_main"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.achievements")}
            value={
              game.achievements_count !== null &&
              game.achievements_count !== undefined
                ? String(game.achievements_count)
                : null
            }
            field="achievements_count"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.genres")}
            value={formatList(game.genres)}
            field="genres"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.themes")}
            value={formatList(game.themes)}
            field="themes"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
          <FactRow
            label={t("overview.fields.franchises")}
            value={formatList(game.franchises)}
            field="franchises"
            lockedFields={game.locked_fields ?? []}
            gameId={game.id}
          />
        </dl>

        {tagPills.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
              {t("overview.tags.label")}
            </h3>
            <ul className="flex flex-wrap gap-1.5">
              {tagPills.map((tag) => (
                <li key={tag.id}>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.65rem] font-medium ring-1 ring-inset ring-zinc-700"
                    style={{
                      backgroundColor: `${tag.color}20`,
                      color: tag.color,
                    }}
                  >
                    <span
                      aria-hidden="true"
                      className="block h-2 w-2 rounded-full ring-1 ring-zinc-950/40"
                      style={{ backgroundColor: tag.color }}
                    />
                    {tag.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
