/**
 * Preferences hydration + persistence (CL008 + FR-013b).
 *
 * Two operator-facing display preferences live both in the
 * authenticated User row (server-side, source of truth across
 * devices) and in localStorage (so the no-flash inline script
 * can set ``<html class="dark">`` before React hydrates):
 *
 *   * ``theme``    — dark / light / auto (``romarr.theme``)
 *   * ``language`` — en / fr            (``romarr.lang``)
 *
 * The documented hydration order:
 *
 *   1. Render the app with the localStorage values (no FOUC).
 *   2. ``GET /api/v3/auth/me`` resolves; the server's
 *      ``user.preferences`` block becomes authoritative.
 *   3. The server values overwrite the local stores and
 *      ``i18next.changeLanguage`` runs, so the second render
 *      reflects the cross-device-synced state.
 *
 * Update path:
 *
 *   * ``PATCH /api/v3/auth/me`` with the new preferences.
 *   * Optimistic UI: the theme / language store is updated
 *     before the request fires.
 *   * On failure the previous values are restored and the
 *     query cache is invalidated so the AuthGuard re-reads.
 */

import { useEffect } from "react";
import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/lib/api/client";
import {
  AUTH_ME_QUERY_KEY,
  useCurrentPrincipal,
  type CurrentPrincipal,
} from "@/lib/api/queries/auth";
import {
  setLanguage,
  SUPPORTED_LANGUAGES,
  type Language,
} from "@/lib/i18n";
import { useThemeStore, type Theme } from "@/lib/store/theme";

const THEME_VALUES = new Set<Theme>(["dark", "light", "auto"]);
const LANGUAGE_VALUES = new Set<Language>([...SUPPORTED_LANGUAGES]);

export interface ServerPreferences {
  theme?: Theme;
  language?: Language;
}

/**
 * Read the typed preferences subset out of the principal's
 * ``preferences`` blob. Unknown keys are ignored; values that
 * don't match the documented enum are dropped (server is
 * authoritative but the client-side enums are still the source
 * of truth for what's renderable).
 */
export function readServerPreferences(
  principal: CurrentPrincipal | undefined,
): ServerPreferences {
  if (!principal || !principal.preferences) {
    return {};
  }
  const raw = principal.preferences as Record<string, unknown>;
  const out: ServerPreferences = {};
  if (typeof raw.theme === "string" && THEME_VALUES.has(raw.theme as Theme)) {
    out.theme = raw.theme as Theme;
  }
  if (
    typeof raw.language === "string" &&
    LANGUAGE_VALUES.has(raw.language as Language)
  ) {
    out.language = raw.language as Language;
  }
  return out;
}

/**
 * Mount-time hydration: when the principal lands, overwrite the
 * local theme + language stores with the server values. This
 * runs in an effect (not at module load) so SSR / test harnesses
 * that mount the hook without a logged-in user are no-ops.
 */
export function usePreferencesHydration(): void {
  const { data } = useCurrentPrincipal();
  useEffect(() => {
    const prefs = readServerPreferences(data);
    if (prefs.theme !== undefined) {
      useThemeStore.getState().setTheme(prefs.theme);
    }
    if (prefs.language !== undefined) {
      void setLanguage(prefs.language);
    }
  }, [data]);
}

export interface UpdatePreferencesVariables {
  theme?: Theme;
  language?: Language;
}

interface RollbackContext {
  previousTheme: Theme;
  previousLanguage: string | undefined;
}

/**
 * PATCH /api/v3/auth/me with the new preferences. Optimistic
 * update: the theme / language store is changed before the
 * request fires; on failure the previous values are restored.
 */
export function useUpdatePreferences(): UseMutationResult<
  CurrentPrincipal,
  ApiError,
  UpdatePreferencesVariables,
  RollbackContext
> {
  const qc = useQueryClient();
  return useMutation<
    CurrentPrincipal,
    ApiError,
    UpdatePreferencesVariables,
    RollbackContext
  >({
    mutationFn: async (vars) => {
      const merged = await apiFetch<CurrentPrincipal>("/api/v3/auth/me", {
        method: "PATCH",
        json: { preferences: { ...vars } },
      });
      return merged;
    },
    onMutate: (vars): RollbackContext => {
      const ctx: RollbackContext = {
        previousTheme: useThemeStore.getState().theme,
        previousLanguage:
          typeof window !== "undefined"
            ? (window.localStorage.getItem("romarr.lang") ?? undefined)
            : undefined,
      };
      if (vars.theme !== undefined) {
        useThemeStore.getState().setTheme(vars.theme);
      }
      if (vars.language !== undefined) {
        void setLanguage(vars.language);
      }
      return ctx;
    },
    onError: (_error, _vars, context) => {
      if (context === undefined) {
        return;
      }
      useThemeStore.getState().setTheme(context.previousTheme);
      if (context.previousLanguage !== undefined) {
        void setLanguage(context.previousLanguage as Language);
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
    },
  });
}
