import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DARK, LIGHT, ThemeProvider } from "../theme.jsx";
import { Toggle, Button, Card, Row, Slider, Badge } from "../primitives.jsx";

// Wrap each component in ThemeProvider with the minimum required tweaks.
function renderWithTheme(ui) {
  const tweaks = { theme: "dark", accent: "slate", density: "cozy", radius: 6 };
  return render(
    <ThemeProvider tweaks={tweaks} setTweaks={vi.fn()}>
      {ui}
    </ThemeProvider>,
  );
}

describe("Toggle", () => {
  it("Renders the off state.", () => {
    renderWithTheme(<Toggle on={false} onChange={vi.fn()} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it("Renders the on state.", () => {
    renderWithTheme(<Toggle on={true} onChange={vi.fn()} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});

describe("Button", () => {
  it("Uses its child text as its accessible name.", () => {
    renderWithTheme(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeVisible();
  });

  it("Renders the primary variant.", () => {
    renderWithTheme(<Button variant="primary">Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });

  it("Forwards accessible disclosure attributes.", () => {
    renderWithTheme(
      <Button aria-expanded="false" aria-controls="details">
        Details
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Details" })).toHaveAttribute(
      "aria-controls",
      "details",
    );
  });
});

describe("Card", () => {
  it("Renders its title and children.", () => {
    renderWithTheme(
      <Card title="Test Card">
        <p>Card content</p>
      </Card>,
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Test Card" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Card content")).toBeInTheDocument();
  });

  it("Renders without a title.", () => {
    renderWithTheme(
      <Card>
        <p>Just content</p>
      </Card>,
    );
    expect(screen.getByText("Just content")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("Renders with the default tone.", () => {
    renderWithTheme(<Badge>NEW</Badge>);
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });

  it("Renders with the accent tone.", () => {
    renderWithTheme(<Badge tone="accent">ON</Badge>);
    expect(screen.getByText("ON")).toBeInTheDocument();
  });
});

describe("Slider", () => {
  function renderSlider(onChange = vi.fn()) {
    renderWithTheme(<Slider value={50} onChange={onChange} />);
    const slider = screen.getByRole("slider");
    vi.spyOn(slider, "getBoundingClientRect").mockReturnValue({
      left: 0,
      width: 100,
      top: 0,
      right: 100,
      bottom: 20,
      height: 20,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
    slider.setPointerCapture = vi.fn();
    slider.hasPointerCapture = vi.fn(() => true);
    slider.releasePointerCapture = vi.fn();
    return { slider, onChange };
  }

  it("Ignores non-primary pointer buttons.", () => {
    const { slider, onChange } = renderSlider();

    fireEvent.pointerDown(slider, { button: 2, clientX: 80, pointerId: 1 });

    expect(onChange).not.toHaveBeenCalled();
    expect(slider.setPointerCapture).not.toHaveBeenCalled();
  });

  it("Stops tracking a pointer after pointer cancellation.", () => {
    const { slider, onChange } = renderSlider();

    fireEvent.pointerDown(slider, { button: 0, clientX: 20, pointerId: 7 });
    expect(onChange).toHaveBeenCalledTimes(1);
    fireEvent.pointerCancel(slider, { pointerId: 7 });
    fireEvent.pointerMove(slider, { clientX: 90, pointerId: 7 });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(slider.releasePointerCapture).toHaveBeenCalledWith(7);
  });

  it("Uses its visual row label as its accessible name.", () => {
    renderWithTheme(
      <Row label="Window width">
        <Slider value={50} onChange={vi.fn()} />
      </Row>,
    );

    expect(screen.getByRole("slider", { name: "Window width" })).toBeVisible();
  });

  it("Supports standard horizontal slider keyboard controls.", () => {
    const onChange = vi.fn();
    renderWithTheme(
      <Slider value={50} onChange={onChange} min={10} max={90} />,
    );
    const slider = screen.getByRole("slider");

    fireEvent.keyDown(slider, { key: "ArrowUp" });
    fireEvent.keyDown(slider, { key: "ArrowDown" });
    fireEvent.keyDown(slider, { key: "Home" });
    fireEvent.keyDown(slider, { key: "End" });

    expect(onChange.mock.calls.map(([value]) => value)).toEqual([
      51, 49, 10, 90,
    ]);
  });

  it("Uses the row description as its accessible description.", () => {
    renderWithTheme(
      <Row label="Window width" description="Percentage of screen width.">
        <Slider value={50} onChange={vi.fn()} />
      </Row>,
    );

    expect(
      screen.getByRole("slider", { name: "Window width" }),
    ).toHaveAccessibleDescription("Percentage of screen width.");
  });
});

describe("Row control names", () => {
  it("Names an otherwise empty switch from its row.", () => {
    renderWithTheme(
      <Row label="Enable snap">
        <Toggle on={true} onChange={vi.fn()} />
      </Row>,
    );

    expect(screen.getByRole("switch", { name: "Enable snap" })).toBeVisible();
  });
});

function relativeLuminance(hex) {
  const channels = [1, 3, 5].map(
    (offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255,
  );
  const linear = channels.map((value) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(foreground, background) {
  const values = [relativeLuminance(foreground), relativeLuminance(background)];
  return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05);
}

describe("semantic text contrast", () => {
  it("Keeps muted and danger text at WCAG AA contrast in both themes.", () => {
    expect(
      contrastRatio(LIGHT.textMuted, LIGHT.sidebar),
    ).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(DARK.textMuted, DARK.surface)).toBeGreaterThanOrEqual(
      4.5,
    );
    expect(
      contrastRatio(LIGHT.dangerText, LIGHT.surface),
    ).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(DARK.dangerText, DARK.surface)).toBeGreaterThanOrEqual(
      4.5,
    );
  });
});
