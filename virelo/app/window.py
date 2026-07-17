"""MainWindow: frameless, tray-integrated window hosting the React frontend."""

import ctypes
import ctypes.wintypes
import logging
import os
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from virelo.app.config import APP_NAME, DEFAULTS, INSTANCE_WINDOW_PROPERTY, normalize_snap_presses
from virelo.app.webview import VireloWebView
from virelo.app.window_hit_test import classify_window_hit
from virelo.bridge import CaptureGuard, VireloBridge
from virelo.platform.resources import resource_path
from virelo.platform.startup import ensure_dispatch, startup_shortcut_spec
from virelo.platform.theme import (
    get_windows_theme,
    normalize_theme_mode,
    resolve_theme,
    toggle_theme_mode,
)
from virelo.platform.win32_abi import USER32
from virelo.services.explorer_service import ExplorerService
from virelo.services.snap import MultiPressHotkeyListener, SnapRestoreController, SnapService
from virelo.settings import Settings, SettingsState
from virelo.workers.key_capture import KeyCaptureWorker

LOG = logging.getLogger("Virelo")

APP_TITLE = APP_NAME

# ------------------------------------------------------------------------------
# Startup shortcut management.
# ------------------------------------------------------------------------------


def get_startup_shortcut_path() -> str:
    """Return the current user's Virelo startup-shortcut path."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set.")
    startup_dir = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(startup_dir, f"{APP_NAME}.lnk")


def create_startup_shortcut() -> None:
    """Create or replace the current user's Virelo startup shortcut."""
    shortcut_path = get_startup_shortcut_path()
    script = os.path.abspath(sys.argv[0])
    frozen = bool(getattr(sys, "frozen", False))
    target, args = startup_shortcut_spec(sys.executable, script, frozen)
    wsh = ensure_dispatch("WScript.Shell")
    os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
    shortcut = wsh.CreateShortcut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = os.path.dirname(target if frozen else script)
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        shortcut.IconLocation = icon_path
    shortcut.Save()


def remove_startup_shortcut() -> None:
    """Remove the current user's Virelo startup shortcut if it exists."""
    shortcut_path = get_startup_shortcut_path()
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)


def sync_startup_shortcut(enabled: bool) -> None:
    """Make the current-user startup shortcut match the persisted setting."""
    if enabled:
        create_startup_shortcut()
    else:
        remove_startup_shortcut()


# ------------------------------------------------------------------------------
# Main window with tray icon.
# ------------------------------------------------------------------------------


class MainWindow(QtWidgets.QMainWindow):
    """Main application window with tray icon and QWebEngineView frontend.

    The React frontend renders inside ``QWebEngineView``. ``VireloBridge``
    mediates settings, theme, capture, and snap communication. ``WM_NCHITTEST``
    provides resizing with an 860 by 600 minimum and 1000 by 620 default.
    """

    snap_key_status = QtCore.Signal(str, int)

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.settings.snap_key = str(self.settings.snap_key)
        self.settings.restore_key = str(self.settings.restore_key)
        self.settings.enable_snap = bool(self.settings.enable_snap)
        self.settings.snap_presses = normalize_snap_presses(self.settings.snap_presses)
        self.settings.snap_interval = int(self.settings.snap_interval)
        self.settings.width_pct = int(self.settings.width_pct)
        self.settings.height_pct = int(self.settings.height_pct)
        self.settings.ex_auto_size = bool(getattr(self.settings, "ex_auto_size", False))
        self.settings.game_mode_enabled = bool(self.settings.game_mode_enabled)
        self.settings.run_at_startup = bool(self.settings.run_at_startup)
        self.settings.theme = normalize_theme_mode(str(self.settings.theme), DEFAULTS["theme"])

        self._capture_guard = CaptureGuard()
        self._capture_thread = None
        self._capture_worker = None
        self._capture_target = None

        self.is_first_show = True

        self._theme_mode = self.settings.theme
        self._theme_state = self.settings.theme

        # React to OS theme changes instead of polling the registry. Qt tracks
        # the Windows "apps use light theme" setting and emits on change.
        QtGui.QGuiApplication.styleHints().colorSchemeChanged.connect(self._sync_system_theme)

        self.setWindowTitle(APP_TITLE)
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            icon = QtGui.QIcon(icon_path)
        else:
            icon = QtGui.QIcon.fromTheme("applications-system")
        self.setWindowIcon(icon)
        QtWidgets.QApplication.setWindowIcon(icon)

        # Frameless + resizable window.
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(860, 600)
        self.resize(1000, 620)

        self.tray_icon = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Virelo")
        menu = QtWidgets.QMenu(self)
        open_act = menu.addAction("Open")
        open_act.triggered.connect(self._restore_window)

        self.minimize_to_tray_on_exit = bool(getattr(self.settings, "minimize_to_tray", True))
        self.action_minimize_on_exit = menu.addAction("Minimize to Tray")
        self.action_minimize_on_exit.setCheckable(True)
        self.action_minimize_on_exit.setChecked(self.minimize_to_tray_on_exit)
        self.action_minimize_on_exit.triggered.connect(self._toggle_minimize_on_exit)

        self.action_run_at_startup = menu.addAction("Run at Startup")
        self.action_run_at_startup.setCheckable(True)
        self.action_run_at_startup.setChecked(bool(self.settings.run_at_startup))
        self.action_run_at_startup.triggered.connect(self._toggle_run_at_startup)

        exit_act = menu.addAction("Quit")
        exit_act.triggered.connect(self._really_quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # Business logic such as ``SnapRestoreController`` and ``_test_snap`` uses this value.
        self.snap_enabled = bool(self.settings.enable_snap)

        # --- Bridge + WebView ---
        self._settings_state = SettingsState(self.settings)
        self._snap_service = SnapService(None)  # ``shift_mgr`` is set after construction.
        self._bridge = VireloBridge(self._settings_state, self._snap_service, parent=self)
        self._bridge.set_main_window(self)
        self._bridge.set_capture_guard(self._capture_guard)

        self.webview = VireloWebView(self._bridge, parent=self)

        # React handles all UI, so the web view is the central widget.
        self.setCentralWidget(self.webview)

        # Route the ``snap_key_status`` signal to the bridge.
        self.snap_key_status.connect(self._bridge.snap_status.emit)

        # Folder view tasks restart Explorer; bring the autosize worker back
        # afterward (queued from the task's worker thread to the GUI thread).
        self._bridge.explorer_service_restart.connect(self._update_explorer_autosize_thread)

        # Register window shortcuts.
        self._window_shortcuts = [
            QtGui.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, activated=self._toggle_theme),
            QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self._test_snap),
            QtGui.QShortcut(QtGui.QKeySequence("F1"), self, activated=self._show_help),
        ]

        # Connect the hotkey listener and snap controller under D-01 to D-03.
        self._hotkey_listener = MultiPressHotkeyListener(
            self.settings, capture_guard=self._capture_guard
        )
        self.shift_mgr = SnapRestoreController(self.settings)
        self._hotkey_listener.triggered.connect(self.shift_mgr.perform)
        self.shift_mgr.blocked.connect(lambda message: self.snap_key_status.emit(message, 3000))
        self._snap_service.set_manager(self.shift_mgr)
        self._snap_service.set_listener(self._hotkey_listener)

        # Manage Explorer autosizing through ``ExplorerService`` under D-07 to D-09.
        self._explorer_service = ExplorerService(self.settings, parent=self)
        self._update_explorer_enabled_state()

        self._apply_theme_mode(self._theme_mode)
        QtCore.QTimer.singleShot(0, self._reconcile_startup_shortcut)

    # ------------------------------------------------------------------
    # Tray behavior
    # ------------------------------------------------------------------

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            if self.isMinimized() and self.minimize_to_tray_on_exit:
                QtCore.QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.minimize_to_tray_on_exit:
            event.ignore()
            self.hide()
        else:
            self._stop_background_threads()
            self._hotkey_listener.cleanup()
            QtWidgets.QApplication.quit()

    def _on_tray_activated(self, reason):
        if reason in (
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_window()

    def _restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _really_quit(self):
        self._stop_background_threads()
        self._hotkey_listener.cleanup()
        QtWidgets.QApplication.quit()

    def _stop_background_threads(self):
        # Let any in-flight folder view registry task finish so it is never
        # killed mid-write during shutdown.
        try:
            self._bridge.wait_for_view_task()
        except Exception:
            LOG.exception("Waiting for the folder-view task failed.")
        self._stop_capture_worker()
        self._explorer_service.stop()
        self._stop_theme_sync()

    # ------------------------------------------------------------------
    # Key capture uses bridge signals for status updates.
    # ------------------------------------------------------------------

    def _start_key_capture(self) -> bool:
        return self._begin_key_capture("snap", "Press the desired snap key. Press Esc to cancel.")

    def _start_restore_key_capture(self) -> bool:
        return self._begin_key_capture(
            "restore", "Press the desired restore key. Press Esc to cancel."
        )

    def _begin_key_capture(self, target: str, message: str) -> bool:
        """Start a key-capture session and report whether capture began."""
        if not self._capture_guard.try_start():
            self._bridge.snap_status.emit("Key capture already in progress.", 2000)
            return False
        try:
            self._capture_target = target
            self._capture_thread = QtCore.QThread(self)
            self._capture_worker = KeyCaptureWorker()
        except Exception:
            # Construction failed; release the guard or capture is dead forever.
            self._capture_guard.finish()
            self._capture_target = None
            self._capture_thread = None
            self._capture_worker = None
            LOG.exception("Key-capture worker construction failed.")
            self._bridge.snap_status.emit("Key capture could not start.", 3000)
            return False
        self._bridge.snap_status.emit(message, 0)
        self._bridge.capture_status.emit("capturing")
        self._capture_worker.moveToThread(self._capture_thread)
        self._capture_thread.started.connect(self._capture_worker.run)
        self._capture_worker.captured.connect(self._on_capture_key)
        self._capture_worker.cancelled.connect(self._on_capture_cancelled)
        self._capture_worker.finished.connect(self._capture_thread.quit)
        self._capture_worker.finished.connect(self._capture_worker.deleteLater)
        self._capture_thread.finished.connect(self._capture_thread.deleteLater)
        self._capture_thread.finished.connect(self._on_capture_finished)
        self._capture_thread.start()
        return True

    def _on_capture_key(self, key: str) -> None:
        key_str = str(key).lower()
        target_key = "restore_key" if self._capture_target == "restore" else "snap_key"
        result = self._settings_state.apply_draft({target_key: key_str})
        if not result.get("ok"):
            self._bridge.capture_status.emit("cancelled")
            self._bridge.snap_status.emit(result.get("error", "Key binding was not changed."), 5000)
            return
        self._bridge.settings_changed.emit(self._settings_state.get_json())
        self._bridge.dirty_changed.emit(True)
        self._bridge.capture_status.emit("done")
        label = "Restore" if self._capture_target == "restore" else "Snap"
        self._bridge.snap_status.emit(f"{label} key set to {key_str.upper()}.", 3000)

    def _on_capture_cancelled(self, reason: str) -> None:
        message = "Key capture timed out." if reason == "timeout" else "Key capture cancelled."
        self._bridge.capture_status.emit("cancelled" if reason != "timeout" else "timeout")
        self._bridge.snap_status.emit(message, 2000)

    def _cancel_key_capture(self) -> None:
        """Stop an in-progress capture so the global keyboard hook is released.

        Signals the worker to stop; the normal cancelled/finished path then
        emits capture_status and releases the guard.
        """
        worker = getattr(self, "_capture_worker", None)
        if worker is not None:
            try:
                worker.stop()
            except Exception:
                LOG.exception("Cancelling key capture failed.")

    def _on_capture_finished(self) -> None:
        self._capture_guard.finish()
        self._capture_thread = None
        self._capture_worker = None
        self._capture_target = None

    def _stop_capture_worker(self) -> None:
        worker = getattr(self, "_capture_worker", None)
        thread = getattr(self, "_capture_thread", None)
        if worker is not None:
            try:
                worker.stop()
            except Exception:
                pass
        if thread is not None:
            thread.quit()
            thread.wait(2000)
        self._capture_guard.finish()
        self._capture_thread = None
        self._capture_worker = None
        self._capture_target = None

    # ------------------------------------------------------------------
    # Business logic actions.
    # ------------------------------------------------------------------

    def _test_snap(self) -> None:
        try:
            if self.shift_mgr.perform(False):
                self._bridge.snap_status.emit("Snap test applied to the active window.", 2000)
            else:
                self._bridge.snap_status.emit("Could not snap the active window.", 2000)
        except Exception:
            LOG.exception("Testing a snap on the active window failed.")
            self._bridge.snap_status.emit("Could not snap the active window.", 2000)

    def _set_modal_shortcuts_enabled(self, enabled: bool) -> None:
        """Enable native shortcuts only when no frontend confirmation is modal."""
        for shortcut in self._window_shortcuts:
            shortcut.setEnabled(bool(enabled))

    def _show_help(self):
        QtWidgets.QMessageBox.information(
            self,
            "Virelo Help",
            "* Press Count & Interval: how many times and how fast to press the Snap Key.\n"
            "* Hold the Restore Key while pressing to restore original window size.\n"
            "* Width/Height: snapped window size as % of the current monitor.\n"
            "* Explorer Auto-Size: auto-fit columns on folder change (Details view).\n"
            "* Game Mode: when enabled, fullscreen windows (typically games) are skipped.\n\n"
            "Shortcuts:\n"
            "  Ctrl+T = Toggle Theme,  Ctrl+Enter = Test Snap,\n"
            "  F1 = Help.",
        )

    # ------------------------------------------------------------------
    # Enable and disable state delegated to pages.
    # ------------------------------------------------------------------

    def _update_explorer_enabled_state(self) -> None:
        self._explorer_service.start()

    def _update_explorer_autosize_thread(self, *_args) -> None:
        """Start or stop the Explorer autosize background thread."""
        self._explorer_service.start()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            if not USER32.SetPropW(int(self.winId()), INSTANCE_WINDOW_PROPERTY, 1):
                LOG.warning("Could not mark Virelo's native window for single-instance focus.")
        except Exception:
            LOG.exception("Could not mark Virelo's native window for single-instance focus.")
        self._update_explorer_enabled_state()
        if self.is_first_show:
            self.is_first_show = False
            # Defer centering to the next event-loop turn instead of forcing a
            # reentrant processEvents() inside the show handler.
            QtCore.QTimer.singleShot(0, self.center_on_screen)

    def _toggle_minimize_on_exit(self) -> None:
        checked = self.action_minimize_on_exit.isChecked()
        if not self._persist_immediate_settings({"minimize_to_tray": checked}):
            self.action_minimize_on_exit.setChecked(not checked)

    def _toggle_run_at_startup(self) -> None:
        checked = self.action_run_at_startup.isChecked()
        if not self._persist_immediate_settings({"run_at_startup": checked}):
            self.action_run_at_startup.setChecked(not checked)

    def _toggle_theme(self) -> None:
        new_mode = toggle_theme_mode(self._theme_mode, get_windows_theme())
        if not self._persist_immediate_settings({"theme": new_mode}):
            self._bridge.snap_status.emit("Could not save the theme setting.", 3000)

    def _persist_immediate_settings(self, data: dict) -> bool:
        """Persist an immediate control without committing the shared draft."""
        try:
            result = self._settings_state.persist_immediate(data)
            if not result.get("ok"):
                return False
            self._bridge._apply_side_effects(result.get("applied", {}))
            self._bridge.dirty_changed.emit(self._settings_state.has_draft)
            self._bridge.settings_changed.emit(self._settings_state.get_json())
            return True
        except Exception:
            LOG.exception("The immediate settings update failed.")
            return False

    def _reconcile_startup_shortcut(self) -> None:
        """Retry the persisted startup preference on every application launch."""
        try:
            sync_startup_shortcut(bool(self.settings.run_at_startup))
        except Exception:
            LOG.exception("Reconciling the persisted startup shortcut failed.")
            self._bridge.snap_status.emit(
                "The run-at-startup setting is saved, but its shortcut could not be updated. "
                "Virelo will retry at the next launch.",
                8000,
            )

    def _apply_theme_mode(self, mode: str) -> None:
        self._theme_mode = normalize_theme_mode(mode, DEFAULTS["theme"])
        if self._theme_mode == "system":
            self._start_theme_sync()
        else:
            self._stop_theme_sync()
            self.set_theme(self._theme_mode)

    def _start_theme_sync(self) -> None:
        self._sync_system_theme()

    def _stop_theme_sync(self) -> None:
        """Leave system-theme synchronization idle for an explicit theme.

        The persistent ``colorSchemeChanged`` connection remains harmless
        because ``_sync_system_theme`` ignores changes outside system mode.
        """

    def _sync_system_theme(self) -> None:
        if self._theme_mode != "system":
            return
        effective = resolve_theme("system", get_windows_theme())
        if effective != self._theme_state:
            self.set_theme(effective)

    def set_theme(self, theme: str) -> None:
        """Publish the effective theme to the frontend."""
        self._theme_state = theme
        self._bridge.theme_applied.emit(theme)

    def center_on_screen(self) -> None:
        """Center the window on the monitor containing the pointer."""
        cursor_pos = QtGui.QCursor.pos()
        screen = (
            QtWidgets.QApplication.screenAt(cursor_pos) or QtWidgets.QApplication.primaryScreen()
        )
        g = screen.availableGeometry()
        w = self.size()
        x = g.x() + (g.width() - w.width()) // 2
        y = g.y() + (g.height() - w.height()) // 2
        self.move(int(x), int(y))

    # ------------------------------------------------------------------
    # Resizable window through ``WM_NCHITTEST``.
    # ------------------------------------------------------------------

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                # Convert screen coordinates to window coordinates.
                pos = self.mapFromGlobal(QtCore.QPoint(x, y))
                rect = self.rect()
                result = classify_window_hit(pos.x(), pos.y(), rect.width(), rect.height())
                if result:
                    return True, result

        return super().nativeEvent(event_type, message)
