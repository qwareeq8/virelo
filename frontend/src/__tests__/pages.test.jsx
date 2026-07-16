import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "../theme.jsx";
import { ShortcutsPage, ExplorerPage } from "../pages.jsx";

// Wrap component in ThemeProvider with minimal tweaks
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
        cb(JSON.stringify({ ok: true, data: {} })),
      ),
      reset_folder_views: vi.fn((cb) =>
        cb(JSON.stringify({ ok: true, data: {} })),
      ),
    },
    ...overrides,
  };
}

describe("ShortcutsPage", () => {
  it("renders one key chip per press for pressCount 5", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 5 })} />);
    expect(screen.getAllByText("SHIFT")).toHaveLength(5);
    expect(screen.getAllByText("CTRL")).toHaveLength(5);
  });

  it("renders a single key chip for pressCount 1", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 1 })} />);
    expect(screen.getAllByText("SHIFT")).toHaveLength(1);
    expect(screen.getAllByText("CTRL")).toHaveLength(1);
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

  it("opens a confirm dialog and calls apply_details_view on confirm", async () => {
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
    expect(app.showStatus).toHaveBeenCalledWith("Details view applied.", 3000);
  });

  it("opens a confirm dialog and calls reset_folder_views on confirm", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByText("Reset folder views to Windows defaults"),
    );
    expect(screen.getByText("Reset folder views?")).toBeInTheDocument();
    await user.click(screen.getByText("Reset and restart Explorer"));
    expect(app.bridge.reset_folder_views).toHaveBeenCalledTimes(1);
    expect(app.showStatus).toHaveBeenCalledWith("Folder views reset.", 3000);
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
});
