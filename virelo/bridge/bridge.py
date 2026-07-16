"""QWebChannel bridge between React frontend and Python backend.

Exposes a single VireloBridge QObject with narrow JSON-based Slot methods.
All inputs are validated. No broad Python object exposure.

The bridge is registered with QWebChannel as "bridge" so JavaScript accesses
it as channel.objects.bridge.

All slots return structured JSON payloads:
  Success: {"ok": true, "data": ...}
  Failure: {"ok": false, "error": "..."}
"""

import json
import logging

from PySide6.QtCore import QObject, Signal, Slot

from virelo.services.snap import SnapService
from virelo.settings.state import SettingsState

LOG = logging.getLogger("Virelo")


class VireloBridge(QObject):
    """Narrow JSON bridge between React UI and Python backend.

    All Slot methods accept/return JSON strings (or primitive types).
    Signals push updates from Python to React.

    Registration: QWebChannel.registerObject("bridge", self)
    JavaScript:   channel.objects.bridge.get_settings(callback)
    """

    # --- Signals (Python -> JS) ---
    settings_changed = Signal(str)  # JSON string of full settings dict
    theme_applied = Signal(str)  # "dark" or "light" (effective theme)
    snap_status = Signal(str, int)  # (message, timeout_ms)
    capture_status = Signal(str)  # "capturing", "done", "cancelled", "timeout"
    dirty_changed = Signal(bool)  # True = unsaved draft exists, False = clean

    def __init__(
        self,
        settings_state: SettingsState,
        snap_service: SnapService,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._state = settings_state
        self._snap = snap_service

        # These are set by MainWindow after construction
        self._main_window = None
        self._capture_guard = None

    def set_main_window(self, mw):
        """Set MainWindow reference for theme/capture/startup operations."""
        self._main_window = mw

    def set_capture_guard(self, guard):
        """Set CaptureGuard for key capture gating."""
        self._capture_guard = guard

    # --- Settings Slots ---

    @Slot(result=str)
    def get_settings(self) -> str:
        """Return all settings as a structured JSON payload."""
        try:
            settings = self._state.get_all()
            return json.dumps({"ok": True, "data": settings})
        except Exception as e:
            LOG.exception("get_settings failed")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def save_settings(self, json_str: str) -> str:
        """Store a partial settings update in draft (not persisted).

        Input: JSON dict of key-value pairs.
        Changes are staged in the draft model. Call commit_draft to persist.
        """
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return json.dumps({"ok": False, "error": "Expected JSON object"})
            result = self._state.apply_draft(data)
            if result.get("ok"):
                # Push updated settings (with draft overlay) to frontend
                self.settings_changed.emit(self._state.get_json())
                self.dirty_changed.emit(self._state.has_draft)
                if "theme" in data and self._main_window:
                    applied_theme = result.get("applied", {}).get("theme")
                    if applied_theme:
                        self._main_window._apply_theme_mode(applied_theme)
            return json.dumps(result)
        except json.JSONDecodeError as e:
            return json.dumps({"ok": False, "error": f"Invalid JSON: {e}"})
        except Exception as e:
            LOG.exception("save_settings failed")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(result=str)
    def commit_draft(self) -> str:
        """Persist draft settings to QSettings and apply side effects."""
        try:
            result = self._state.commit_draft()
            if result.get("ok"):
                self.settings_changed.emit(self._state.get_json())
                self.dirty_changed.emit(False)
                self._apply_side_effects(result.get("applied", {}))
            return json.dumps(result)
        except Exception as e:
            LOG.exception("commit_draft failed")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(result=str)
    def discard_draft(self) -> str:
        """Discard unsaved changes and push persisted settings to frontend."""
        try:
            self._state.discard_draft()
            self.settings_changed.emit(self._state.get_json())
            self.dirty_changed.emit(False)
            if self._main_window:
                persisted_theme = self._state._settings.theme
                self._main_window._apply_theme_mode(persisted_theme)
            return json.dumps({"ok": True})
        except Exception as e:
            LOG.exception("discard_draft failed")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(result=str)
    def has_draft(self) -> str:
        """Return whether unsaved changes exist."""
        return json.dumps({"ok": True, "data": self._state.has_draft})

    @Slot(result=str)
    def reset_defaults(self) -> str:
        """Reset all settings to defaults. Returns new settings as structured payload."""
        try:
            new_settings = self._state.reset_to_defaults()
            self.settings_changed.emit(self._state.get_json())
            self.dirty_changed.emit(False)
            # Apply all business logic side effects
            if self._main_window:
                self._main_window._update_snap_enabled_state()
                self._main_window._update_explorer_autosize_thread()
                if hasattr(self._main_window, "_hotkey_listener"):
                    self._main_window._hotkey_listener.update_binding(new_settings["snap_key"])
                    self._main_window._hotkey_listener.update_restore_key(new_settings["restore_key"])
                    self._main_window._hotkey_listener.update_press_limit(new_settings["snap_presses"])
                self._main_window._apply_theme_mode(new_settings["theme"])
            return json.dumps({"ok": True, "data": new_settings})
        except Exception as e:
            LOG.exception("reset_defaults failed")
            return json.dumps({"ok": False, "error": str(e)})

    # --- Snap Slots ---

    @Slot(result=str)
    def test_snap(self) -> str:
        """Trigger a test snap on the active window."""
        try:
            result = self._snap.test_snap()
            msg = result.get("message", result.get("error", ""))
            timeout = 2000
            self.snap_status.emit(msg, timeout)
            return json.dumps(result)
        except Exception as e:
            LOG.exception("test_snap failed")
            return json.dumps({"ok": False, "error": str(e)})

    # --- Key Capture Slots ---

    @Slot(str, result=str)
    def capture_key(self, target: str) -> str:
        """Start key capture for 'snap' or 'restore' target."""
        if target not in ("snap", "restore"):
            return json.dumps({"ok": False, "error": f"Invalid target: {target}"})
        if self._main_window is None:
            return json.dumps({"ok": False, "error": "MainWindow not ready"})
        try:
            if target == "snap":
                self._main_window._start_key_capture()
            else:
                self._main_window._start_restore_key_capture()
            self.capture_status.emit("capturing")
            return json.dumps({"ok": True})
        except Exception as e:
            LOG.exception("capture_key failed")
            return json.dumps({"ok": False, "error": str(e)})

    # --- Theme Slots ---

    @Slot(result=str)
    def get_theme_mode(self) -> str:
        """Return current theme mode and effective theme as structured JSON."""
        mode = "system"
        effective = "dark"
        if self._main_window:
            mode = getattr(self._main_window, "_theme_mode", "system")
            effective = getattr(self._main_window, "_theme_state", "dark")
        return json.dumps({"ok": True, "data": {"mode": mode, "effective": effective}})

    @Slot(result=str)
    def get_launch_at_login(self) -> str:
        """Return current launch-at-login state as structured JSON."""
        if self._main_window:
            val = self._main_window.action_run_at_startup.isChecked()
            return json.dumps({"ok": True, "data": val})
        return json.dumps({"ok": True, "data": False})

    @Slot(result=str)
    def get_snap_enabled(self) -> str:
        """Return whether snap is currently enabled as structured JSON."""
        if self._main_window:
            val = bool(getattr(self._main_window, "snap_enabled", False))
            return json.dumps({"ok": True, "data": val})
        return json.dumps({"ok": True, "data": False})

    # --- Window Command Slot ---

    @Slot(str, result=str)
    def setWindowCommand(self, command: str) -> str:
        """Execute a window management command (minimize or close)."""
        if command not in ("minimize", "close"):
            return json.dumps({"ok": False, "error": f"Unknown command: {command}"})
        if self._main_window is None:
            return json.dumps({"ok": False, "error": "MainWindow not ready"})
        try:
            if command == "minimize":
                self._main_window.showMinimized()
            elif command == "close":
                self._main_window.close()
            return json.dumps({"ok": True})
        except Exception as e:
            LOG.exception("setWindowCommand(%s) failed", command)
            return json.dumps({"ok": False, "error": str(e)})

    # --- Internal helpers ---

    def _apply_side_effects(self, applied: dict):
        """Apply business logic side effects after settings are committed."""
        if not self._main_window:
            return
        mw = self._main_window

        if "enable_snap" in applied:
            mw.snap_enabled = bool(applied["enable_snap"])
            mw._update_snap_enabled_state()

        if "ex_auto_size" in applied:
            mw._update_explorer_autosize_thread()

        if "snap_presses" in applied and hasattr(mw, "_hotkey_listener"):
            mw._hotkey_listener.update_press_limit(applied["snap_presses"])

        if "snap_key" in applied and hasattr(mw, "_hotkey_listener"):
            mw._hotkey_listener.update_binding(applied["snap_key"])

        if "restore_key" in applied and hasattr(mw, "_hotkey_listener"):
            mw._hotkey_listener.update_restore_key(applied["restore_key"])

        if "theme" in applied:
            mw._apply_theme_mode(applied["theme"])

        if "run_at_startup" in applied:
            try:
                from virelo.app.window import create_startup_shortcut, remove_startup_shortcut
                if applied["run_at_startup"]:
                    create_startup_shortcut()
                else:
                    remove_startup_shortcut()
            except Exception:
                LOG.exception("Startup shortcut error")
                self.snap_status.emit("Failed to update startup shortcut.", 5000)

        if "minimize_to_tray" in applied:
            mw.minimize_to_tray_on_exit = bool(applied["minimize_to_tray"])

        if "run_at_startup" in applied:
            mw.action_run_at_startup.setChecked(bool(applied["run_at_startup"]))
        if "minimize_to_tray" in applied:
            mw.action_minimize_on_exit.setChecked(bool(applied["minimize_to_tray"]))
