/**
 * QWebChannel bridge client for Virelo.
 *
 * In release mode, QWebChannel is loaded via qrc:///qtwebchannel/qwebchannel.js
 * and the Python VireloBridge QObject is available as channel.objects.bridge.
 *
 * In dev mode (Vite dev server), QWebChannel may not be available.
 * getBridge() returns a mock bridge with no-op methods so the UI renders.
 */

let _bridge = null;
let _bridgePromise = null;

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
  get_settings: (cb) => cb(JSON.stringify({ ok: true, data: MOCK_SETTINGS })),
  save_settings: (json, cb) =>
    cb(JSON.stringify({ ok: true, applied: JSON.parse(json) })),
  commit_draft: (cb) => cb(JSON.stringify({ ok: true, applied: {} })),
  discard_draft: (cb) => cb(JSON.stringify({ ok: true })),
  has_draft: (cb) => cb(JSON.stringify({ ok: true, data: false })),
  get_snap_enabled: (cb) => cb(JSON.stringify({ ok: true, data: true })),
  test_snap: (cb) => cb(JSON.stringify({ ok: true })),
  capture_key: (target, cb) => cb(JSON.stringify({ ok: true })),
  reset_defaults: (cb) => cb(JSON.stringify({ ok: true, data: MOCK_SETTINGS })),
  get_theme_mode: (cb) =>
    cb(JSON.stringify({ ok: true, data: { mode: "dark", effective: "dark" } })),
  get_launch_at_login: (cb) => cb(JSON.stringify({ ok: true, data: false })),
  setWindowCommand: (cmd, cb) => cb(JSON.stringify({ ok: true })),
  apply_details_view: (cb) =>
    setTimeout(() => cb(JSON.stringify({ ok: true, data: {} })), 200),
  reset_folder_views: (cb) =>
    setTimeout(() => cb(JSON.stringify({ ok: true, data: {} })), 200),
  settings_changed: { connect: () => {}, disconnect: () => {} },
  theme_applied: { connect: () => {}, disconnect: () => {} },
  snap_status: { connect: () => {}, disconnect: () => {} },
  capture_status: { connect: () => {}, disconnect: () => {} },
  dirty_changed: { connect: () => {}, disconnect: () => {} },
  views_status: { connect: () => {}, disconnect: () => {} },
};

function _initBridge() {
  if (_bridgePromise) return _bridgePromise;

  _bridgePromise = new Promise((resolve) => {
    if (typeof QWebChannel === "undefined") {
      console.warn(
        "[bridge] QWebChannel not available — using mock bridge (dev mode)",
      );
      _bridge = MOCK_BRIDGE;
      resolve(_bridge);
      return;
    }

    // eslint-disable-next-line no-undef
    new QWebChannel(qt.webChannelTransport, (channel) => {
      _bridge = channel.objects.bridge;
      if (!_bridge) {
        console.error('[bridge] No "bridge" object found in QWebChannel');
        _bridge = MOCK_BRIDGE;
      }
      resolve(_bridge);
    });
  });

  return _bridgePromise;
}

export function getBridge() {
  return _initBridge();
}

// Returns the resolved bridge if available, otherwise the mock. Safe to call
// outside React, for example from bootstrap timeout fallbacks.
export function getBridgeSync() {
  return _bridge || MOCK_BRIDGE;
}

export function useBridgeSync() {
  return getBridgeSync();
}
