import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { CoverImage } from "./CoverImage";

describe("CoverImage", () => {
  it("falls back to the gradient + initials when no src and no gameId", () => {
    render(<CoverImage alt="Sonic the Hedgehog" />);

    const fallback = screen.getByRole("img", {
      name: "Sonic the Hedgehog",
    });
    expect(fallback).toBeInTheDocument();
    expect(fallback).toHaveTextContent("ST");
    expect(fallback.className).toContain("from-brand-700");
  });

  it("renders a single-letter initial for single-word titles", () => {
    render(<CoverImage alt="Tetris" />);

    const fallback = screen.getByRole("img", { name: "Tetris" });
    expect(fallback).toHaveTextContent("T");
  });

  it("renders an <img> when src is supplied without gameId", () => {
    const { container } = render(
      <CoverImage src="https://cdn.test/sonic.jpg" alt="Sonic" />,
    );
    const img = container.querySelector("img")!;
    expect(img).toBeInTheDocument();
    expect(img.getAttribute("src")).toBe("https://cdn.test/sonic.jpg");
    expect(img.getAttribute("alt")).toBe("Sonic");
    expect(img.getAttribute("loading")).toBe("lazy");
  });

  it("resolves to /api/v3/cover/{gameId} when gameId + src are supplied", () => {
    const { container } = render(
      <CoverImage gameId={42} src="data/covers/42.jpg" alt="Sonic" />,
    );
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/api/v3/cover/42");
  });

  it("appends ?v=<cacheKey> for cache-busting", () => {
    const { container } = render(
      <CoverImage
        gameId={42}
        src="data/covers/42.jpg"
        cacheKey="2026-05-04T12:00:00Z"
        alt="Sonic"
      />,
    );
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe(
      "/api/v3/cover/42?v=2026-05-04T12%3A00%3A00Z",
    );
  });

  it("falls back to the gradient when the <img> errors", () => {
    const { container, rerender: _rerender } = render(
      <CoverImage src="https://cdn.test/missing.jpg" alt="Sonic" />,
    );
    const img = container.querySelector("img")!;
    expect(img).toBeInTheDocument();

    fireEvent.error(img);

    // After the error, the component swaps to the fallback.
    const fallback = screen.getByRole("img", { name: "Sonic" });
    expect(fallback).toHaveTextContent("S");
    expect(container.querySelector("img")).toBeNull();
  });
});
