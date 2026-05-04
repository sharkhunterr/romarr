import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { ButtonFAB, LinkFAB } from "./FAB";

describe("LinkFAB", () => {
  it("renders a router Link to the supplied path with the icon + label", () => {
    render(
      <MemoryRouter>
        <LinkFAB
          ariaLabel="Add a new game"
          icon={<span>+</span>}
          label="Add"
          to="/add"
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "Add a new game" });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/add");
    expect(link).toHaveTextContent("+");
    expect(link).toHaveTextContent("Add");
  });

  it("clears the BottomNav on mobile + sits in the corner on desktop", () => {
    render(
      <MemoryRouter>
        <LinkFAB
          ariaLabel="Add"
          icon={<span>+</span>}
          label="Add"
          to="/add"
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "Add" });
    expect(link.className).toContain("bottom-20");
    expect(link.className).toContain("md:bottom-6");
    expect(link.className).toContain("right-4");
  });
});

describe("ButtonFAB", () => {
  it("calls onClick when clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <ButtonFAB
        ariaLabel="Trigger search"
        icon={<span>⚡</span>}
        label="Search"
        onClick={onClick}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Trigger search" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("respects disabled — onClick must not fire", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <ButtonFAB
        ariaLabel="Trigger search"
        icon={<span>⚡</span>}
        label="Search"
        onClick={onClick}
        disabled
      />,
    );

    const btn = screen.getByRole("button", { name: "Trigger search" });
    expect(btn).toBeDisabled();
    expect(btn.className).toContain("disabled:opacity-60");
    await user.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("renders the icon decoratively (aria-hidden) so the label drives a11y", () => {
    render(
      <ButtonFAB
        ariaLabel="Trigger search"
        icon={<span data-testid="icon">⚡</span>}
        label="Search"
        onClick={() => {}}
      />,
    );

    const icon = screen.getByTestId("icon");
    // The icon is wrapped in an aria-hidden span.
    expect(icon.parentElement?.getAttribute("aria-hidden")).toBe("true");
  });
});
