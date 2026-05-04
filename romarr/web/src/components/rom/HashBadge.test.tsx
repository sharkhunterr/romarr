import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HashBadge } from "./HashBadge";

describe("HashBadge", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the hash type prefix and the truncated value", () => {
    const fullHash = "abcd1234567890ef";
    render(<HashBadge type="SHA1" value={fullHash} />);

    const button = screen.getByRole("button", {
      name: /copy SHA1 hash/i,
    });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("SHA1");
    // Default truncate=12 → first 12 chars + ellipsis.
    expect(button).toHaveTextContent("abcd12345678…");
  });

  it("doesn't truncate when value is shorter than the cap", () => {
    render(<HashBadge type="CRC32" value="abcd1234" />);

    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("abcd1234");
    expect(button).not.toHaveTextContent("…");
  });

  it("respects the operator-supplied truncate length", () => {
    render(<HashBadge type="MD5" value="0123456789abcdef" truncate={4} />);

    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("0123…");
  });

  it("copies the FULL hash to clipboard on click", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText },
    });

    const fullHash = "abcd1234567890ef0123456789abcdef";
    render(<HashBadge type="SHA256" value={fullHash} />);

    await user.click(screen.getByRole("button"));
    expect(writeText).toHaveBeenCalledWith(fullHash);
  });

  it("exposes the full hash in the tooltip even when truncated", () => {
    const fullHash = "0123456789abcdef0123456789abcdef";
    render(<HashBadge type="SHA1" value={fullHash} />);

    const button = screen.getByRole("button");
    expect(button.getAttribute("title")).toContain(fullHash);
  });
});
