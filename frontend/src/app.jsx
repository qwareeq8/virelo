// Main app shell: title bar, sidebar, page router, footer.

import React from "react";
import { useTokens, useTheme } from "./theme.jsx";
import {
  SnapPage,
  ExplorerPage,
  ShortcutsPage,
  GeneralPage,
  AboutPage,
} from "./pages.jsx";
import { CommandPalette } from "./panels.jsx";
import { Button, Badge } from "./primitives.jsx";
import { Icon } from "./icons.jsx";

// Minimum interval between draft writes to the bridge. Slider drags update
// the UI on every pointer move, but bridge writes are throttled to this rate
// with a trailing write so the final value is always sent.
const SAVE_THROTTLE_MS = 150;

// Human-readable copy for the raw capture_status tokens from the backend.
const CAPTURE_STATUS_COPY = {
  capturing: "Press a key...",
  done: "Key captured.",
  cancelled: "Capture cancelled.",
  timeout: "Capture timed out.",
};

function TitleBar({ onOpenPalette, bridge }) {
  const t = useTokens();
  return (
    <div
      style={{
        height: 34,
        display: "flex",
        alignItems: "center",
        padding: "0 6px 0 12px",
        gap: 10,
        background: t.sidebar,
        borderBottom: `1px solid ${t.border}`,
      }}
    >
      <div
        style={{
          width: 14,
          height: 14,
          borderRadius: Math.min(t.radius, 3),
          background: t.accent,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: t.accentOn,
          fontSize: 9,
          fontWeight: 700,
        }}
      >
        V
      </div>
      <div style={{ fontSize: 12, fontWeight: 500, color: t.text }}>Virelo</div>

      <button
        onClick={onOpenPalette}
        style={{
          marginLeft: 14,
          display: "flex",
          alignItems: "center",
          gap: 8,
          height: 22,
          padding: "0 8px 0 8px",
          background: t.isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.035)",
          border: `1px solid ${t.border}`,
          borderRadius: t.radius,
          color: t.textDim,
          fontSize: 11.5,
          cursor: "pointer",
          fontFamily: "inherit",
          minWidth: 220,
        }}
      >
        <Icon name="search" size={11} />
        <span style={{ flex: 1, textAlign: "left" }}>Search or jump to...</span>
        <span style={{ fontFamily: t.mono, fontSize: 10, opacity: 0.7 }}>
          Ctrl K
        </span>
      </button>

      <div style={{ flex: 1 }} />
      <button
        onClick={() => bridge.setWindowCommand("minimize", () => {})}
        style={{
          width: 28,
          height: 26,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: t.textDim,
          fontSize: 10,
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = t.hover)}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {"—"}
      </button>
      <button
        onClick={() => bridge.setWindowCommand("close", () => {})}
        style={{
          width: 28,
          height: 26,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: t.textDim,
          fontSize: 10,
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "#e81123")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {"x"}
      </button>
    </div>
  );
}

function NavItem({ icon, label, active, onClick, badge, mode }) {
  const t = useTokens();
  const [hover, setHover] = React.useState(false);
  const iconsOnly = mode === "icons";
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={iconsOnly ? label : undefined}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 10,
        height: 30,
        padding: iconsOnly ? "0" : "0 10px",
        justifyContent: iconsOnly ? "center" : "flex-start",
        borderRadius: t.radius,
        background: active ? t.surface : hover ? t.hover : "transparent",
        border: active ? `1px solid ${t.border}` : "1px solid transparent",
        color: active ? t.text : t.textDim,
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        cursor: "pointer",
        textAlign: "left",
        fontFamily: "inherit",
        boxShadow: active ? t.shadow : "none",
        transition: "background .1s",
      }}
    >
      <span
        style={{
          width: 14,
          display: "flex",
          justifyContent: "center",
          opacity: active ? 1 : 0.75,
        }}
      >
        <Icon name={icon} />
      </span>
      {!iconsOnly && <span style={{ flex: 1 }}>{label}</span>}
      {!iconsOnly && badge && <Badge tone="accent">{badge}</Badge>}
    </button>
  );
}

function Sidebar({ nav, setNav, app, mode }) {
  const t = useTokens();
  if (mode === "hidden") return null;
  const iconsOnly = mode === "icons";
  const width = iconsOnly ? 52 : 208;
  return (
    <div
      style={{
        width,
        background: t.sidebar,
        borderRight: `1px solid ${t.border}`,
        padding: iconsOnly ? "10px 6px" : "14px 10px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        transition: "width .18s",
      }}
    >
      {!iconsOnly && (
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            color: t.textMuted,
            textTransform: "uppercase",
            letterSpacing: 0.8,
            padding: "8px 10px 6px",
          }}
        >
          Settings
        </div>
      )}
      <NavItem
        icon="snap"
        label="Window snap"
        active={nav === "snap"}
        onClick={() => setNav("snap")}
        badge={app.snapEnabled ? "ON" : null}
        mode={mode}
      />
      <NavItem
        icon="folder"
        label="Explorer"
        active={nav === "exp"}
        onClick={() => setNav("exp")}
        mode={mode}
      />
      <NavItem
        icon="keyb"
        label="Shortcuts"
        active={nav === "keys"}
        onClick={() => setNav("keys")}
        mode={mode}
      />
      <div style={{ height: 10 }} />
      {!iconsOnly && (
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            color: t.textMuted,
            textTransform: "uppercase",
            letterSpacing: 0.8,
            padding: "8px 10px 6px",
          }}
        >
          App
        </div>
      )}
      <NavItem
        icon="general"
        label="General"
        active={nav === "gen"}
        onClick={() => setNav("gen")}
        mode={mode}
      />
      <NavItem
        icon="about"
        label="About"
        active={nav === "about"}
        onClick={() => setNav("about")}
        mode={mode}
      />
      <div style={{ flex: 1 }} />
      {!iconsOnly && (
        <div
          style={{
            padding: "10px 10px 4px",
            fontSize: 11,
            color: t.textMuted,
          }}
        >
          v{__APP_VERSION__}
        </div>
      )}
    </div>
  );
}

function Footer({ unsaved, onSave, onDiscard, statusMsg }) {
  const t = useTokens();
  return (
    <div
      style={{
        padding: "12px 24px",
        borderTop: `1px solid ${t.border}`,
        background: t.surface,
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      {statusMsg && (
        <span style={{ fontSize: 12, color: t.textDim }}>{statusMsg}</span>
      )}
      <div style={{ flex: 1 }} />
      {unsaved && (
        <>
          <div
            style={{
              fontSize: 12,
              color: t.textDim,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: 3,
                background: "#C99A2E",
              }}
            />
            Unsaved changes
          </div>
          <Button variant="secondary" onClick={onDiscard}>
            Discard
          </Button>
        </>
      )}
      <Button variant="primary" onClick={onSave}>
        Save changes
      </Button>
    </div>
  );
}

export function bridgeToState(settings) {
  return {
    snapEnabled: settings.enable_snap ?? true,
    snapKey: (settings.snap_key || "shift").toUpperCase(),
    restoreKey: (settings.restore_key || "ctrl").toUpperCase(),
    pressCount: settings.snap_presses ?? 3,
    interval: settings.snap_interval ?? 1050,
    width: settings.width_pct ?? 76,
    height: settings.height_pct ?? 76,
    gameMode: settings.game_mode_enabled ?? true,
    autoSize: settings.ex_auto_size ?? true,
    launchLogin: settings.run_at_startup ?? false,
    accent: settings.accent || "slate",
    density: settings.density || "cozy",
    minimizeToTray: settings.minimize_to_tray ?? true,
    themeMode: settings.theme || "system",
  };
}

export function stateToBridge(state) {
  return JSON.stringify({
    enable_snap: state.snapEnabled,
    snap_key: state.snapKey.toLowerCase(),
    restore_key: state.restoreKey.toLowerCase(),
    snap_presses: state.pressCount,
    snap_interval: state.interval,
    width_pct: state.width,
    height_pct: state.height,
    game_mode_enabled: state.gameMode,
    ex_auto_size: state.autoSize,
    run_at_startup: state.launchLogin,
    accent: state.accent,
    density: state.density,
    minimize_to_tray: state.minimizeToTray,
    theme: state.themeMode,
  });
}

export default function VireloApp({ bridge }) {
  const { tweaks } = useTheme();
  const t = useTokens();
  const [nav, setNav] = React.useState("snap");
  const [palette, setPalette] = React.useState(false);
  const [state, setState] = React.useState({
    snapEnabled: true,
    snapKey: "SHIFT",
    restoreKey: "CTRL",
    pressCount: 3,
    interval: 1050,
    width: 76,
    height: 76,
    gameMode: true,
    autoSize: true,
    launchLogin: true,
    accent: "slate",
    density: "cozy",
    minimizeToTray: true,
    themeMode: "system",
  });
  const [unsaved, setUnsaved] = React.useState(false);
  const [statusMsg, setStatusMsg] = React.useState("");

  // Footer status helper. Shows a message and clears it after timeoutMs
  // milliseconds; a timeout of 0 keeps the message until it is replaced.
  const statusTimer = React.useRef(null);
  const showStatus = React.useCallback((message, timeoutMs = 0) => {
    if (statusTimer.current) {
      clearTimeout(statusTimer.current);
      statusTimer.current = null;
    }
    setStatusMsg(message);
    if (timeoutMs > 0) {
      statusTimer.current = setTimeout(() => setStatusMsg(""), timeoutMs);
    }
  }, []);
  React.useEffect(
    () => () => {
      if (statusTimer.current) clearTimeout(statusTimer.current);
    },
    [],
  );

  // Load initial settings from bridge
  React.useEffect(() => {
    bridge.get_settings((json) => {
      try {
        const r = JSON.parse(json);
        if (r.ok && r.data) {
          setState(bridgeToState(r.data));
        }
      } catch (e) {
        console.error("[app] Failed to parse initial settings:", e);
      }
    });

    bridge.settings_changed.connect((json) => {
      try {
        const settings = JSON.parse(json);
        setState(bridgeToState(settings));
      } catch (e) {
        console.error("[app] Failed to parse settings_changed:", e);
      }
    });

    bridge.dirty_changed.connect((isDirty) => {
      setUnsaved(isDirty);
    });

    // Subscribe to snap status messages, honoring the backend timeout.
    bridge.snap_status.connect((message, timeoutMs) => {
      showStatus(
        message,
        typeof timeoutMs === "number" && timeoutMs > 0 ? timeoutMs : 3000,
      );
    });

    // Map raw capture tokens to readable copy. Terminal states clear after
    // three seconds; the in-progress state persists until it resolves.
    bridge.capture_status.connect((status) => {
      const message = CAPTURE_STATUS_COPY[status] || status;
      showStatus(message, status === "capturing" ? 0 : 3000);
    });

    // Folder view operations report completion through views_status. Guard
    // the connect so a backend without the signal does not crash the UI.
    if (bridge.views_status) {
      bridge.views_status.connect((message, timeoutMs) => {
        showStatus(
          message,
          typeof timeoutMs === "number" && timeoutMs > 0 ? timeoutMs : 3000,
        );
      });
    }
  }, [bridge, showStatus]);

  // Mirror of the latest state so `set` can compute the next full snapshot
  // without calling the bridge inside the setState updater, which must stay
  // pure.
  const stateRef = React.useRef(state);
  React.useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Throttled draft writes: the first write in a burst goes out immediately,
  // later writes coalesce into one trailing write per SAVE_THROTTLE_MS
  // window, so the final value in a burst is always sent.
  const saveTimer = React.useRef(null);
  const pendingSave = React.useRef(null);
  const lastSaveAt = React.useRef(0);

  const sendSave = React.useCallback(
    (next) => {
      lastSaveAt.current = Date.now();
      bridge.save_settings(stateToBridge(next), (result) => {
        try {
          const r = JSON.parse(result);
          if (!r.ok) {
            console.error("[app] save_settings failed:", r.error);
            showStatus(`Save failed: ${r.error}`, 5000);
          }
        } catch (e) {
          console.error("[app] Failed to parse save_settings result:", e);
        }
      });
    },
    [bridge, showStatus],
  );

  const set = React.useCallback(
    (p) => {
      const next = { ...stateRef.current, ...p };
      stateRef.current = next;
      setState(next);
      pendingSave.current = next;
      if (saveTimer.current) return; // A trailing write is already scheduled.
      const elapsed = Date.now() - lastSaveAt.current;
      if (elapsed >= SAVE_THROTTLE_MS) {
        pendingSave.current = null;
        sendSave(next);
      } else {
        saveTimer.current = setTimeout(() => {
          saveTimer.current = null;
          const queued = pendingSave.current;
          pendingSave.current = null;
          if (queued) sendSave(queued);
        }, SAVE_THROTTLE_MS - elapsed);
      }
    },
    [sendSave],
  );

  // Cancel any scheduled trailing write and drop the queued value. Save,
  // discard, and reset must call this (or flushPendingSave) first so a stale
  // throttled write cannot fire after the action and resurrect old state.
  const cancelPendingSave = React.useCallback(() => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    pendingSave.current = null;
  }, []);

  // Send any queued trailing write immediately so the bridge draft reflects
  // the latest UI state before a commit.
  const flushPendingSave = React.useCallback(() => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    const queued = pendingSave.current;
    pendingSave.current = null;
    if (queued) sendSave(queued);
  }, [sendSave]);

  // Flush any queued draft write on unmount so no change is lost.
  React.useEffect(() => () => flushPendingSave(), [flushPendingSave]);

  const handleSave = () => {
    // Push any queued draft write first; bridge calls are handled in order,
    // so the commit below operates on the latest state.
    flushPendingSave();
    bridge.commit_draft((result) => {
      try {
        const r = JSON.parse(result);
        if (!r.ok) {
          console.error("[app] commit_draft failed:", r.error);
          showStatus(`Save failed: ${r.error}`, 5000);
        }
      } catch (e) {
        console.error("[app] Failed to parse commit_draft result:", e);
        showStatus("Save failed: invalid response from the backend.", 5000);
      }
    });
  };

  const handleDiscard = () => {
    // Drop any queued draft write so it cannot re-dirty the settings right
    // after the discard lands.
    cancelPendingSave();
    bridge.discard_draft((result) => {
      try {
        const r = JSON.parse(result);
        if (!r.ok) {
          console.error("[app] discard_draft failed:", r.error);
          showStatus(`Discard failed: ${r.error}`, 5000);
        }
      } catch (e) {
        console.error("[app] Failed to parse discard_draft result:", e);
        showStatus("Discard failed: invalid response from the backend.", 5000);
      }
    });
  };

  const handleReset = () => {
    // Drop any queued draft write so it cannot overwrite the defaults that
    // the reset is about to install.
    cancelPendingSave();
    bridge.reset_defaults((json) => {
      try {
        const r = JSON.parse(json);
        if (r.ok && r.data) {
          setState(bridgeToState(r.data));
        }
      } catch (e) {
        console.error("[app] Failed to parse reset_defaults result:", e);
      }
    });
  };

  const handleTestSnap = () => {
    bridge.test_snap((result) => {
      try {
        const r = JSON.parse(result);
        // On success the backend reports through snap_status, so nothing
        // overwrites that message here.
        if (!r.ok) {
          showStatus(`Test snap failed: ${r.error}`, 5000);
        }
      } catch (e) {
        console.error("[app] Failed to parse test_snap result:", e);
      }
    });
  };

  const app = {
    ...state,
    set,
    onTestSnap: handleTestSnap,
    onReset: handleReset,
    bridge,
    showStatus,
  };

  // Ctrl+K to toggle command palette
  React.useEffect(() => {
    const on = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((o) => !o);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  const Page = {
    snap: SnapPage,
    exp: ExplorerPage,
    keys: ShortcutsPage,
    gen: GeneralPage,
    about: AboutPage,
  }[nav];

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: t.bg,
        color: t.text,
        fontFamily: t.font,
        fontSize: t.fontBase,
        letterSpacing: -0.05,
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      <TitleBar onOpenPalette={() => setPalette(true)} bridge={bridge} />
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Sidebar
          nav={nav}
          setNav={setNav}
          app={app}
          mode={tweaks.sidebarMode}
        />
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: `${t.cardPad + 8}px ${t.cardPad + 14}px ${t.cardPad + 8}px`,
          }}
        >
          <Page app={app} />
          <div style={{ height: 30 }} />
        </div>
      </div>
      <Footer
        unsaved={unsaved}
        onSave={handleSave}
        onDiscard={handleDiscard}
        statusMsg={statusMsg}
      />
      <CommandPalette
        open={palette}
        onClose={() => setPalette(false)}
        app={app}
        setNav={setNav}
        onTestSnap={handleTestSnap}
        onSave={handleSave}
      />
    </div>
  );
}
