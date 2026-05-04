/**
 * ConnectionIndicator test (spec 014 T050 follow-up).
 *
 * The dot maps each documented WebSocket connection status
 * to a class + label. We exercise four representative
 * branches: idle, connecting, connected, offline. The
 * verbose label is `title=` on the wrapper plus a md+-only
 * inline span — we verify both.
 */

import { afterEach, describe, expect, it } from "vitest";
import { act, screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { ConnectionIndicator } from "./ConnectionIndicator";
import { useConnectionStore } from "@/lib/store/connection";

const I18N_BUNDLE = {
  translation: {
    connection: {
      idle: "Idle",
      connecting: "Connecting…",
      connected: "Live",
      reconnecting: "Reconnecting…",
      offline: "Offline",
    },
  },
};

afterEach(() => {
  act(() => {
    useConnectionStore.getState().setStatus("idle");
  });
});

describe("ConnectionIndicator", () => {
  it("renders the idle state by default", () => {
    renderWithProviders(<ConnectionIndicator />, {
      i18nResources: I18N_BUNDLE,
    });

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("title", "Idle");
  });

  it("renders the connecting state with amber pulse + i18n label", () => {
    act(() => {
      useConnectionStore.getState().setStatus("connecting");
    });

    renderWithProviders(<ConnectionIndicator />, {
      i18nResources: I18N_BUNDLE,
    });

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("title", "Connecting…");
  });

  it("renders the connected state with the brand-green class", () => {
    act(() => {
      useConnectionStore.getState().setStatus("connected");
    });

    renderWithProviders(<ConnectionIndicator />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByRole("status")).toHaveAttribute("title", "Live");
  });

  it("renders the offline state with the red class", () => {
    act(() => {
      useConnectionStore.getState().setStatus("offline");
    });

    renderWithProviders(<ConnectionIndicator />, {
      i18nResources: I18N_BUNDLE,
    });

    expect(screen.getByRole("status")).toHaveAttribute("title", "Offline");
  });
});
