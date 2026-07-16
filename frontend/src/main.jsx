import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "./theme.jsx";
import VireloApp from "./app.jsx";
import { getBridge, getBridgeSync } from "./bridge.js";

/**
 * Inner component that renders AFTER bridge is ready.
 * This avoids the React hooks violation of calling useState after a conditional return.
 * All hooks in this component are called unconditionally.
 */
function AppWithBridge({
  bridge,
  initialTheme,
  initialAccent,
  initialDensity,
}) {
  const [tweaks, setTweaks] = React.useState({
    theme: initialTheme,
    accent: initialAccent || "slate",
    density: initialDensity || "cozy",
    radius: 6,
    sidebarMode: "full",
  });

  React.useEffect(() => {
    const handler = (theme) => {
      setTweaks((prev) => ({ ...prev, theme }));
    };
    bridge.theme_applied.connect(handler);

    bridge.settings_changed.connect((json) => {
      try {
        const settings = JSON.parse(json);
        setTweaks((prev) => ({
          ...prev,
          accent: settings.accent || prev.accent,
          density: settings.density || prev.density,
        }));
      } catch (e) {
        console.error("[main] Failed to parse settings_changed for tweaks:", e);
      }
    });
  }, [bridge]);

  const handleSetTweaks = (updates) => {
    setTweaks((prev) => ({ ...prev, ...updates }));
  };

  return (
    <ThemeProvider tweaks={tweaks} setTweaks={handleSetTweaks}>
      <VireloApp bridge={bridge} />
    </ThemeProvider>
  );
}

/**
 * Root component handles bridge initialization only.
 * Uses a single useState + useEffect pair, then conditionally renders
 * either a loading screen or AppWithBridge.
 */
function Root() {
  const [bridgeState, setBridgeState] = React.useState(null);

  React.useEffect(() => {
    // Resolve at most once, from whichever finishes first: the normal
    // bootstrap path, the failure path, or the timeout fallback.
    let settled = false;
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      setBridgeState(payload);
    };
    const defaults = {
      initialTheme: "dark",
      initialAccent: "slate",
      initialDensity: "cozy",
    };
    // If the bridge callbacks never fire, render the app with defaults
    // instead of showing the loading screen forever.
    const timer = setTimeout(() => {
      console.warn(
        "[main] Bridge did not respond within 3 seconds; rendering with defaults.",
      );
      finish({ bridge: getBridgeSync(), ...defaults });
    }, 3000);
    getBridge()
      .then((b) => {
        b.get_theme_mode((themeResult) => {
          b.get_settings((settingsResult) => {
            try {
              const tr = JSON.parse(themeResult);
              const sr = JSON.parse(settingsResult);
              const themeData =
                tr.ok && tr.data
                  ? tr.data
                  : { mode: "system", effective: "dark" };
              const settingsData = sr.ok && sr.data ? sr.data : {};
              finish({
                bridge: b,
                initialTheme: themeData.effective || "dark",
                initialAccent: settingsData.accent || "slate",
                initialDensity: settingsData.density || "cozy",
              });
            } catch (e) {
              console.error("[main] Failed to parse initial state:", e);
              finish({ bridge: b, ...defaults });
            }
          });
        });
      })
      .catch((e) => {
        console.error("[main] Bridge initialization failed:", e);
        finish({ bridge: getBridgeSync(), ...defaults });
      });
    return () => clearTimeout(timer);
  }, []);

  if (!bridgeState) {
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#111113",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#ECECEE",
          fontFamily: '"Inter", "Segoe UI", sans-serif',
          fontSize: 14,
        }}
      >
        Loading Virelo...
      </div>
    );
  }

  return (
    <AppWithBridge
      bridge={bridgeState.bridge}
      initialTheme={bridgeState.initialTheme}
      initialAccent={bridgeState.initialAccent}
      initialDensity={bridgeState.initialDensity}
    />
  );
}

const root = createRoot(document.getElementById("root"));
root.render(<Root />);
