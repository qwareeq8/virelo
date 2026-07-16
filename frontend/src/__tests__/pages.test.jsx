import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "../theme.jsx";
import { ShortcutsPage, ExplorerPage, SnapPage } from "../pages.jsx";

// Wrap the component under test in a ThemeProvider with minimal tweaks.
function renderWithTheme(ui) {
  const tweaks = { theme: "dark", accent: "slate", density: "cozy", radius: 6 };
  return render(
    <ThemeProvider tweaks={tweaks} setTweaks={vi.fn()}>
      {ui}
    </ThemeProvider>,
  );
}

function makeApp(overrides = {}) {
  return {
    snapEnabled: true,
    snapKey: "SHIFT",
    restoreKey: "CTRL",
    pressCount: 3,
    interval: 1050,
    width: 76,
    height: 76,
    gameMode: true,
    autoSize: true,
    launchLogin: false,
    accent: "slate",
    density: "cozy",
    themeMode: "system",
    set: vi.fn(),
    onTestSnap: vi.fn(),
    onReset: vi.fn(),
    showStatus: vi.fn(),
    bridge: {
      capture_key: vi.fn(),
      capture_status: { connect: vi.fn(), disconnect: vi.fn() },
      apply_details_view: vi.fn((cb) =>
        cb(JSON.stringify({ ok: true, data: { started: true } })),
      ),
      reset_folder_views: vi.fn((cb) =>
        cb(JSON.stringify({ ok: true, data: { started: true } })),
      ),
    },
    ...overrides,
  };
}

describe("ShortcutsPage", () => {
  it("renders one snap key chip per press in both snap and restore rows", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 5 })} />);
    // The trigger row and the restore row each show the snap key once per
    // press, so the snap key appears twice per configured press.
    expect(screen.getAllByText("SHIFT")).toHaveLength(10);
  });

  it("shows the restore key as a single held modifier, not repeated presses", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 5 })} />);
    expect(screen.getAllByText("CTRL")).toHaveLength(1);
    expect(screen.getByText("(hold)")).toBeInTheDocument();
    expect(
      screen.getByText("Hold CTRL while tapping SHIFT 5 times."),
    ).toBeInTheDocument();
  });

  it("uses singular copy and a single chip pair for pressCount 1", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 1 })} />);
    expect(screen.getAllByText("SHIFT")).toHaveLength(2);
    expect(screen.getAllByText("CTRL")).toHaveLength(1);
    expect(
      screen.getByText("Hold CTRL while tapping SHIFT once."),
    ).toBeInTheDocument();
  });
});

describe("SnapPage size sliders", () => {
  it("limits the width and height sliders to the backend range 10 to 100", () => {
    renderWithTheme(<SnapPage app={makeApp()} />);
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(2);
    for (const slider of sliders) {
      expect(slider).toHaveAttribute("aria-valuemin", "10");
      expect(slider).toHaveAttribute("aria-valuemax", "100");
    }
  });
});

describe("ExplorerPage default folder view", () => {
  it("renders the section title, body copy, and both buttons", () => {
    renderWithTheme(<ExplorerPage app={makeApp()} />);
    expect(screen.getByText("Default folder view")).toBeInTheDocument();
    expect(screen.getByText(/the way WinSetView does/)).toBeInTheDocument();
    expect(screen.getByText("Make Details the default")).toBeInTheDocument();
    expect(
      screen.getByText("Reset folder views to Windows defaults"),
    ).toBeInTheDocument();
  });

  it("shows an in-progress message, not success, when apply starts", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Make Details the default"));
    expect(screen.getByText("Make Details the default?")).toBeInTheDocument();
    expect(
      screen.getByText(/Open Explorer windows will close/),
    ).toBeInTheDocument();
    await user.click(screen.getByText("Apply and restart Explorer"));
    expect(app.bridge.apply_details_view).toHaveBeenCalledTimes(1);
    // The bridge callback only acknowledges a start. The completion message
    // arrives later through the views_status signal, so no success text may
    // be announced here.
    expect(app.showStatus).toHaveBeenCalledWith(
      "Applying Details view. File Explorer will restart...",
      0,
    );
    expect(app.showStatus).not.toHaveBeenCalledWith(
      "Details view applied.",
      expect.anything(),
    );
    // The buttons re-enable once the started acknowledgment arrives.
    expect(
      screen.getByText("Make Details the default").closest("button"),
    ).toBeEnabled();
  });

  it("shows an in-progress message, not success, when reset starts", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByText("Reset folder views to Windows defaults"),
    );
    expect(screen.getByText("Reset folder views?")).toBeInTheDocument();
    await user.click(screen.getByText("Reset and restart Explorer"));
    expect(app.bridge.reset_folder_views).toHaveBeenCalledTimes(1);
    expect(app.showStatus).toHaveBeenCalledWith(
      "Resetting folder views. File Explorer will restart...",
      0,
    );
    expect(app.showStatus).not.toHaveBeenCalledWith(
      "Folder views reset.",
      expect.anything(),
    );
    expect(
      screen
        .getByText("Reset folder views to Windows defaults")
        .closest("button"),
    ).toBeEnabled();
  });

  it("does not call the bridge when the dialog is cancelled", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Make Details the default"));
    await user.click(screen.getByText("Cancel"));
    expect(app.bridge.apply_details_view).not.toHaveBeenCalled();
    expect(
      screen.queryByText("Make Details the default?"),
    ).not.toBeInTheDocument();
  });

  it("surfaces a backend error through showStatus", async () => {
    const app = makeApp();
    app.bridge.apply_details_view = vi.fn((cb) =>
      cb(JSON.stringify({ ok: false, error: "Explorer restart failed." })),
    );
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Make Details the default"));
    await user.click(screen.getByText("Apply and restart Explorer"));
    expect(app.showStatus).toHaveBeenCalledWith(
      "Explorer restart failed.",
      5000,
    );
  });

  it("reports an unsupported backend when the method is missing", async () => {
    const app = makeApp();
    delete app.bridge.apply_details_view;
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Make Details the default"));
    await user.click(screen.getByText("Apply and restart Explorer"));
    expect(app.showStatus).toHaveBeenCalledWith(
      "Folder view changes are not supported by this backend build.",
      5000,
    );
  });
});
