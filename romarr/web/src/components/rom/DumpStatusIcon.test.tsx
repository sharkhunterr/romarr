import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { DumpStatusIcon } from "./DumpStatusIcon";

describe("DumpStatusIcon", () => {
  it("renders 'Verified' status with the checkmark icon", () => {
    render(<DumpStatusIcon status="verified" />);

    const icon = screen.getByLabelText("Verified");
    expect(icon).toBeInTheDocument();
    expect(icon).toHaveTextContent("✓");
    expect(icon).toHaveTextContent("Verified");
  });

  it("renders 'Hack' status with warning + amber styling", () => {
    const { container } = render(<DumpStatusIcon status="hack" />);

    const icon = container.querySelector("span")!;
    expect(icon).toHaveTextContent("⚠");
    expect(icon).toHaveTextContent("Hack");
    expect(icon.className).toContain("amber");
  });

  it("renders 'Bad dump' with red styling", () => {
    const { container } = render(<DumpStatusIcon status="baddump" />);

    const icon = container.querySelector("span")!;
    expect(icon).toHaveTextContent("Bad dump");
    expect(icon.className).toContain("red");
  });

  it("renders icon-only when iconOnly=true", () => {
    render(<DumpStatusIcon status="proto" iconOnly />);

    const icon = screen.getByLabelText("Prototype");
    expect(icon).toHaveTextContent("🚧");
    expect(icon).not.toHaveTextContent("Prototype");
  });

  it("uses the documented label as both title and aria-label", () => {
    render(<DumpStatusIcon status="overdump" />);

    const icon = screen.getByLabelText("Overdump");
    expect(icon).toHaveAttribute("title", "Overdump");
  });
});
