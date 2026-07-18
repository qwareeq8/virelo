import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { FatalErrorScreen, VireloErrorBoundary } from "../fatal-error.jsx";

function ThrowingChild() {
  throw new Error("Render failed.");
}

describe("FatalErrorScreen", () => {
  it("Provides an actionable fatal-error message.", () => {
    render(<FatalErrorScreen message="Virelo could not load." />);

    expect(screen.getByRole("alert")).toHaveTextContent("Virelo could not load. Restart Virelo.");
  });
});

describe("VireloErrorBoundary", () => {
  it("Replaces a failed React tree with the fatal-error screen.", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      render(
        <VireloErrorBoundary>
          <ThrowingChild />
        </VireloErrorBoundary>,
      );

      expect(screen.getByRole("alert")).toHaveTextContent("Virelo encountered an interface error.");
      expect(consoleError).toHaveBeenCalled();
    } finally {
      consoleError.mockRestore();
    }
  });
});
