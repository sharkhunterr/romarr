import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { PlatformIcon } from "./PlatformIcon";

describe("PlatformIcon", () => {
  it("renders the slug initials in a coloured square", () => {
    render(<PlatformIcon slug="megadrive" name="Mega Drive" />);

    const icon = screen.getByLabelText("Mega Drive");
    expect(icon).toBeInTheDocument();
    expect(icon).toHaveTextContent("ME");
    expect(icon.className).toContain("blue-700");
  });

  it("falls back to manufacturer colour when slug is unrecognised", () => {
    render(
      <PlatformIcon
        slug="dreamcast"
        name="Dreamcast"
        manufacturer="Sega"
      />,
    );

    const icon = screen.getByLabelText("Dreamcast");
    expect(icon).toHaveTextContent("DR");
    // Sega manufacturer colour fall-through.
    expect(icon.className).toContain("blue-600");
  });

  it("falls back to neutral colours when neither slug nor manufacturer is known", () => {
    render(<PlatformIcon slug="zx-spectrum" name="ZX Spectrum" />);

    const icon = screen.getByLabelText("ZX Spectrum");
    expect(icon).toHaveTextContent("ZX");
    expect(icon.className).toContain("zinc-800");
  });

  it("uses the slug as the aria-label when name is omitted", () => {
    render(<PlatformIcon slug="snes" />);

    const icon = screen.getByLabelText("Platform snes");
    expect(icon).toHaveAttribute("title", "snes");
  });

  it("recognises the kebab-cased slug variants", () => {
    render(<PlatformIcon slug="mega-drive" name="Mega Drive" />);

    const icon = screen.getByLabelText("Mega Drive");
    expect(icon.className).toContain("blue-700");
  });
});
