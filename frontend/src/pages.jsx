// Pages: Window Snap, Explorer, Shortcuts, General, About.
// Each takes an `app` object with state/setters so Tweaks + palette can
// deep-link into specific settings.

import React from "react";
import { useTokens, useTheme, ACCENTS } from "./theme.jsx";
import {
  Toggle,
  Button,
  Card,
  Row,
  Segmented,
  Stepper,
  Slider,
  Kbd,
} from "./primitives.jsx";
import { Icon } from "./icons.jsx";

// License text shown inline on the About page. Kept in sync with the
// repository LICENSE file.
const MIT_LICENSE = `MIT License

Copyright (c) 2024 Yusuf Qwareeq

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`;

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useModalFocus(open, onClose) {
  const dialogRef = React.useRef(null);
  const returnFocusRef = React.useRef(null);

  React.useEffect(() => {
    if (!open) return undefined;
    returnFocusRef.current = document.activeElement;
    const dialog = dialogRef.current;
    const focusable = () =>
      Array.from(dialog?.querySelectorAll(FOCUSABLE_SELECTOR) || []);
    (focusable()[0] || dialog)?.focus();

    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      const previous = returnFocusRef.current;
      if (previous?.isConnected) previous.focus();
    };
  }, [onClose, open]);

  return dialogRef;
}

function KeyCapture({
  label,
  value,
  target,
  bridge,
  captureActive,
  setCaptureActive,
  showStatus,
}) {
  const t = useTokens();
  const [capturing, setCapturing] = React.useState(false);
  const btnRef = React.useRef(null);
  const capturingRef = React.useRef(false);

  React.useEffect(() => {
    capturingRef.current = capturing;
  }, [capturing]);

  React.useEffect(
    () => () => {
      if (capturingRef.current) {
        setCaptureActive?.(false);
        bridge.cancel_capture?.(() => {});
      }
    },
    [bridge, setCaptureActive],
  );

  React.useEffect(() => {
    const onStatus = (status) => {
      if (status === "done" || status === "cancelled" || status === "timeout") {
        setCapturing(false);
        setCaptureActive?.(false);
      }
    };
    bridge.capture_status.connect(onStatus);
    return () => bridge.capture_status.disconnect(onStatus);
  }, [bridge, setCaptureActive]);

  React.useEffect(() => {
    if (!capturing) return;
    // Tell the backend to release its global keyboard hook. Without this,
    // dismissing the capture UI leaves the hook active and the next key
    // pressed in any application is captured as the new binding.
    const cancelCapture = () => {
      if (bridge.cancel_capture) bridge.cancel_capture(() => {});
      setCapturing(false);
      setCaptureActive?.(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        cancelCapture();
      }
    };
    window.addEventListener("keydown", onKey);
    const onMouseDown = (event) => {
      if (btnRef.current && !btnRef.current.contains(event.target)) {
        cancelCapture();
      }
    };
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", onMouseDown);
    }, 50);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onMouseDown);
      clearTimeout(timer);
    };
  }, [capturing, bridge, setCaptureActive]);

  const handleClick = () => {
    if (capturing || captureActive) return;
    setCapturing(true);
    setCaptureActive?.(true);
    bridge.capture_key(target, (result) => {
      try {
        const response = JSON.parse(result);
        if (!response.ok) {
          setCapturing(false);
          setCaptureActive?.(false);
          showStatus?.(response.error || "Key capture could not start.", 3000);
        }
      } catch (error) {
        console.error("[capture] Failed to parse capture response:", error);
        setCapturing(false);
        setCaptureActive?.(false);
        showStatus?.("Key capture could not start.", 3000);
      }
    });
  };

  return (
    <button
      ref={btnRef}
      aria-label={`${label}: ${capturing ? "Press a key" : value}`}
      onClick={handleClick}
      disabled={captureActive && !capturing}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 64,
        height: 28,
        padding: "0 12px",
        background: t.isDark ? "rgba(255,255,255,0.06)" : "#fff",
        border: capturing ? `2px solid ${t.accent}` : `1px solid ${t.borderHi}`,
        borderRadius: 4,
        color: capturing ? t.accent : t.text,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.3,
        fontFamily: t.mono,
        cursor: captureActive && !capturing ? "not-allowed" : "pointer",
        opacity: captureActive && !capturing ? 0.55 : 1,
        boxShadow: t.isDark ? "none" : "0 1px 0 rgba(0,0,0,0.04)",
        transition: "border-color .15s, color .15s",
      }}
    >
      {capturing ? "Press a key..." : value}
    </button>
  );
}

function MonitorPreview({ width, height }) {
  const t = useTokens();
  const monitorWidth = 280;
  const monitorHeight = 170;
  const monitorPadding = 12;
  const innerWidth = monitorWidth - monitorPadding * 2;
  const innerHeight = monitorHeight - monitorPadding * 2;
  const windowWidth = (innerWidth * width) / 100;
  const windowHeight = (innerHeight * height) / 100;
  const windowLeft = monitorPadding + (innerWidth - windowWidth) / 2;
  const windowTop = monitorPadding + (innerHeight - windowHeight) / 2;

  // If the UI accent is too dark in light mode (slate), fall back to a sky
  // blue so the rect stays visible against the dark monitor. Otherwise use
  // the accent so the preview reflects the user's choice.
  const darkAccents = ["slate"];
  const { tweaks } = useTheme();
  const rectColor =
    !t.isDark && darkAccents.includes(tweaks.accent) ? "#8EC4FF" : t.accent;
  const monitorBg = t.isDark ? "#0C0C0E" : "#3B3833";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        padding: `${t.cardPad + 6}px ${t.cardPad}px ${t.cardPad + 4}px`,
        background: t.surface,
      }}
    >
      <div style={{ position: "relative" }}>
        <div
          style={{
            position: "absolute",
            top: -22,
            left: 0,
            right: 0,
            textAlign: "center",
            fontSize: 11,
            fontFamily: t.mono,
            color: t.textDim,
            fontWeight: 600,
            letterSpacing: 0.3,
          }}
        >
          {width}% × {height}%
        </div>
        <div
          style={{
            width: monitorWidth,
            height: monitorHeight,
            borderRadius: 6,
            background: monitorBg,
            border: `1px solid ${t.borderHi}`,
            position: "relative",
            overflow: "hidden",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
          }}
        >
          <svg
            width={monitorWidth}
            height={monitorHeight}
            style={{
              position: "absolute",
              inset: 0,
              opacity: 0.18,
              pointerEvents: "none",
            }}
          >
            <defs>
              <pattern
                id="mp-grid"
                width="20"
                height="20"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 20 0 L 0 0 0 20"
                  fill="none"
                  stroke="rgba(255,255,255,0.15)"
                  strokeWidth="0.5"
                />
              </pattern>
            </defs>
            <rect
              width={monitorWidth}
              height={monitorHeight}
              fill="url(#mp-grid)"
            />
          </svg>

          <div
            style={{
              position: "absolute",
              left: windowLeft,
              top: windowTop,
              width: windowWidth,
              height: windowHeight,
              background: `${rectColor}33`,
              border: `1.5px solid ${rectColor}`,
              borderRadius: 3,
              transition: "all .2s cubic-bezier(.2,.7,.3,1)",
              boxShadow: `0 0 16px ${rectColor}30`,
            }}
          >
            {windowHeight >= 22 && (
              <div
                style={{
                  height: 10,
                  background: `${rectColor}40`,
                  borderBottom: `1px solid ${rectColor}`,
                  borderRadius: "2px 2px 0 0",
                }}
              />
            )}
          </div>
        </div>
        <div
          style={{
            width: 70,
            height: 4,
            margin: "0 auto",
            background: t.borderHi,
            borderRadius: "0 0 3px 3px",
          }}
        />
        <div
          style={{
            width: 120,
            height: 2,
            margin: "0 auto",
            background: t.border,
            borderRadius: 2,
          }}
        />
      </div>
    </div>
  );
}

function SnapPage({ app }) {
  const t = useTokens();
  return (
    <Pg
      title="Window snap"
      subtitle="Configure snap/restore presets and the keyboard shortcuts that trigger them."
    >
      <Card>
        <Row
          label="Enable snap"
          description="Resize the foreground window with a keyboard shortcut."
        >
          <Toggle
            on={app.snapEnabled}
            onChange={(v) => app.set({ snapEnabled: v })}
          />
        </Row>
        <Row
          label="Game mode"
          description="Skip snapping while a fullscreen app is in focus."
          last
        >
          <Toggle
            on={app.gameMode}
            onChange={(v) => app.set({ gameMode: v })}
          />
        </Row>
      </Card>

      <Card
        title="Shortcut"
        subtitle="Press the key button to rebind. Tap the bound key repeatedly to trigger."
      >
        <Row label="Snap key">
          <KeyCapture
            label="Snap key"
            value={app.snapKey}
            target="snap"
            bridge={app.bridge}
            captureActive={app.captureActive}
            setCaptureActive={app.setCaptureActive}
            showStatus={app.showStatus}
          />
        </Row>
        <Row label="Restore key">
          <KeyCapture
            label="Restore key"
            value={app.restoreKey}
            target="restore"
            bridge={app.bridge}
            captureActive={app.captureActive}
            setCaptureActive={app.setCaptureActive}
            showStatus={app.showStatus}
          />
        </Row>
        <Row
          label="Press count"
          description="How many taps trigger the action."
        >
          <Stepper
            value={app.pressCount}
            onChange={(v) => app.set({ pressCount: v })}
            min={1}
            max={10}
          />
        </Row>
        <Row label="Interval" description="Maximum time between taps." last>
          <Stepper
            value={app.interval}
            onChange={(v) => app.set({ interval: v })}
            min={100}
            max={5000}
            step={50}
            suffix="ms"
          />
        </Row>
      </Card>

      <Card padding={false}>
        <div
          style={{
            padding: `${t.rowPad + 2}px ${t.cardPad}px`,
            borderBottom: `1px solid ${t.border}`,
            background: t.surface2,
            display: "flex",
            alignItems: "center",
          }}
        >
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: t.text,
                letterSpacing: -0.1,
              }}
            >
              Target size
            </div>
            <div style={{ fontSize: 12, color: t.textDim, marginTop: 2 }}>
              Snapped windows will match this fraction of the current display.
            </div>
          </div>
          <Button
            variant="ghost"
            icon={<Icon name="play" size={12} />}
            onClick={app.onTestSnap}
          >
            Test snap
          </Button>
        </div>
        <MonitorPreview width={app.width} height={app.height} />
        <div style={{ padding: `4px ${t.cardPad}px` }}>
          <Row label="Width" description={`${app.width}% of screen width`}>
            <Slider
              value={app.width}
              onChange={(v) => app.set({ width: v })}
              min={10}
              max={100}
            />
          </Row>
          <Row
            label="Height"
            description={`${app.height}% of screen height`}
            last
          >
            <Slider
              value={app.height}
              onChange={(v) => app.set({ height: v })}
              min={10}
              max={100}
            />
          </Row>
        </div>
      </Card>
    </Pg>
  );
}

function ExplorerPage({ app }) {
  const t = useTokens();
  const [confirmAction, setConfirmAction] = React.useState(null);
  const [busy, setBusy] = React.useState(null);
  const closeConfirm = React.useCallback(() => setConfirmAction(null), []);
  const confirmDialogRef = useModalFocus(Boolean(confirmAction), closeConfirm);

  React.useEffect(() => {
    const onViewsStatus = () => setBusy(null);
    app.bridge.views_status?.connect(onViewsStatus);
    return () => app.bridge.views_status?.disconnect?.(onViewsStatus);
  }, [app.bridge]);

  React.useEffect(() => {
    app.setModalOpen?.(Boolean(confirmAction));
    return () => app.setModalOpen?.(false);
  }, [app.setModalOpen, confirmAction]);

  const runViewsAction = (action) => {
    setConfirmAction(null);
    const method =
      action === "apply"
        ? app.bridge.apply_details_view
        : app.bridge.reset_folder_views;
    if (typeof method !== "function") {
      // The backend build in use does not expose the folder view slots yet.
      app.showStatus?.(
        "Folder view changes are not supported by this backend build.",
        5000,
      );
      return;
    }
    setBusy(action);
    const onResult = (result) => {
      try {
        const r = JSON.parse(result);
        if (r.ok) {
          app.showStatus?.(
            action === "apply"
              ? "Applying Details view. File Explorer will restart..."
              : "Resetting folder views. File Explorer will restart...",
            0,
          );
        } else {
          setBusy(null);
          app.showStatus?.(r.error || "Folder view update failed.", 5000);
        }
      } catch (error) {
        setBusy(null);
        console.error("[explorer] Failed to parse folder view result:", error);
        app.showStatus?.("Folder view update failed.", 5000);
      }
    };
    method(onResult);
  };

  const confirmCopy =
    confirmAction === "apply"
      ? {
          title: "Make Details the default?",
          body: "File Explorer will restart to apply the change. Finish any file copies, moves, or deletions first; open Explorer windows will close.",
          confirmLabel: "Apply and restart Explorer",
          confirmVariant: "primary",
        }
      : {
          title: "Reset folder views?",
          body: "This restores the Windows default view for every folder. Finish any file copies, moves, or deletions first; File Explorer will restart and open windows will close.",
          confirmLabel: "Reset and restart Explorer",
          confirmVariant: "danger",
        };

  return (
    <Pg
      title="Explorer"
      subtitle="Quality-of-life tweaks for File Explorer's Details view."
    >
      <Card>
        <Row
          label="Auto-size columns on folder change"
          description="Resize Details view columns to fit each time you navigate."
          last
        >
          <Toggle
            on={app.autoSize}
            onChange={(v) => app.set({ autoSize: v })}
          />
        </Row>
      </Card>

      <Card title="Default folder view">
        <div style={{ padding: `${t.rowPad}px 0` }}>
          <div
            style={{
              fontSize: 12.5,
              color: t.textDim,
              lineHeight: 1.5,
              maxWidth: 560,
            }}
          >
            Make Details the default view for every folder, the way WinSetView
            does. File Explorer restarts when this is applied.
          </div>
          <div
            style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}
          >
            <Button
              variant="primary"
              disabled={busy !== null}
              onClick={() => setConfirmAction("apply")}
            >
              {busy === "apply" ? "Working..." : "Make Details the default"}
            </Button>
            <Button
              variant="secondary"
              disabled={busy !== null}
              onClick={() => setConfirmAction("reset")}
            >
              {busy === "reset"
                ? "Working..."
                : "Reset folder views to Windows defaults"}
            </Button>
          </div>
        </div>
      </Card>

      {confirmAction && (
        <div
          onClick={closeConfirm}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            background: t.overlay,
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            ref={confirmDialogRef}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={confirmCopy.title}
            aria-describedby="explorer-view-confirm-description"
            style={{
              width: 360,
              background: t.surface,
              border: `1px solid ${t.borderHi}`,
              borderRadius: t.radius + 4,
              boxShadow:
                "0 20px 60px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.08)",
              padding: `${t.cardPad + 4}px ${t.cardPad}px`,
            }}
          >
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: t.text,
                marginBottom: 8,
              }}
            >
              {confirmCopy.title}
            </div>
            <div
              id="explorer-view-confirm-description"
              style={{
                fontSize: 13,
                color: t.textDim,
                lineHeight: 1.5,
                marginBottom: 20,
              }}
            >
              {confirmCopy.body}
            </div>
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <Button variant="secondary" onClick={closeConfirm}>
                Cancel
              </Button>
              <Button
                variant={confirmCopy.confirmVariant}
                onClick={() => runViewsAction(confirmAction)}
              >
                {confirmCopy.confirmLabel}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Pg>
  );
}

function ShortcutsPage({ app }) {
  const t = useTokens();
  const taps = app.pressCount === 1 ? "once" : `${app.pressCount} times`;
  // Restore is a modifier gesture: the restore key is HELD while the snap
  // key is tapped the configured number of times (see snap.py, which checks
  // keyboard.is_pressed(restore_key) when the press target is reached).
  const items = [
    {
      label: "Trigger snap",
      description: `Tap ${app.snapKey} ${taps}.`,
      keys: Array.from({ length: app.pressCount }, () => app.snapKey),
    },
    {
      label: "Restore last snap",
      description: `Hold ${app.restoreKey} while tapping ${app.snapKey} ${taps}.`,
      hold: app.restoreKey,
      keys: Array.from({ length: app.pressCount }, () => app.snapKey),
    },
    { label: "Command palette", keys: ["Ctrl", "K"] },
  ];
  return (
    <Pg
      title="Shortcuts"
      subtitle="Global keyboard shortcuts registered by Virelo."
    >
      <Card padding={false}>
        {items.map((item, index) => (
          <div
            key={item.label}
            style={{
              display: "flex",
              alignItems: "center",
              flexWrap: "wrap",
              rowGap: 8,
              padding: `${t.rowPad}px ${t.cardPad}px`,
              borderBottom:
                index < items.length - 1 ? `1px solid ${t.border}` : "none",
            }}
          >
            <div style={{ flex: "1 1 180px", minWidth: 0 }}>
              <div style={{ fontSize: 13, color: t.text }}>{item.label}</div>
              {item.description && (
                <div style={{ fontSize: 11.5, color: t.textDim, marginTop: 2 }}>
                  {item.description}
                </div>
              )}
            </div>
            <div
              style={{
                display: "flex",
                flex: "1 1 260px",
                flexWrap: "wrap",
                gap: 3,
                alignItems: "center",
                justifyContent: "flex-end",
                minWidth: 0,
              }}
            >
              {item.hold && (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                  }}
                >
                  <Kbd>{item.hold}</Kbd>
                  <span
                    style={{
                      color: t.textMuted,
                      fontSize: 10,
                      margin: "0 2px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    (hold)
                  </span>
                </span>
              )}
              {item.keys.map((key, keyIndex) => (
                <span
                  key={`${key}-${keyIndex}`}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                  }}
                >
                  {(keyIndex > 0 || item.hold) && (
                    <span
                      style={{
                        color: t.textMuted,
                        fontSize: 11,
                      }}
                    >
                      +
                    </span>
                  )}
                  <Kbd>{key}</Kbd>
                </span>
              ))}
            </div>
          </div>
        ))}
      </Card>
    </Pg>
  );
}

function GeneralPage({ app }) {
  const t = useTokens();
  const [confirmReset, setConfirmReset] = React.useState(false);
  const closeReset = React.useCallback(() => setConfirmReset(false), []);
  const resetDialogRef = useModalFocus(confirmReset, closeReset);

  React.useEffect(() => {
    app.setModalOpen?.(confirmReset);
    return () => app.setModalOpen?.(false);
  }, [app.setModalOpen, confirmReset]);

  return (
    <Pg title="General" subtitle="Application-wide preferences.">
      <Card title="Appearance">
        <Row
          label="Theme"
          description="Light or dark surfaces throughout the app."
        >
          <Segmented
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
            value={app.themeMode}
            onChange={(v) => app.set({ themeMode: v })}
          />
        </Row>
        <Row
          label="Accent color"
          description="Used for selection, toggles, and primary actions."
        >
          <div style={{ display: "flex", gap: 6 }}>
            {Object.entries(ACCENTS).map(([k, v]) => (
              <button
                key={k}
                aria-label={`${k[0].toUpperCase()}${k.slice(1)} accent`}
                aria-pressed={app.accent === k}
                onClick={() => app.set({ accent: k })}
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 11,
                  background: t.isDark ? v.dark : v.light,
                  border:
                    app.accent === k
                      ? `2px solid ${t.text}`
                      : `1px solid ${t.border}`,
                  cursor: "pointer",
                  padding: 0,
                }}
              />
            ))}
          </div>
        </Row>
        <Row
          label="Density"
          description="Controls spacing throughout the app."
          last
        >
          <Segmented
            options={[
              { value: "compact", label: "Compact" },
              { value: "cozy", label: "Cozy" },
              { value: "comfortable", label: "Comfortable" },
            ]}
            value={app.density}
            onChange={(v) => app.set({ density: v })}
          />
        </Row>
      </Card>

      <Card title="Startup">
        <Row
          label="Launch at login"
          description="Start Virelo when you sign in to Windows."
        >
          <Toggle
            on={app.launchLogin}
            onChange={(v) => app.set({ launchLogin: v })}
          />
        </Row>
        <Row
          label="Minimize to tray"
          description="Keep Virelo running in the notification area when closed."
          last
        >
          <Toggle
            on={app.minimizeToTray}
            onChange={(v) => app.set({ minimizeToTray: v })}
          />
        </Row>
      </Card>

      <Card title="Advanced">
        <Row
          label="Reset all settings"
          description="Restore every preference to its default value."
          last
        >
          <Button
            variant="danger"
            size="sm"
            onClick={() => setConfirmReset(true)}
          >
            Reset
          </Button>
        </Row>
      </Card>

      {confirmReset && (
        <div
          onClick={closeReset}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            background: t.overlay,
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            ref={resetDialogRef}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Reset all settings"
            aria-describedby="reset-settings-confirm-description"
            style={{
              width: 360,
              background: t.surface,
              border: `1px solid ${t.borderHi}`,
              borderRadius: t.radius + 4,
              boxShadow:
                "0 20px 60px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.08)",
              padding: `${t.cardPad + 4}px ${t.cardPad}px`,
            }}
          >
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: t.text,
                marginBottom: 8,
              }}
            >
              Reset all settings?
            </div>
            <div
              id="reset-settings-confirm-description"
              style={{
                fontSize: 13,
                color: t.textDim,
                lineHeight: 1.5,
                marginBottom: 20,
              }}
            >
              This will restore every preference to its default value. This
              cannot be undone.
            </div>
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <Button variant="secondary" onClick={closeReset}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  app.onReset();
                  setConfirmReset(false);
                }}
              >
                Reset
              </Button>
            </div>
          </div>
        </div>
      )}
    </Pg>
  );
}

function AboutPage() {
  const t = useTokens();
  const [showLicense, setShowLicense] = React.useState(false);
  const licenseId = React.useId();
  return (
    <Pg title="About" subtitle="Virelo, a tiny utility for snappier windows.">
      <Card padding={false}>
        <div
          style={{
            padding: `${t.cardPad + 4}px ${t.cardPad}px`,
            display: "flex",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: t.radius + 4,
              background: t.accent,
              color: t.accentOn,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 26,
              fontWeight: 700,
              letterSpacing: -1,
            }}
          >
            V
          </div>
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 18,
                fontWeight: 600,
                color: t.text,
                letterSpacing: -0.3,
              }}
            >
              Virelo
            </div>
            <div style={{ fontSize: 12.5, color: t.textDim, marginTop: 2 }}>
              Version {__APP_VERSION__}
            </div>
          </div>
        </div>
      </Card>
      <Card>
        <Row label="License" description="MIT" last={!showLicense}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowLicense((v) => !v)}
            aria-expanded={showLicense}
            aria-controls={licenseId}
            aria-label={`${showLicense ? "Hide" : "View"} MIT license`}
          >
            {showLicense ? "Hide" : "View"}
          </Button>
        </Row>
        {showLicense && (
          <div id={licenseId} style={{ padding: `${t.rowPad}px 0` }}>
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontFamily: t.mono,
                fontSize: 11,
                lineHeight: 1.6,
                color: t.textDim,
              }}
            >
              {MIT_LICENSE}
            </pre>
          </div>
        )}
      </Card>
    </Pg>
  );
}

function Pg({ title, subtitle, children }) {
  const t = useTokens();
  return (
    <div>
      <div style={{ marginBottom: t.sectionGap + 6 }}>
        <h1
          style={{
            margin: 0,
            fontSize: t.titleSize,
            fontWeight: 600,
            letterSpacing: -0.3,
            color: t.text,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <div
            style={{
              fontSize: 13,
              color: t.textDim,
              marginTop: 4,
              maxWidth: 560,
              lineHeight: 1.5,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
      <div
        style={{ display: "flex", flexDirection: "column", gap: t.sectionGap }}
      >
        {children}
      </div>
    </div>
  );
}

export {
  SnapPage,
  ExplorerPage,
  ShortcutsPage,
  GeneralPage,
  AboutPage,
  MonitorPreview,
  Pg,
};
