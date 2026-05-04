/**
 * Settings > Tags page test (spec 014 P-SET).
 *
 * Mocks `useTags` (page-level read) plus `useCreateTag`
 * (CreateTagForm). The form's full submit/PATCH/DELETE flow
 * is integration-grade; here we cover the read-side states
 * + the create form's surface (renders, fields present).
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/test/render";

import { TagsPage } from "./index";
import * as tagsQuery from "@/lib/api/queries/tags";

const I18N_BUNDLE = {
  settings: {
    tags: {
      title: "Tags",
      subtitle: "Categorise games for filtering.",
      existing: "Existing tags",
      empty: { title: "No tags yet", body: "Create your first tag." },
      loadError: "Tag list unavailable",
      search: { label: "Search tags", placeholder: "Slug or label" },
      filter: {
        unusedOnly: { on: "Showing {{count}} unused", off: "{{count}} unused" },
        noMatches: "Nothing matches.",
      },
      create: {
        heading: "New tag",
        slug: "Slug",
        slugPlaceholder: "rare",
        label: "Label",
        labelPlaceholder: "Rare imports",
        color: "Color",
        submit: "Create tag",
        submitting: "Creating…",
        errors: { conflict: "Tag already exists" },
      },
    },
  },
};

function _stubCreate(): void {
  vi.spyOn(tagsQuery, "useCreateTag").mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof tagsQuery.useCreateTag>);
}

describe("TagsPage", () => {
  it("renders the empty-state when useTags returns []", () => {
    vi.spyOn(tagsQuery, "useTags").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof tagsQuery.useTags>);
    _stubCreate();

    renderWithProviders(<TagsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Tags")).toBeInTheDocument();
    expect(screen.getByText("No tags yet")).toBeInTheDocument();
    // Create form remains rendered so the operator can fix it.
    expect(screen.getByLabelText("Slug")).toBeInTheDocument();
    expect(screen.getByLabelText("Label")).toBeInTheDocument();
  });

  it("renders one row per tag when useTags returns data", () => {
    vi.spyOn(tagsQuery, "useTags").mockReturnValue({
      data: [
        { id: 1, name: "rare", label: "Rare imports", color: "#9BBC0F", usageCount: 3 },
        { id: 2, name: "hack", label: "Hacks", color: "#FF0000", usageCount: 0 },
      ],
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof tagsQuery.useTags>);
    _stubCreate();

    renderWithProviders(<TagsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Rare imports")).toBeInTheDocument();
    expect(screen.getByText("Hacks")).toBeInTheDocument();
  });

  it("surfaces the loadError when useTags fails", () => {
    vi.spyOn(tagsQuery, "useTags").mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: { message: "tag table missing" },
    } as unknown as ReturnType<typeof tagsQuery.useTags>);
    _stubCreate();

    renderWithProviders(<TagsPage />, { i18nResources: I18N_BUNDLE });

    expect(screen.getByText("Tag list unavailable")).toBeInTheDocument();
    expect(screen.getByText("tag table missing")).toBeInTheDocument();
  });
});
