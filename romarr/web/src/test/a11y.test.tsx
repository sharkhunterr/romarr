/**
 * Accessibility regression tests (T121, FR-037, SC-007).
 *
 * Runs ``axe-core`` against every component the operator
 * touches on the critical paths. We can't render the full
 * authenticated app tree under jsdom (the AuthGuard probes
 * ``/auth/me`` and would 401), so we exercise the
 * subcomponents directly with realistic props.
 *
 * The Playwright-driven full-page a11y suite (Dashboard /
 * Library / GameDetail / Settings end-to-end) lands with
 * the spec-014 E2E gate (T124-T128). This vitest suite is
 * the regression net for the fast feedback loop.
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";

import { renderWithProviders } from "@/test/render";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorFallback } from "@/components/shared/ErrorFallback";
import { RegionBadge } from "@/components/rom/RegionBadge";
import { ConventionBadge } from "@/components/rom/ConventionBadge";
import { DumpStatusIcon } from "@/components/rom/DumpStatusIcon";
import { ScoreBadge } from "@/components/rom/ScoreBadge";

// jsdom doesn't ship a real layout engine: ``color-contrast``
// reads computed colors via Canvas / getBoundingClientRect and
// blows up under jsdom. We disable the rule here; the
// Playwright-driven a11y suite (T124-T128) re-enables it
// against a real browser. The structural rules (label,
// landmark, aria-*) are what catch regressions in this fast
// feedback loop.
const _AXE_OPTIONS = {
  rules: {
    "color-contrast": { enabled: false },
  },
};

const I18N_BUNDLE = {
  errors: {
    boundary: {
      title: "Page hit an error",
      body: "Something on this page crashed.",
      retry: "Try again",
      dashboard: "Back to Dashboard",
      copyAria: "Copy error id {{id}}",
      copied: "Copied",
    },
  },
};

describe("a11y regression suite", () => {
  it("EmptyState carries no axe violations", async () => {
    const { container } = render(
      <EmptyState
        title="No games yet"
        description="Once Romarr ingests a ROM, you'll see games here."
      />,
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });

  it("ErrorFallback (PageErrorBoundary's visual half) is accessible", async () => {
    const { container } = renderWithProviders(
      <ErrorFallback
        error={new Error("synthetic")}
        errorId="abcd1234"
        onRetry={() => {}}
      />,
      { i18nResources: I18N_BUNDLE },
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });

  it("RegionBadge — every region variant", async () => {
    const { container } = render(
      <div>
        <RegionBadge code="USA" />
        <RegionBadge code="EUR" />
        <RegionBadge code="JPN" />
        <RegionBadge code="WLD" />
      </div>,
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });

  it("ConventionBadge — every convention variant", async () => {
    const { container } = render(
      <div>
        <ConventionBadge convention="no-intro" />
        <ConventionBadge convention="redump" />
        <ConventionBadge convention="tosec" />
        <ConventionBadge convention="goodtools" />
        <ConventionBadge convention="scene" />
      </div>,
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });

  it("DumpStatusIcon — every status variant", async () => {
    const { container } = render(
      <div>
        <DumpStatusIcon status="verified" />
        <DumpStatusIcon status="good" />
        <DumpStatusIcon status="proto" />
        <DumpStatusIcon status="beta" />
        <DumpStatusIcon status="demo" />
        <DumpStatusIcon status="sample" />
      </div>,
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });

  it("ScoreBadge — positive / zero / negative", async () => {
    const { container } = render(
      <div>
        <ScoreBadge score={120} />
        <ScoreBadge score={0} />
        <ScoreBadge score={-50} />
      </div>,
    );
    const result = await axe(container, _AXE_OPTIONS);
    expect(result.violations).toEqual([]);
  });
});
