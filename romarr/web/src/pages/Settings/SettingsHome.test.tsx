/**
 * SettingsHome test (spec 014 T095).
 *
 * The landing panel partitions every entry from
 * SETTINGS_NAV_ENTRIES into "shipped" vs "coming soon" and
 * renders the shipped ones as Link cards. We assert the
 * documented headings, that a few representative shipped
 * entries land in the right column, and that the link href
 * matches each entry's `to` field.
 */

import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { SettingsHome } from "./SettingsHome";

const I18N_BUNDLE = {
  settings: {
    home: {
      welcomeTitle: "Welcome to Settings",
      welcomeBody: "Configure profiles, libraries, and integrations.",
      availableNow: "Available now",
      comingSoon: "Coming soon",
    },
    nav: {
      profiles: "Profiles",
      "media-management": "Media management",
      "quality-definitions": "Quality definitions",
      indexers: "Indexers",
      "download-clients": "Download clients",
      "dat-sources": "DAT sources",
      "metadata-sources": "Metadata sources",
      platforms: "Platforms",
      connect: "Notifications",
      tags: "Tags",
      unidentified: "Unidentified",
      ui: "User interface",
      general: "General",
      comingSoon: "Soon",
    },
  },
};

describe("SettingsHome", () => {
  it("renders the welcome panel + both section headings", () => {
    renderWithProviders(<SettingsHome />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Welcome to Settings")).toBeInTheDocument();
    expect(screen.getByText("Available now")).toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("links each shipped entry to its documented sub-route", () => {
    renderWithProviders(<SettingsHome />, { i18nResources: I18N_BUNDLE });

    const profilesLink = screen.getByRole("link", { name: /Profiles/i });
    expect(profilesLink).toHaveAttribute("href", "/settings/profiles");
    const tagsLink = screen.getByRole("link", { name: /Tags/i });
    expect(tagsLink).toHaveAttribute("href", "/settings/tags");
    const platformsLink = screen.getByRole("link", { name: /Platforms/i });
    expect(platformsLink).toHaveAttribute("href", "/settings/platforms");
  });

  it("lists the unshipped entries under the Coming soon section without rendering links for them", () => {
    renderWithProviders(<SettingsHome />, { i18nResources: I18N_BUNDLE });

    // "Quality definitions" and "DAT sources" are not yet shipped —
    // they appear in the Coming soon list but not as links.
    expect(screen.getByText("Quality definitions")).toBeInTheDocument();
    expect(screen.getByText("DAT sources")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Quality definitions/i }),
    ).toBeNull();
    expect(
      screen.queryByRole("link", { name: /DAT sources/i }),
    ).toBeNull();
  });
});
