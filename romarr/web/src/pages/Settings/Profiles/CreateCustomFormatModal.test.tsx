/**
 * CreateCustomFormatModal — visual builder tests (spec 014 T097).
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";
import * as customFormatsQuery from "@/lib/api/queries/custom-formats";

import { CreateCustomFormatModal } from "./CreateCustomFormatModal";

const I18N_BUNDLE = {
  settings: {
    customFormats: {
      create: {
        title: "New Custom Format",
        name: "Name",
        score: "Score",
        conditions: "Conditions",
        field: "Field",
        operator: "Operator",
        value: "Value",
        addCondition: "Add condition",
        removeCondition: "Remove condition",
        save: "Save",
        saving: "Saving…",
        cancel: "Cancel",
        success: "Created {{name}}",
      },
    },
  },
};

describe("CreateCustomFormatModal — visual builder", () => {
  it("renders the form with one default condition", () => {
    renderWithProviders(<CreateCustomFormatModal onClose={() => {}} />, {
      i18nResources: I18N_BUNDLE,
    });
    expect(
      screen.getByRole("heading", { name: "New Custom Format" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Field")).toBeInTheDocument();
    expect(screen.getByLabelText("Operator")).toBeInTheDocument();
    expect(screen.getByLabelText("Value")).toBeInTheDocument();
  });

  it("Save is disabled when name or value are empty", () => {
    renderWithProviders(<CreateCustomFormatModal onClose={() => {}} />, {
      i18nResources: I18N_BUNDLE,
    });
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
  });

  it("adds a second condition row when 'Add condition' is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CreateCustomFormatModal onClose={() => {}} />, {
      i18nResources: I18N_BUNDLE,
    });
    expect(screen.getAllByLabelText("Field")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Add condition" }));
    expect(screen.getAllByLabelText("Field")).toHaveLength(2);
  });

  it("submits the projected payload on save", async () => {
    const mutate = vi.fn();
    vi.spyOn(customFormatsQuery, "useCreateCustomFormat").mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof customFormatsQuery.useCreateCustomFormat>);

    const onClose = vi.fn();
    renderWithProviders(<CreateCustomFormatModal onClose={onClose} />, {
      i18nResources: I18N_BUNDLE,
    });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Name"), "x265");
    await user.clear(screen.getByLabelText("Score"));
    await user.type(screen.getByLabelText("Score"), "100");
    await user.type(screen.getByLabelText("Value"), "x265");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    const [payload] = mutate.mock.calls[0];
    expect(payload).toMatchObject({
      name: "x265",
      score: 100,
      conditions: [
        { field: "tags", operator: "equals", values: "x265" },
      ],
    });
  });
});
