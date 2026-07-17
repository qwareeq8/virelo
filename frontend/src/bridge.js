/**
 * QWebChannel bridge client for Virelo.
 *
 * In release mode, QWebChannel is loaded via qrc:///qtwebchannel/qwebchannel.js
 * and the Python VireloBridge QObject is available as channel.objects.bridge.
 *
 * In dev mode (Vite dev server), QWebChannel may not be available.
 * getBridge() returns a mock bridge with no-op methods so the UI renders.
 */

let bridgeInstance = null;
let bridgePromise = null;
const DEV_MODE = import.meta.env.DEV;

const MOCK_SETTINGS = {
  snap_key: "shift",
  restore_key: "ctrl",
  enable_snap: true,
  snap_presses: 3,
  snap_interval: 1050,
  width_pct: 76,
  height_pct: 76,
  game_mode_enabled: true,
  ex_auto_size: true,
  run_at_startup: false,
  theme: "dark",
  accent: "slate",
  density: "cozy",
  minimize_to_tray: true,
};

const MOCK_BRIDGE = {
  get_settings: (callback) =>
    callback(JSON.stringify({ ok: true, data: MOCK_SETTINGS })),
  save_settings: (json, transactionId, callback) =>
    callback(JSON.stringify({ ok: true, applied: JSON.parse(json) })),
  commit_draft: (transactionId, callback) =>
    callback(JSON.stringify({ ok: true, applied: {} })),
  discard_draft: (transactionId, callback) =>
    callback(JSON.stringify({ ok: true })),
  has_draft: (callback) => callback(JSON.stringify({ ok: true, data: false })),
  get_snap_enabled: (callback) =>
    callback(JSON.stringify({ ok: true, data: true })),
  test_snap: (callback) => callback(JSON.stringify({ ok: true })),
  capture_key: (target, callback) => callback(JSON.stringify({ ok: true })),
  cancel_capture: (callback) => callback(JSON.stringify({ ok: true })),
  set_modal_open: (isOpen, callback) => callback(JSON.stringify({ ok: true })),
  reset_defaults: (transactionId, callback) =>
    callback(JSON.stringify({ ok: true, data: MOCK_SETTINGS })),
  get_theme_mode: (callback) =>
    callback(
      JSON.stringify({
        ok: true,
        data: { mode: "dark", effective: "dark" },
      }),
    ),
  get_launch_at_login: (callback) =>
    callback(JSON.stringify({ ok: true, data: false })),
  setWindowCommand: (command, callback) =>
    callback(JSON.stringify({ ok: true })),
  apply_details_view: (callback) =>
    setTimeout(() => callback(JSON.stringify({ ok: true, data: {} })), 200),
  reset_folder_views: (callback) =>
    setTimeout(() => callback(JSON.stringify({ ok: true, data: {} })), 200),
  settings_changed: { connect: () => {}, disconnect: () => {} },
  theme_applied: { connect: () => {}, disconnect: () => {} },
  snap_status: { connect: () => {}, disconnect: () => {} },
  capture_status: { connect: () => {}, disconnect: () => {} },
  dirty_changed: { connect: () => {}, disconnect: () => {} },
  views_status: { connect: () => {}, disconnect: () => {} },
};

function initBridge() {
  if (bridgePromise) return bridgePromise;

  bridgePromise = new Promise((resolve, reject) => {
    const QWebChannelConstructor = globalThis.QWebChannel;
    const transport = globalThis.qt?.webChannelTransport;
    if (typeof QWebChannelConstructor !== "function" || !transport) {
      const message = "QWebChannel or its Qt transport is unavailable.";
      if (DEV_MODE) {
        console.warn(`[bridge] ${message} Using the development mock bridge.`);
        bridgeInstance = MOCK_BRIDGE;
        resolve(bridgeInstance);
      } else {
        reject(new Error(message));
      }
      return;
    }

    new QWebChannelConstructor(transport, (channel) => {
      bridgeInstance = channel.objects.bridge;
      if (!bridgeInstance) {
        const message =
          'QWebChannel did not expose the required "bridge" object.';
        if (!DEV_MODE) {
          reject(new Error(message));
          return;
        }
        console.warn(`[bridge] ${message} Using the development mock bridge.`);
        bridgeInstance = MOCK_BRIDGE;
      }
      resolve(bridgeInstance);
    });
  });

  return bridgePromise;
}

/**
 * Resolve the real Qt bridge or the development-only mock bridge.
 *
 * @returns {Promise<object>} The initialized bridge object.
 */
export function getBridge() {
  return initBridge();
}

/**
 * Return the bridge synchronously if initialization has completed.
 *
 * Development builds may use the mock bridge. Production builds return
 * `null` so a broken release cannot appear functional.
 *
 * @returns {object | null} The initialized bridge, a development mock, or null.
 */
export function getBridgeSync() {
  return bridgeInstance || (DEV_MODE ? MOCK_BRIDGE : null);
}

/** Parse a successful settings response without substituting writeable defaults. */
export function parseSettingsResult(rawResult) {
  const response = JSON.parse(rawResult);
  const data = response?.data;
  if (
    response?.ok !== true ||
    data === null ||
    typeof data !== "object" ||
    Array.isArray(data)
  ) {
    throw new Error(
      response?.error || "The backend did not return settings data.",
    );
  }
  return data;
}
