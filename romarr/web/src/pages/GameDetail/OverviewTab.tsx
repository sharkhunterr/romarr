/**
 * GameDetail > Overview tab (slice 89).
 *
 * Read-only metadata view: cover (CoverImage with gradient
 * fallback), title, summary, key facts. Edit-in-place per
 * field with the lock toggle (per the spec) lands in a
 * follow-up slice once the field-locking surface is wired.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { CoverImage } from "@/components/rom";
import type { Game } from "@/lib/api/queries/games";

interface OverviewTabProps {
  game: Game;
}

interface FactRowProps {
  label: string;
  value: string | null | undefined;
}

function FactRow(props: FactRowProps): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-3 border-b border-zinc-800 py-2 last:border-b-0">
      <dt className="text-[0.65rem] uppercase tracking-wider text-zinc-500">
        {props.label}
      </dt>
      <dd className="text-xs text-zinc-200">{props.value ?? "—"}</dd>
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

export function OverviewTab(props: OverviewTabProps): ReactElement {
  const { t } = useTranslation("game");
  const { game } = props;

  return (
    <div className="grid gap-4 md:grid-cols-[10rem_minmax(0,1fr)]">
      <div className="md:sticky md:top-20 md:self-start">
        <CoverImage
          src={game.cover_path ?? null}
          alt={game.title}
          sizeClassName="aspect-[3/4] w-full md:w-40"
        />
      </div>

      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            {game.title}
          </h2>
          <p className="mt-2 text-sm text-zinc-400">
            {game.summary && game.summary.trim().length > 0
              ? game.summary
              : t("overview.noSummary")}
          </p>
        </div>

        <dl className="rounded-md border border-zinc-800 bg-zinc-900/40 px-4">
          <FactRow
            label={t("overview.fields.developer")}
            value={game.developer ?? null}
          />
          <FactRow
            label={t("overview.fields.publisher")}
            value={game.publisher ?? null}
          />
          <FactRow
            label={t("overview.fields.releaseDate")}
            value={formatReleaseDate(game.release_date)}
          />
          <FactRow
            label={t("overview.fields.platform")}
            value={`#${game.platform_id}`}
          />
          <FactRow
            label={t("overview.fields.rating")}
            value={
              game.rating !== null && game.rating !== undefined
                ? game.rating.toFixed(1)
                : null
            }
          />
          <FactRow
            label={t("overview.fields.ageRating")}
            value={game.age_rating ?? null}
          />
          <FactRow
            label={t("overview.fields.players")}
            value={formatPlayers(game, t)}
          />
          <FactRow
            label={t("overview.fields.hltb")}
            value={
              game.hltb_main !== null && game.hltb_main !== undefined
                ? t("overview.hltbHours", { hours: game.hltb_main })
                : null
            }
          />
          <FactRow
            label={t("overview.fields.achievements")}
            value={
              game.achievements_count !== null &&
              game.achievements_count !== undefined
                ? String(game.achievements_count)
                : null
            }
          />
          <FactRow
            label={t("overview.fields.genres")}
            value={formatList(game.genres)}
          />
          <FactRow
            label={t("overview.fields.themes")}
            value={formatList(game.themes)}
          />
          <FactRow
            label={t("overview.fields.franchises")}
            value={formatList(game.franchises)}
          />
          <FactRow
            label={t("overview.fields.monitored")}
            value={game.monitored ? t("overview.yes") : t("overview.no")}
          />
        </dl>
      </div>
    </div>
  );
}
