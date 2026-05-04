/**
 * OfflineIndicator test (spec 014 T021).
 *
 * The component subscribes to window online/offline events
 * and renders a banner only when the device is offline.
 * jsdom's navigator.onLine defaults to true; we exercise
 * both the initial-mount-online (returns null) and the
 * subsequent offline-transition (banner renders) paths.
 */

import { afterEach, describe, expect, it } from "vitest";
import { act, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { OfflineIndicator } from "./OfflineIndicator";

const I18N_BUNDLE = {
  translation: {
    connection: {
      deviceOffline: "Device is offline — using cached data.",
    },
  },
};

afterEach(() => {
  // Reset onLine for the next test if a previous one stubbed it.
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
  });
});

describe("OfflineIndicator", () => {
  it("renders nothing when navigator.onLine is true on mount", () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: true,
    });

    const { container } = renderWithProviders(<OfflineIndicator />, {
      i18nResources: I18N_BUNDLE,
    });

    // The component returns null when online — the wrapper div
    // from React Testing Library is empty.
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the banner immediately when navigator.onLine is false on mount", () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: false,
    });

    renderWithProviders(<OfflineIndicator />, { i18nResources: I18N_BUNDLE });

    expect(
      screen.getByText("Device is offline — using cached data."),
    ).toBeInTheDocument();
  });

  it("toggles visibility on window online/offline events", () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: true,
    });

    renderWithProviders(<OfflineIndicator />, { i18nResources: I18N_BUNDLE });

    // Initially hidden.
    expect(
      screen.queryByText("Device is offline — using cached data."),
    ).toBeNull();

    // Fire offline → banner appears.
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(
      screen.getByText("Device is offline — using cached data."),
    ).toBeInTheDocument();

    // Fire online → banner unmounts.
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(
      screen.queryByText("Device is offline — using cached data."),
    ).toBeNull();
  });
});
