import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MultiDiscAccordion } from "./MultiDiscAccordion";

describe("MultiDiscAccordion", () => {
  it("renders the parent title + Disc 1/N counter", () => {
    render(
      <MultiDiscAccordion
        parentTitle="Final Fantasy VII (USA)"
        totalDiscs={3}
      >
        <div>disc 2</div>
        <div>disc 3</div>
      </MultiDiscAccordion>,
    );

    expect(
      screen.getByText("Final Fantasy VII (USA)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Disc 1/3")).toBeInTheDocument();
  });

  it("starts closed by default", () => {
    const { container } = render(
      <MultiDiscAccordion parentTitle="X" totalDiscs={2}>
        <div>child</div>
      </MultiDiscAccordion>,
    );

    const details = container.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");
  });

  it("starts open when defaultOpen=true", () => {
    const { container } = render(
      <MultiDiscAccordion parentTitle="X" totalDiscs={2} defaultOpen>
        <div>child</div>
      </MultiDiscAccordion>,
    );

    const details = container.querySelector("details")!;
    expect(details).toHaveAttribute("open");
  });

  it("toggles open / closed when the summary is clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MultiDiscAccordion parentTitle="X" totalDiscs={2}>
        <div data-testid="child">child</div>
      </MultiDiscAccordion>,
    );

    const details = container.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");

    const summary = container.querySelector("summary")!;
    await user.click(summary);
    expect(details).toHaveAttribute("open");
  });

  it("renders the children inside the disclosure body", () => {
    render(
      <MultiDiscAccordion
        parentTitle="Sonic Mega Collection"
        totalDiscs={2}
        defaultOpen
      >
        <div data-testid="disc-2-body">Disc 2 details</div>
      </MultiDiscAccordion>,
    );

    expect(screen.getByTestId("disc-2-body")).toBeInTheDocument();
  });
});
