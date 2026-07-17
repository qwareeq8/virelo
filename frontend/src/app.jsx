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
const TRANSACTION_KEY = "__vireloTransaction";
const STATE_ENCODERS = {
  snapEnabled: ["enable_snap", (value) => value],
  snapKey: ["snap_key", (value) => value.toLowerCase()],
  restoreKey: ["restore_key", (value) => value.toLowerCase()],
  pressCount: ["snap_presses", (value) => value],
  interval: ["snap_interval", (value) => value],
  width: ["width_pct", (value) => value],
  height: ["height_pct", (value) => value],
  gameMode: ["game_mode_enabled", (value) => value],
  autoSize: ["ex_auto_size", (value) => value],
  launchLogin: ["run_at_startup", (value) => value],
  accent: ["accent", (value) => value],
  density: ["density", (value) => value],
  minimizeToTray: ["minimize_to_tray", (value) => value],
  themeMode: ["theme", (value) => value],
};
const PAGE_COMPONENTS = {
  snap: SnapPage,
  exp: ExplorerPage,
  keys: ShortcutsPage,
  gen: GeneralPage,
  about: AboutPage,
};

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
        background: t.sidebar,
        borderBottom: `1px solid ${t.border}`,
      }}
    >
      <div
        style={{
          width: 320,
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
          paddingLeft: 12,
          flexShrink: 0,
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
        <div style={{ fontSize: 12, fontWeight: 500, color: t.text }}>
          Virelo
        </div>

        <button
          aria-label="Search or jump to commands"
          onClick={onOpenPalette}
          style={{
            marginLeft: 14,
            display: "flex",
            alignItems: "center",
            gap: 8,
            height: 22,
            padding: "0 8px",
            background: t.isDark
              ? "rgba(255,255,255,0.04)"
              : "rgba(0,0,0,0.035)",
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
          <span style={{ flex: 1, textAlign: "left" }}>
            Search or jump to...
          </span>
          <span style={{ fontFamily: t.mono, fontSize: 10, opacity: 0.7 }}>
            Ctrl K
          </span>
        </button>
      </div>

      <div style={{ flex: 1 }} />
      <div
        style={{
          width: 72,
          display: "flex",
          alignItems: "center",
          gap: 10,
          paddingRight: 6,
          flexShrink: 0,
        }}
      >
        <button
          aria-label="Minimize Virelo"
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
          onMouseLeave={(e) =>
            (e.currentTarget.style.background = "transparent")
          }
        >
          {"—"}
        </button>
        <button
          aria-label="Close Virelo"
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
          onMouseLeave={(e) =>
            (e.currentTarget.style.background = "transparent")
          }
        >
          {"x"}
        </button>
      </div>
    </div>
  );
}

function NavItem({ icon, label, active, onClick, badge, mode }) {
  const t = useTokens();
  const [hover, setHover] = React.useState(false);
  const iconsOnly = mode === "icons";
  return (
    <button
      aria-current={active ? "page" : undefined}
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
    <nav
      aria-label="Settings pages"
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
    </nav>
  );
}

function Footer({ unsaved, saving, onSave, onDiscard, statusMsg }) {
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
        <span
          role="status"
          aria-live="polite"
          style={{ fontSize: 12, color: t.textDim }}
        >
          {statusMsg}
        </span>
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
      <Button variant="primary" onClick={onSave} disabled={!unsaved || saving}>
        Save changes
      </Button>
    </div>
  );
}

/** Convert backend settings keys and defaults into frontend state. */
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

/** Serialize a frontend state patch for the backend bridge. */
export function stateToBridge(state) {
  const payload = {};
  for (const [key, value] of Object.entries(state)) {
    const encoder = STATE_ENCODERS[key];
    if (encoder && value !== undefined) {
      payload[encoder[0]] = encoder[1](value);
    }
  }
  return JSON.stringify(payload);
}

export default function VireloApp({ bridge, initialSettings = null }) {
  const { tweaks, setTweaks } = useTheme();
  const t = useTokens();
  const [nav, setNav] = React.useState("snap");
  const [palette, setPalette] = React.useState(false);
  const [state, setState] = React.useState(() =>
    bridgeToState(initialSettings ?? {}),
  );
  const [unsaved, setUnsaved] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [statusMsg, setStatusMsg] = React.useState("");
  const [captureActive, setCaptureActive] = React.useState(false);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [settingsHydrated, setSettingsHydrated] = React.useState(
    initialSettings !== null,
  );
  const stateRef = React.useRef(state);
  const dirtyRevisions = React.useRef(new Map());
  const nextRevision = React.useRef(1);
  const backendDirty = React.useRef(false);
  const backendState = React.useRef(
    initialSettings !== null ? bridgeToState(initialSettings) : null,
  );
  const expectedSettingsSignals = React.useRef(new Map());
  const nextTransaction = React.useRef(1);
  const operationTail = React.useRef(Promise.resolve());
  const saveTimer = React.useRef(null);
  const pendingSave = React.useRef({});
  const lastSaveAt = React.useRef(0);
  const mounted = React.useRef(true);
  const contentRef = React.useRef(null);

  const refreshUnsaved = React.useCallback(() => {
    if (mounted.current) {
      setUnsaved(backendDirty.current || dirtyRevisions.current.size > 0);
    }
  }, []);

  const removePendingKey = React.useCallback((key) => {
    if (!(key in pendingSave.current)) return;
    const next = { ...pendingSave.current };
    delete next[key];
    pendingSave.current = next;
  }, []);

  const applyIncomingSettings = React.useCallback(
    (settings, context = null) => {
      const incoming = bridgeToState(settings);
      const previousBackend = backendState.current;
      backendState.current = incoming;
      const next = { ...incoming };

      if (context?.type === "stage") {
        for (const [key, operationRevision] of context.revisions ?? []) {
          if (dirtyRevisions.current.get(key) !== operationRevision) {
            next[key] = stateRef.current[key];
          }
        }
      }

      for (const [key, revision] of dirtyRevisions.current) {
        const localValue = stateRef.current[key];
        if (context?.type === "stage" || context?.type === "commit") {
          // Full-state echoes from our own draft/commit calls can contain an
          // older value for a different locally edited key. Preserve every
          // local edit until the operation callback acknowledges its revision.
          next[key] = localValue;
          continue;
        }
        if (context?.type === "discard" || context?.type === "reset") {
          const operationRevision = context.revisions?.get(key);
          if (
            operationRevision !== undefined &&
            revision <= operationRevision
          ) {
            dirtyRevisions.current.delete(key);
            removePendingKey(key);
          } else {
            next[key] = localValue;
          }
          continue;
        }

        // A signal with no matching frontend operation came from an immediate
        // backend action such as Ctrl+T or a tray toggle. Only keys that
        // actually changed in the backend snapshot supersede a local edit;
        // unrelated unsent edits remain intact.
        const changedExternally =
          previousBackend !== null &&
          !Object.is(incoming[key], previousBackend[key]);
        if (changedExternally) {
          dirtyRevisions.current.delete(key);
          removePendingKey(key);
        } else {
          next[key] = localValue;
        }
      }

      stateRef.current = next;
      if (mounted.current) setState(next);
      refreshUnsaved();
    },
    [refreshUnsaved, removePendingKey],
  );

  const enqueueOperation = React.useCallback((operation) => {
    const result = operationTail.current.then(operation, operation);
    operationTail.current = result.catch(() => undefined);
    return result;
  }, []);

  const callBridge = React.useCallback(
    (method, args = [], signalContext = null) =>
      new Promise((resolve) => {
        const transactionId = signalContext
          ? `virelo-${Date.now()}-${nextTransaction.current++}`
          : null;
        if (transactionId) {
          expectedSettingsSignals.current.set(transactionId, signalContext);
        }

        const callArgs = [...args];
        if (
          transactionId &&
          [
            "save_settings",
            "commit_draft",
            "discard_draft",
            "reset_defaults",
          ].includes(method)
        ) {
          callArgs.push(transactionId);
        }

        const removeExpected = () => {
          if (transactionId) {
            expectedSettingsSignals.current.delete(transactionId);
          }
        };
        const finish = (rawResult) => {
          let result;
          try {
            result = JSON.parse(rawResult);
            if (!result || typeof result !== "object") {
              throw new Error("The response is not a JSON object.");
            }
          } catch (error) {
            result = {
              ok: false,
              error: `Invalid response from ${method}: ${error.message}`,
            };
          }
          if (!result.ok) removeExpected();
          resolve(result);
        };

        try {
          if (typeof bridge[method] !== "function") {
            throw new Error(`Backend method "${method}" is unavailable.`);
          }
          bridge[method](...callArgs, finish);
        } catch (error) {
          removeExpected();
          resolve({
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }),
    [bridge],
  );

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
  React.useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Load initial settings and subscribe to backend signals.
  React.useEffect(() => {
    let active = true;
    if (initialSettings === null) {
      bridge.get_settings((json) => {
        if (!active) return;
        try {
          const response = JSON.parse(json);
          if (response?.ok && response.data) {
            applyIncomingSettings(response.data, { type: "stage" });
            setSettingsHydrated(true);
          } else {
            const detail = response?.error ? ` ${response.error}` : "";
            showStatus(`Settings could not be loaded.${detail}`, 5000);
          }
        } catch (error) {
          console.error("[app] Failed to parse initial settings:", error);
          showStatus("Settings could not be loaded; defaults are shown.", 5000);
        }
      });
    }

    const onSettingsChanged = (json) => {
      try {
        const settings = JSON.parse(json);
        const transactionId = settings[TRANSACTION_KEY];
        delete settings[TRANSACTION_KEY];
        const context = transactionId
          ? expectedSettingsSignals.current.get(transactionId)
          : null;
        if (transactionId)
          expectedSettingsSignals.current.delete(transactionId);
        applyIncomingSettings(settings, context ?? null);
      } catch (error) {
        console.error("[app] Failed to parse settings_changed:", error);
      }
    };

    const onDirtyChanged = (isDirty) => {
      backendDirty.current = isDirty;
      refreshUnsaved();
    };

    const onSnapStatus = (message, timeoutMs) => {
      showStatus(
        message,
        typeof timeoutMs === "number" && timeoutMs >= 0 ? timeoutMs : 3000,
      );
    };

    const onCaptureStatus = (status) => {
      setCaptureActive(status === "capturing");
      const message = CAPTURE_STATUS_COPY[status] || status;
      showStatus(message, status === "capturing" ? 0 : 3000);
    };

    const onViewsStatus = (message, timeoutMs) => {
      showStatus(
        message,
        typeof timeoutMs === "number" && timeoutMs >= 0 ? timeoutMs : 3000,
      );
    };

    bridge.settings_changed.connect(onSettingsChanged);
    bridge.dirty_changed.connect(onDirtyChanged);
    bridge.snap_status.connect(onSnapStatus);
    bridge.capture_status.connect(onCaptureStatus);
    bridge.views_status?.connect(onViewsStatus);

    return () => {
      active = false;
      bridge.settings_changed.disconnect?.(onSettingsChanged);
      bridge.dirty_changed.disconnect?.(onDirtyChanged);
      bridge.snap_status.disconnect?.(onSnapStatus);
      bridge.capture_status.disconnect?.(onCaptureStatus);
      bridge.views_status?.disconnect?.(onViewsStatus);
    };
  }, [
    applyIncomingSettings,
    bridge,
    initialSettings,
    refreshUnsaved,
    showStatus,
  ]);

  // Mirror of the latest state so `set` can compute the next local snapshot
  // without calling the bridge inside the setState updater, which must stay
  // pure.
  React.useEffect(() => {
    stateRef.current = state;
  }, [state]);

  React.useEffect(() => {
    if (!settingsHydrated) return;
    setTweaks({ accent: state.accent, density: state.density });
  }, [setTweaks, settingsHydrated, state.accent, state.density]);

  // Throttled draft writes: the first write in a burst goes out immediately,
  // later writes coalesce into one trailing write per SAVE_THROTTLE_MS
  // window, so the final value in a burst is always sent.
  const takePendingSave = React.useCallback(() => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    const queued = pendingSave.current;
    pendingSave.current = {};
    return queued;
  }, []);

  const queueDraftEntries = React.useCallback(
    (entries, reportErrors = true) => {
      if (Object.keys(entries).length === 0)
        return Promise.resolve({ ok: true });
      lastSaveAt.current = Date.now();
      return enqueueOperation(async () => {
        const patch = {};
        const revisions = new Map();
        for (const [key, entry] of Object.entries(entries)) {
          if (dirtyRevisions.current.get(key) === entry.revision) {
            patch[key] = entry.value;
            revisions.set(key, entry.revision);
          }
        }
        if (Object.keys(patch).length === 0) return { ok: true };
        const result = await callBridge(
          "save_settings",
          [stateToBridge(patch)],
          { type: "stage", revisions },
        );
        if (!result.ok && reportErrors) {
          console.error("[app] save_settings failed:", result.error);
          showStatus(`Save failed: ${result.error}`, 5000);
        }
        return result;
      });
    },
    [callBridge, enqueueOperation, showStatus],
  );

  const set = React.useCallback(
    (patch) => {
      const next = { ...stateRef.current, ...patch };
      const revision = nextRevision.current++;
      for (const [key, value] of Object.entries(patch)) {
        dirtyRevisions.current.set(key, revision);
        pendingSave.current[key] = { value, revision };
      }
      stateRef.current = next;
      setState(next);
      refreshUnsaved();
      if (saveTimer.current) return; // A trailing write is already scheduled.
      const elapsed = Date.now() - lastSaveAt.current;
      if (elapsed >= SAVE_THROTTLE_MS) {
        void queueDraftEntries(takePendingSave());
      } else {
        saveTimer.current = setTimeout(() => {
          saveTimer.current = null;
          void queueDraftEntries(takePendingSave());
        }, SAVE_THROTTLE_MS - elapsed);
      }
    },
    [queueDraftEntries, refreshUnsaved, takePendingSave],
  );

  // Flush any queued draft write on unmount so no change is lost.
  React.useEffect(
    () => () => {
      const queued = takePendingSave();
      void queueDraftEntries(queued, false);
    },
    [queueDraftEntries, takePendingSave],
  );

  const handleSave = () => {
    const revisions = new Map(dirtyRevisions.current);
    if (revisions.size === 0) return;
    takePendingSave();
    const patch = {};
    for (const key of revisions.keys()) patch[key] = stateRef.current[key];
    lastSaveAt.current = 0;
    setSaving(true);

    void enqueueOperation(async () => {
      const staged = await callBridge("save_settings", [stateToBridge(patch)], {
        type: "stage",
        revisions,
      });
      if (!staged.ok) {
        console.error("[app] save_settings failed:", staged.error);
        showStatus(`Save failed: ${staged.error}`, 5000);
        return false;
      }
      const committed = await callBridge("commit_draft", [], {
        type: "commit",
        revisions,
      });
      if (!committed.ok) {
        console.error("[app] commit_draft failed:", committed.error);
        showStatus(`Save failed: ${committed.error}`, 5000);
        return false;
      }

      backendDirty.current = false;
      for (const [key, revision] of revisions) {
        if (dirtyRevisions.current.get(key) === revision) {
          dirtyRevisions.current.delete(key);
        }
      }
      refreshUnsaved();
      showStatus(
        dirtyRevisions.current.size === 0
          ? "Changes saved."
          : "Earlier changes saved; newer changes remain.",
        3000,
      );
      return true;
    }).finally(() => {
      if (mounted.current) setSaving(false);
    });
  };

  const handleDiscard = () => {
    const revisions = new Map(dirtyRevisions.current);
    takePendingSave();
    lastSaveAt.current = 0;
    void enqueueOperation(async () => {
      const context = { type: "discard", revisions };
      const result = await callBridge("discard_draft", [], context);
      if (!result.ok) {
        console.error("[app] discard_draft failed:", result.error);
        showStatus(`Discard failed: ${result.error}`, 5000);
        refreshUnsaved();
        return;
      }
      let data = result.data;
      if (!data) {
        const current = await callBridge("get_settings");
        if (current.ok) data = current.data;
      }
      if (data) applyIncomingSettings(data, context);
      backendDirty.current = false;
      for (const [key, revision] of revisions) {
        if (dirtyRevisions.current.get(key) === revision) {
          dirtyRevisions.current.delete(key);
        }
      }
      refreshUnsaved();
    });
  };

  const handleReset = () => {
    const revisions = new Map(dirtyRevisions.current);
    takePendingSave();
    lastSaveAt.current = 0;
    void enqueueOperation(async () => {
      const context = { type: "reset", revisions };
      const result = await callBridge("reset_defaults", [], context);
      if (!result.ok) {
        console.error("[app] reset_defaults failed:", result.error);
        showStatus(`Reset failed: ${result.error}`, 5000);
        refreshUnsaved();
        return;
      }
      if (result.data) applyIncomingSettings(result.data, context);
      backendDirty.current = false;
      for (const [key, revision] of revisions) {
        if (dirtyRevisions.current.get(key) === revision) {
          dirtyRevisions.current.delete(key);
        }
      }
      refreshUnsaved();
    });
  };

  const handleTestSnap = () => {
    bridge.test_snap((result) => {
      try {
        const response = JSON.parse(result);
        // On success the backend reports through snap_status, so nothing
        // overwrites that message here.
        if (!response?.ok) {
          showStatus(
            `Test snap failed: ${response?.error || "The backend rejected the request."}`,
            5000,
          );
        }
      } catch (error) {
        console.error("[app] Failed to parse test_snap result:", error);
        showStatus(
          "Test snap failed because the backend returned an invalid response.",
          5000,
        );
      }
    });
  };

  const updateModalOpen = React.useCallback((isOpen) => {
    setModalOpen(Boolean(isOpen));
  }, []);

  const updateNativeShortcutGuard = React.useCallback(
    (isGuarded) => {
      bridge.set_modal_open?.(Boolean(isGuarded), (rawResult) => {
        try {
          const result = JSON.parse(rawResult);
          if (!result?.ok) {
            const detail = result?.error || "The backend rejected the request.";
            console.error("[app] set_modal_open failed:", detail);
            showStatus(`Modal shortcut guard failed: ${detail}`, 5000);
          }
        } catch (error) {
          console.error("[app] Invalid set_modal_open response:", error);
          showStatus(
            "Modal shortcut guard failed because the backend returned an invalid response.",
            5000,
          );
        }
      });
    },
    [bridge, showStatus],
  );

  React.useEffect(() => {
    updateNativeShortcutGuard(modalOpen || palette);
  }, [modalOpen, palette, updateNativeShortcutGuard]);

  React.useEffect(
    () => () => {
      bridge.set_modal_open?.(false, () => {});
    },
    [bridge],
  );

  const app = {
    ...state,
    unsaved,
    set,
    onTestSnap: handleTestSnap,
    onReset: handleReset,
    bridge,
    showStatus,
    captureActive,
    setCaptureActive,
    setModalOpen: updateModalOpen,
  };

  // Keep temporary surfaces mutually exclusive with key capture and modals.
  React.useEffect(() => {
    if (captureActive || modalOpen) setPalette(false);
  }, [captureActive, modalOpen]);

  // Toggle the command palette with Ctrl+K.
  React.useEffect(() => {
    const on = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (captureActive || modalOpen) return;
        setPalette((o) => !o);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [captureActive, modalOpen]);

  React.useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [nav]);

  const Page = PAGE_COMPONENTS[nav];

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
      <TitleBar
        onOpenPalette={() => {
          if (!captureActive && !modalOpen) setPalette(true);
        }}
        bridge={bridge}
      />
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Sidebar
          nav={nav}
          setNav={setNav}
          app={app}
          mode={tweaks.sidebarMode}
        />
        <main
          ref={contentRef}
          tabIndex={-1}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: `${t.cardPad + 8}px ${t.cardPad + 14}px ${t.cardPad + 8}px`,
          }}
        >
          <Page app={app} />
          <div style={{ height: 30 }} />
        </main>
      </div>
      <Footer
        unsaved={unsaved}
        saving={saving}
        onSave={handleSave}
        onDiscard={handleDiscard}
        statusMsg={statusMsg}
      />
      <CommandPalette
        open={palette && !captureActive && !modalOpen}
        onClose={() => setPalette(false)}
        app={app}
        setNav={setNav}
        onTestSnap={handleTestSnap}
        onSave={handleSave}
      />
    </div>
  );
}
