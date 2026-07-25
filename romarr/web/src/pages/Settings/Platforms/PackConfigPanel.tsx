/**
 * Panneau config platform-packs — toggle builtin + priorité.
 *
 * Placé en TÊTE de la page Platforms (avant les sources, avant la
 * liste des plateformes) : ce sont les paramètres globaux qui
 * dictent le comportement de tout le reste.
 */

import { type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch, ApiError } from "@/lib/api/client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface PackConfig {
  builtin_enabled: boolean;
  priority: "builtin" | "community";
}

const QK = ["platform-pack-config"] as const;
const API = "/api/v3/rom/platform-pack-config";

export function PackConfigPanel(): ReactElement {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();

  const cfg = useQuery<PackConfig, ApiError>({
    queryKey: QK,
    queryFn: () => apiFetch<PackConfig>(API),
  });

  const patch = useMutation({
    mutationFn: (body: Partial<PackConfig>) =>
      apiFetch<PackConfig>(API, { method: "PATCH", json: body }),
    onSuccess: (data) => qc.setQueryData(QK, data),
  });

  const data = cfg.data;

  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
      <header className="mb-3">
        <h3 className="text-sm font-medium text-zinc-100">
          {t("platforms.config.heading", "Pack configuration")}
        </h3>
        <p className="text-[0.65rem] text-zinc-500">
          {t(
            "platforms.config.subhead",
            "Toggle the built-in pack + decide which side wins for slugs present in both builtin and community sources.",
          )}
        </p>
      </header>

      {cfg.isPending && (
        <p className="text-xs text-zinc-500">
          {t("platforms.config.loading", "Loading…")}
        </p>
      )}
      {cfg.isError && (
        <p role="alert" className="text-xs text-red-300">
          {cfg.error.message}
        </p>
      )}

      {data && (
        <div className="space-y-3">
          {/* Toggle builtin */}
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={data.builtin_enabled}
              disabled={patch.isPending}
              onChange={(e) =>
                patch.mutate({ builtin_enabled: e.target.checked })
              }
              className="mt-0.5 h-4 w-4 accent-brand"
            />
            <span className="flex-1">
              <span className="block text-sm font-medium text-zinc-100">
                {t("platforms.config.builtinEnabled", "Enable built-in pack")}
              </span>
              <span className="mt-0.5 block text-[0.7rem] text-zinc-500">
                {t(
                  "platforms.config.builtinEnabledHint",
                  "Auto-applies the wheel-bundled builtin pack at boot. Disable if you want a community-only setup — takes effect on next restart.",
                )}
              </span>
            </span>
          </label>

          {/* Priority radio */}
          <fieldset
            disabled={!data.builtin_enabled || patch.isPending}
            className="pl-7"
          >
            <legend className="mb-1.5 text-[0.65rem] font-medium uppercase tracking-widest text-zinc-500">
              {t("platforms.config.priorityLabel", "Priority when slugs overlap")}
            </legend>
            <div className="flex flex-col gap-1.5 sm:flex-row sm:gap-4">
              {(
                [
                  {
                    key: "community",
                    label: t(
                      "platforms.config.priorityCommunity",
                      "Community wins",
                    ),
                    hint: t(
                      "platforms.config.priorityCommunityHint",
                      "Community packs applied after builtin — their values overwrite for shared slugs (default).",
                    ),
                  },
                  {
                    key: "builtin",
                    label: t(
                      "platforms.config.priorityBuiltin",
                      "Built-in wins",
                    ),
                    hint: t(
                      "platforms.config.priorityBuiltinHint",
                      "After every community sync, re-applies the builtin pack so its values overwrite the community's for shared slugs.",
                    ),
                  },
                ] as const
              ).map((opt) => (
                <label
                  key={opt.key}
                  className="flex cursor-pointer items-start gap-2 rounded p-1 hover:bg-zinc-800/40"
                  title={opt.hint}
                >
                  <input
                    type="radio"
                    name="pack-priority"
                    checked={data.priority === opt.key}
                    onChange={() => patch.mutate({ priority: opt.key })}
                    className="mt-0.5 h-3.5 w-3.5 accent-brand"
                  />
                  <span className="text-sm text-zinc-100">{opt.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {patch.isError && (
            <p role="alert" className="text-xs text-red-300">
              {(patch.error as Error).message}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
