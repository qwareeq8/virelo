import { describe, it, expect, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "../theme.jsx";
import { AboutPage, ShortcutsPage, ExplorerPage, SnapPage } from "../pages.jsx";

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
    captureActive: false,
    setCaptureActive: vi.fn(),
    setModalOpen: vi.fn(),
    set: vi.fn(),
    onTestSnap: vi.fn(),
    onReset: vi.fn(),
    showStatus: vi.fn(),
    bridge: {
      capture_key: vi.fn((target, cb) => cb(JSON.stringify({ ok: true }))),
      cancel_capture: vi.fn((cb) => cb(JSON.stringify({ ok: true }))),
      capture_status: { connect: vi.fn(), disconnect: vi.fn() },
      apply_details_view: vi.fn((cb) => cb(JSON.stringify({ ok: true, data: { started: true } }))),
      reset_folder_views: vi.fn((cb) => cb(JSON.stringify({ ok: true, data: { started: true } }))),
      views_status: { connect: vi.fn(), disconnect: vi.fn() },
    },
    ...overrides,
  };
}

describe("ShortcutsPage", () => {
  it("Renders one snap key chip per press in both snap and restore rows.", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 5 })} />);
    // The trigger row and the restore row each show the snap key once per
    // press, so the snap key appears twice per configured press.
    expect(screen.getAllByText("SHIFT")).toHaveLength(10);
  });

  it("Shows the restore key as one held modifier.", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 5 })} />);
    expect(screen.getAllByText("CTRL")).toHaveLength(1);
    expect(screen.getByText("(hold)")).toBeInTheDocument();
    expect(screen.getByText("Hold CTRL while tapping SHIFT 5 times.")).toBeInTheDocument();
  });

  it("Uses singular copy and one chip pair when pressCount is 1.", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 1 })} />);
    expect(screen.getAllByText("SHIFT")).toHaveLength(2);
    expect(screen.getAllByText("CTRL")).toHaveLength(1);
    expect(screen.getByText("Hold CTRL while tapping SHIFT once.")).toBeInTheDocument();
  });

  it("Wraps large shortcut sequences inside the supported window width.", () => {
    renderWithTheme(<ShortcutsPage app={makeApp({ pressCount: 10 })} />);
    const triggerRow = screen.getByText("Trigger snap").parentElement.parentElement;
    const chips = triggerRow.lastElementChild;

    expect(triggerRow.style.flexWrap).toBe("wrap");
    expect(chips.style.flexWrap).toBe("wrap");
    expect(chips.style.minWidth).toBe("0px");
  });

  it("Separates global gestures from the complete in-app shortcut list.", () => {
    renderWithTheme(<ShortcutsPage app={makeApp()} />);

    expect(screen.getByRole("heading", { level: 2, name: "Global snap gestures" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "In-app shortcuts" })).toBeVisible();
    for (const label of ["Command palette", "Save changes", "Toggle theme", "Test snap", "Help"]) {
      expect(screen.getByText(label)).toBeVisible();
    }
  });
});

describe("SnapPage size sliders", () => {
  it("Limits the width and height sliders to the backend range 10 to 100.", () => {
    renderWithTheme(<SnapPage app={makeApp()} />);
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(2);
    for (const slider of sliders) {
      expect(slider).toHaveAttribute("aria-valuemin", "10");
      expect(slider).toHaveAttribute("aria-valuemax", "100");
    }
    expect(screen.getByRole("slider", { name: "Width" })).toBeVisible();
    expect(screen.getByRole("slider", { name: "Height" })).toBeVisible();
  });

  it("Clears capture state and reports a rejected second capture.", async () => {
    const app = makeApp();
    app.bridge.capture_key = vi.fn((target, cb) =>
      cb(
        JSON.stringify({
          ok: false,
          error: "Key capture is already in progress.",
        }),
      ),
    );
    renderWithTheme(<SnapPage app={app} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Snap key: SHIFT" }));

    expect(screen.getByRole("button", { name: "Snap key: SHIFT" })).toBeVisible();
    expect(app.setCaptureActive).toHaveBeenLastCalledWith(false);
    expect(app.showStatus).toHaveBeenCalledWith(
      "Key capture is already in progress.",
      3000,
      "error",
    );
  });
});

describe("ExplorerPage default folder view", () => {
  it("Renders the section title, body copy, and both buttons.", () => {
    renderWithTheme(<ExplorerPage app={makeApp()} />);
    expect(screen.getByText("Default folder view")).toBeInTheDocument();
    expect(screen.getByText(/the way WinSetView does/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make Details the default" })).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: "Reset folder views to Windows defaults",
      }),
    ).toBeVisible();
  });

  it("Shows an in-progress message instead of success when apply starts.", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Make Details the default" }));
    const dialog = screen.getByRole("dialog", {
      name: "Make Details the default?",
    });
    expect(
      screen.getByText(/Finish any file copies, moves, or deletions first/),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", {
        name: "Apply and restart Explorer",
      }),
    );
    expect(app.bridge.apply_details_view).toHaveBeenCalledTimes(1);
    // The bridge callback only acknowledges a start. The completion message
    // arrives later through the views_status signal, so no success text may
    // be announced here.
    expect(app.showStatus).toHaveBeenCalledWith(
      "Applying Details view. File Explorer will restart...",
      0,
    );
    expect(app.showStatus).not.toHaveBeenCalledWith("Details view applied.", expect.anything());
    // The start acknowledgment must not permit a duplicate task.
    expect(screen.getByRole("button", { name: "Working..." })).toBeDisabled();
    const onViewsStatus = app.bridge.views_status.connect.mock.calls[0][0];
    act(() => onViewsStatus("Details is now the default view for all folders.", 6000));
    expect(screen.getByRole("button", { name: "Make Details the default" })).toBeEnabled();
  });

  it("Moves focus into the confirmation and restores the opener.", async () => {
    renderWithTheme(<ExplorerPage app={makeApp()} />);
    const user = userEvent.setup();
    const opener = screen.getByRole("button", {
      name: "Make Details the default",
    });

    await user.click(opener);
    const dialog = screen.getByRole("dialog", {
      name: "Make Details the default?",
    });
    expect(dialog).toContainElement(document.activeElement);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(document.activeElement).toBe(opener);
  });

  it("Moves focus to a stable action region when folder-view work starts.", async () => {
    renderWithTheme(<ExplorerPage app={makeApp()} />);
    const user = userEvent.setup();
    const opener = screen.getByRole("button", {
      name: "Make Details the default",
    });

    await user.click(opener);
    await user.click(
      within(screen.getByRole("dialog", { name: "Make Details the default?" })).getByRole(
        "button",
        { name: "Apply and restart Explorer" },
      ),
    );

    expect(opener).toBeDisabled();
    expect(screen.getByRole("group", { name: "Default folder view actions" })).toHaveFocus();
  });

  it("Shows an in-progress message instead of success when reset starts.", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", {
        name: "Reset folder views to Windows defaults",
      }),
    );
    const dialog = screen.getByRole("dialog", { name: "Reset folder views?" });
    await user.click(
      within(dialog).getByRole("button", {
        name: "Reset and restart Explorer",
      }),
    );
    expect(app.bridge.reset_folder_views).toHaveBeenCalledTimes(1);
    expect(app.showStatus).toHaveBeenCalledWith(
      "Resetting folder views. File Explorer will restart...",
      0,
    );
    expect(app.showStatus).not.toHaveBeenCalledWith("Folder views reset.", expect.anything());
    expect(screen.getByRole("button", { name: "Working..." })).toBeDisabled();
  });

  it("Does not call the bridge when the dialog is cancelled.", async () => {
    const app = makeApp();
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Make Details the default" }));
    const dialog = screen.getByRole("dialog", {
      name: "Make Details the default?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(app.bridge.apply_details_view).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("dialog", { name: "Make Details the default?" }),
    ).not.toBeInTheDocument();
  });

  it("Surfaces a backend error through showStatus.", async () => {
    const app = makeApp();
    app.bridge.apply_details_view = vi.fn((cb) =>
      cb(JSON.stringify({ ok: false, error: "Explorer restart failed." })),
    );
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Make Details the default" }));
    await user.click(screen.getByRole("button", { name: "Apply and restart Explorer" }));
    expect(app.showStatus).toHaveBeenCalledWith("Explorer restart failed.", 5000, "error");
  });

  it("Reports an unsupported backend when the method is missing.", async () => {
    const app = makeApp();
    delete app.bridge.apply_details_view;
    renderWithTheme(<ExplorerPage app={app} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Make Details the default" }));
    await user.click(screen.getByRole("button", { name: "Apply and restart Explorer" }));
    expect(app.showStatus).toHaveBeenCalledWith(
      "Folder view changes are not supported by this backend build.",
      5000,
      "error",
    );
  });
});

describe("AboutPage semantics", () => {
  it("Exposes the page heading and license disclosure state.", async () => {
    renderWithTheme(<AboutPage app={makeApp()} />);
    const user = userEvent.setup();

    expect(screen.getByRole("heading", { level: 1, name: "About" })).toBeVisible();
    const disclosure = screen.getByRole("button", { name: "View MIT license" });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    await user.click(disclosure);
    expect(screen.getByRole("button", { name: "Hide MIT license" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
