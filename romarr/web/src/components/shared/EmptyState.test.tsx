import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders the title alongside the default ◌ icon", () => {
    render(<EmptyState title="No games yet" />);

    expect(
      screen.getByRole("heading", { name: "No games yet" }),
    ).toBeInTheDocument();
    // The default icon is decorative — aria-hidden, no a11y role.
    expect(screen.getByText("◌")).toBeInTheDocument();
  });

  it("renders the description paragraph when supplied", () => {
    render(
      <EmptyState
        title="No games yet"
        description="Add a library to get started."
      />,
    );

    expect(
      screen.getByText("Add a library to get started."),
    ).toBeInTheDocument();
  });

  it("doesn't render a description paragraph when omitted", () => {
    const { container } = render(<EmptyState title="No games" />);

    expect(container.querySelector("p")).toBeNull();
  });

  it("renders the operator-supplied CTA below the body", () => {
    render(
      <EmptyState
        title="No games"
        cta={<button>Add library</button>}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Add library" }),
    ).toBeInTheDocument();
  });

  it("replaces the default icon when one is supplied", () => {
    render(
      <EmptyState
        title="No games"
        icon={<span data-testid="custom-icon">★</span>}
      />,
    );

    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
    // Default icon must be gone.
    expect(screen.queryByText("◌")).toBeNull();
  });
});
