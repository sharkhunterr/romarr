/**
 * ActionSheet tests (spec 014 T017 / T024).
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "@/test/render";

import { ActionSheet, ActionSheetItem } from "./ActionSheet";

describe("ActionSheet", () => {
  it("renders nothing when closed", () => {
    renderWithProviders(
      <ActionSheet open={false} onClose={() => {}}>
        <div>action-1</div>
      </ActionSheet>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the dialog with provided actions when open", () => {
    renderWithProviders(
      <ActionSheet open={true} onClose={() => {}} title="Choose an action">
        <ActionSheetItem onClick={() => {}}>Edit</ActionSheetItem>
        <ActionSheetItem onClick={() => {}} danger>Delete</ActionSheetItem>
      </ActionSheet>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Choose an action")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Edit" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete" }),
    ).toBeInTheDocument();
  });

  it("invokes onClose when the backdrop is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <ActionSheet open={true} onClose={onClose}>
        <div>x</div>
      </ActionSheet>,
    );
    await user.click(
      screen.getByRole("button", { name: "Close action sheet" }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("invokes onClose on Escape keypress", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <ActionSheet open={true} onClose={onClose}>
        <div>x</div>
      </ActionSheet>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does NOT invoke onClose on Escape when closed", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <ActionSheet open={false} onClose={onClose}>
        <div>x</div>
      </ActionSheet>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("locks body scroll while open and restores it on close", () => {
    const initialOverflow = document.body.style.overflow;
    const { rerender } = renderWithProviders(
      <ActionSheet open={true} onClose={() => {}}>
        <div>x</div>
      </ActionSheet>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    rerender(
      <ActionSheet open={false} onClose={() => {}}>
        <div>x</div>
      </ActionSheet>,
    );
    expect(document.body.style.overflow).toBe(initialOverflow);
  });
});

describe("ActionSheetItem", () => {
  it("invokes onClick when clicked", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <ActionSheet open={true} onClose={() => {}}>
        <ActionSheetItem onClick={onClick}>Click me</ActionSheetItem>
      </ActionSheet>,
    );
    await user.click(screen.getByRole("button", { name: "Click me" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disables the button when ``disabled`` prop is set", () => {
    renderWithProviders(
      <ActionSheet open={true} onClose={() => {}}>
        <ActionSheetItem onClick={() => {}} disabled>
          Disabled action
        </ActionSheetItem>
      </ActionSheet>,
    );
    const button = screen.getByRole("button", { name: "Disabled action" });
    expect(button).toBeDisabled();
  });

  it("applies danger tone styling when ``danger`` is set", () => {
    renderWithProviders(
      <ActionSheet open={true} onClose={() => {}}>
        <ActionSheetItem onClick={() => {}} danger>
          Delete forever
        </ActionSheetItem>
      </ActionSheet>,
    );
    const button = screen.getByRole("button", { name: "Delete forever" });
    expect(button.className).toContain("text-red-400");
  });
});
