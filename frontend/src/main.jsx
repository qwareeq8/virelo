import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "./theme.jsx";
import VireloApp from "./app.jsx";
import { getBridge, getBridgeSync, parseSettingsResult } from "./bridge.js";
import { FatalErrorScreen, VireloErrorBoundary } from "./fatal-error.jsx";

/**
 * Render the application after the bridge and initial preferences are ready.
 *
 * Keeping these hooks in a separate component lets `Root` render loading and
 * error states without calling hooks conditionally.
 */
function AppWithBridge({ bridge, initialTheme, initialAccent, initialDensity, initialSettings }) {
  const [tweaks, setTweaks] = React.useState({
    theme: initialTheme,
    accent: initialAccent || "slate",
    density: initialDensity || "cozy",
    radius: 6,
    sidebarMode: "full",
  });

  React.useEffect(() => {
    const onThemeApplied = (theme) => {
      setTweaks((prev) => ({ ...prev, theme }));
    };
    bridge.theme_applied.connect(onThemeApplied);
    return () => {
      bridge.theme_applied.disconnect?.(onThemeApplied);
    };
  }, [bridge]);

  const handleSetTweaks = React.useCallback((updates) => {
    setTweaks((prev) => ({ ...prev, ...updates }));
  }, []);

  return (
    <ThemeProvider tweaks={tweaks} setTweaks={handleSetTweaks}>
      <VireloApp bridge={bridge} initialSettings={initialSettings} />
    </ThemeProvider>
  );
}

/** Initialize the bridge and render the corresponding application state. */
function Root() {
  const [bridgeState, setBridgeState] = React.useState(null);

  React.useEffect(() => {
    // Resolve at most once from the normal path, failure path, or timeout.
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
      console.warn("[main] Bridge did not respond within 3 seconds; rendering with defaults.");
      const fallback = getBridgeSync();
      finish(
        fallback
          ? { bridge: fallback, ...defaults }
          : { error: "Virelo could not connect to its Windows backend." },
      );
    }, 3000);
    getBridge()
      .then((bridge) => {
        bridge.get_theme_mode((themeResult) => {
          bridge.get_settings((settingsResult) => {
            try {
              const themeResponse = JSON.parse(themeResult);
              const settingsData = parseSettingsResult(settingsResult);
              const themeData =
                themeResponse.ok && themeResponse.data
                  ? themeResponse.data
                  : { mode: "system", effective: "dark" };
              finish({
                bridge,
                initialTheme: themeData.effective || "dark",
                initialAccent: settingsData.accent || "slate",
                initialDensity: settingsData.density || "cozy",
                initialSettings: settingsData,
              });
            } catch (error) {
              console.error("[main] Failed to parse initial state:", error);
              finish({
                error: "Virelo could not safely load its initial settings.",
              });
            }
          });
        });
      })
      .catch((error) => {
        console.error("[main] Bridge initialization failed:", error);
        const fallback = getBridgeSync();
        finish(
          fallback
            ? { bridge: fallback, ...defaults }
            : { error: "Virelo could not connect to its Windows backend." },
        );
      });
    return () => clearTimeout(timer);
  }, []);

  if (!bridgeState) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          width: "100%",
          height: "100%",
          colorScheme: "light dark",
          background: "Canvas",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "CanvasText",
          fontFamily: "inherit",
          fontSize: 14,
        }}
      >
        Loading Virelo...
      </div>
    );
  }

  if (bridgeState.error) {
    return <FatalErrorScreen message={bridgeState.error} />;
  }

  return (
    <AppWithBridge
      bridge={bridgeState.bridge}
      initialTheme={bridgeState.initialTheme}
      initialAccent={bridgeState.initialAccent}
      initialDensity={bridgeState.initialDensity}
      initialSettings={bridgeState.initialSettings}
    />
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error('Virelo cannot start because the "root" element is missing.');
}
const root = createRoot(rootElement);
root.render(
  <VireloErrorBoundary>
    <Root />
  </VireloErrorBoundary>,
);
