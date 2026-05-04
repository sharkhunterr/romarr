/**
 * PageErrorBoundary tests (CL011).
 *
 * Verifies the boundary contract:
 *   * a child render-time throw renders the localized fallback
 *     (title + Retry + Back to Dashboard + error id);
 *   * Retry resets the boundary so the children re-render;
 *   * a stable error id (8 hex chars) is computed from the error
 *     message;
 *   * the shell (rendered alongside the boundary) is unaffected.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { PageErrorBoundary } from "./PageErrorBoundary";

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

function _Boom(): never {
  throw new Error("boom");
}

describe("PageErrorBoundary", () => {
  it("renders the localized fallback when a child throws", () => {
    // Suppress the noisy "Error: boom" trace React prints when a
    // boundary catches.
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    renderWithProviders(
      <div>
        <header data-testid="shell">shell</header>
        <PageErrorBoundary>
          <_Boom />
        </PageErrorBoundary>
      </div>,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("Page hit an error")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Dashboard" }),
    ).toBeInTheDocument();
    // Shell stays mounted.
    expect(screen.getByTestId("shell")).toBeInTheDocument();

    errSpy.mockRestore();
  });

  it("Retry resets the boundary so children re-render", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    // External mutable cell drives the conditional throw. The
    // boundary's reset → React calls ``render`` again → the child
    // reads the latest cell value and renders OK.
    const cell = { fail: true };
    function _ChildFromCell(): JSX.Element {
      if (cell.fail) {
        throw new Error("boom");
      }
      return <div data-testid="ok">child mounted</div>;
    }

    renderWithProviders(
      <PageErrorBoundary>
        <_ChildFromCell />
      </PageErrorBoundary>,
      { i18nResources: I18N_BUNDLE },
    );

    expect(screen.getByText("Page hit an error")).toBeInTheDocument();

    // Flip the failure flag, then click Retry — the boundary
    // clears its error state, React re-renders children, and the
    // cell now reports ``fail=false`` so OK renders.
    cell.fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.getByTestId("ok")).toBeInTheDocument();
    expect(screen.queryByText("Page hit an error")).toBeNull();

    errSpy.mockRestore();
  });

  it("computes a stable 8-char hex error id from the error message", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    renderWithProviders(
      <PageErrorBoundary>
        <_Boom />
      </PageErrorBoundary>,
      { i18nResources: I18N_BUNDLE },
    );

    // The id button labels itself "#xxxxxxxx" before the click.
    // We can't grab it by name (the localized aria-label includes
    // the id we don't know yet), so query by aria-label prefix.
    const idButton = screen.getByRole("button", {
      name: /Copy error id [0-9a-f]{8}/,
    });
    const match = idButton.getAttribute("aria-label")?.match(
      /Copy error id ([0-9a-f]{8})/,
    );
    expect(match).not.toBeNull();
    expect(match?.[1]).toMatch(/^[0-9a-f]{8}$/);

    errSpy.mockRestore();
  });
});
