/**
 * Test rendering helper (slice 211).
 *
 * Wraps the operator-facing components in the providers they
 * actually consume in production: the i18next instance, the
 * React Router context, and the TanStack Query client. Page
 * tests under ``src/pages/**`` all use this helper so the
 * provider plumbing stays consistent across the suite.
 *
 * The i18next instance here is intentionally minimal — no
 * HTTP backend, no language detection — because tests want
 * deterministic key resolution. Keys without a registered
 * translation resolve to themselves via the
 * ``returnEmptyString: false`` + ``parseMissingKeyHandler``
 * shape, which matches what the running SPA would do for an
 * unrecognised key.
 */

import { type ReactElement, type ReactNode, type ComponentType } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// One-shot init so the i18next module is configured even
// when a test imports the helper but never calls
// ``renderWithProviders``.
if (!i18n.isInitialized) {
  void i18n.use(initReactI18next).init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: {}, fr: {} },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    parseMissingKeyHandler: (key: string) => key,
  });
}

export interface ProviderOptions {
  /** Initial entries for the in-memory router. */
  routerEntries?: string[];
  /** Lazy-attach test resources to a namespace. */
  i18nResources?: Record<string, Record<string, unknown>>;
  /** Test-time language override. */
  language?: "en" | "fr";
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: { retry: false },
    },
  });
}

export function buildTestProviders(
  options: ProviderOptions = {},
): ComponentType<{ children: ReactNode }> {
  const { routerEntries = ["/"], i18nResources, language } = options;

  if (i18nResources) {
    for (const [ns, bundle] of Object.entries(i18nResources)) {
      i18n.addResourceBundle("en", ns, bundle, true, true);
    }
  }
  if (language) {
    void i18n.changeLanguage(language);
  }

  const queryClient = makeQueryClient();

  function Wrapper(props: { children: ReactNode }): ReactElement {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={routerEntries}>
            {props.children}
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>
    );
  }

  return Wrapper;
}

export function renderWithProviders(
  ui: ReactElement,
  options: ProviderOptions & Omit<RenderOptions, "wrapper"> = {},
): ReturnType<typeof render> {
  const { routerEntries, i18nResources, language, ...renderOptions } = options;
  return render(ui, {
    wrapper: buildTestProviders({
      routerEntries,
      i18nResources,
      language,
    }),
    ...renderOptions,
  });
}
