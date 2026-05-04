import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { LanguagePills } from "./LanguagePills";

describe("LanguagePills", () => {
  it("renders one pill per language code", () => {
    render(<LanguagePills codes={["en", "fr", "ja"]} />);

    expect(screen.getByLabelText("Language en")).toBeInTheDocument();
    expect(screen.getByLabelText("Language fr")).toBeInTheDocument();
    expect(screen.getByLabelText("Language ja")).toBeInTheDocument();
  });

  it("normalises uppercase codes to lowercase in the rendered label", () => {
    render(<LanguagePills codes={["EN", "FR"]} />);

    expect(screen.getByLabelText("Language en")).toBeInTheDocument();
    expect(screen.getByLabelText("Language fr")).toBeInTheDocument();
  });

  it("falls back to a globe for unknown codes", () => {
    render(<LanguagePills codes={["xx"]} />);

    const pill = screen.getByLabelText("Language xx");
    expect(pill).toHaveTextContent("xx");
    expect(pill).toHaveTextContent("🌐");
  });

  it("collapses overflow into a +N pill when codes exceed max", () => {
    render(
      <LanguagePills
        codes={["en", "fr", "de", "es", "it", "ja", "ko"]}
        max={3}
      />,
    );

    // First three rendered.
    expect(screen.getByLabelText("Language en")).toBeInTheDocument();
    expect(screen.getByLabelText("Language fr")).toBeInTheDocument();
    expect(screen.getByLabelText("Language de")).toBeInTheDocument();
    // Remainder collapsed.
    expect(screen.queryByLabelText("Language es")).not.toBeInTheDocument();
    const overflow = screen.getByLabelText("4 more languages");
    expect(overflow).toHaveTextContent("+4");
    expect(overflow.getAttribute("title")).toBe("es, it, ja, ko");
  });

  it("renders nothing extra when codes <= max", () => {
    render(<LanguagePills codes={["en", "fr"]} max={5} />);

    expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument();
  });
});
