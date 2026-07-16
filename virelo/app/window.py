"""MainWindow: frameless, tray-integrated window hosting the React frontend."""

import ctypes
import ctypes.wintypes
import logging
import os
import sys

from PySide6 import QtCore, QtGui, QtWidgets
from win32com.client import Dispatch

from virelo.app.config import APP_NAME, DEFAULTS, normalize_snap_presses
from virelo.app.webview import VireloWebView
from virelo.bridge import CaptureGuard, VireloBridge
from virelo.platform.resources import resource_path
from virelo.platform.startup import startup_shortcut_spec
from virelo.platform.theme import (
    get_windows_theme,
    normalize_theme_mode,
    resolve_theme,
    toggle_theme_mode,
)
from virelo.services.explorer_service import ExplorerService
from virelo.services.snap import MultiPressHotkeyListener, SnapRestoreController, SnapService
from virelo.settings import Settings, SettingsState
from virelo.workers.key_capture import KeyCaptureWorker

LOG = logging.getLogger("Virelo")

APP_TITLE = APP_NAME

# Window chrome constants for WM_NCHITTEST hit-zone classification
TITLE_BAR_HEIGHT = 35  # Frontend TitleBar: 34px height + 1px borderBottom
CONTROLS_WIDTH = 60  # Two 28px window control buttons + right padding margin


# ------------------------------------------------------------------------------
# Startup shortcut management
# ------------------------------------------------------------------------------


def get_startup_shortcut_path() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set.")
    startup_dir = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(startup_dir, f"{APP_NAME}.lnk")


def _ensure_dispatch(app_name: str):
    try:
        return Dispatch(app_name)
    except AttributeError:
        import re
        import shutil

        LOG.warning("win32com gen_py cache appears corrupted. Rebuilding.")
        module_list = [m.__name__ for m in sys.modules.values() if getattr(m, "__name__", None)]
        for module in module_list:
            if re.match(r"win32com\.gen_py\..+", module):
                sys.modules.pop(module, None)
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            gen_py_path = os.path.join(localappdata, "Temp", "gen_py")
            if os.path.exists(gen_py_path):
                shutil.rmtree(gen_py_path, ignore_errors=True)
        from win32com import client

        return client.gencache.EnsureDispatch(app_name)


def create_startup_shortcut():
    shortcut_path = get_startup_shortcut_path()
    script = os.path.abspath(sys.argv[0])
    frozen = bool(getattr(sys, "frozen", False))
    target, args = startup_shortcut_spec(sys.executable, script, frozen)
    wsh = Dispatch("WScript.Shell")
    os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
    shortcut = wsh.CreateShortcut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = os.path.dirname(target if frozen else script)
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        shortcut.IconLocation = icon_path
    shortcut.Save()


def remove_startup_shortcut():
    shortcut_path = get_startup_shortcut_path()
    if os.path.exists(shortcut_path):
        try:
            os.remove(shortcut_path)
        except Exception as e:
            LOG.exception("Failed to remove startup shortcut.", exc_info=e)


# ------------------------------------------------------------------------------
# Main window with tray icon
# ------------------------------------------------------------------------------


class MainWindow(QtWidgets.QMainWindow):
    """Main application window with tray icon and QWebEngineView frontend.

    UI rendered by React frontend in QWebEngineView. VireloBridge
    mediates all settings/theme/capture/snap communication. Window is resizable
    via WM_NCHITTEST (min 860x600, default 1000x620).
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

        # snap_enabled used by business logic (SnapRestoreController, _test_snap)
        self.snap_enabled = bool(self.settings.enable_snap)

        # --- Bridge + WebView ---
        self._settings_state = SettingsState(self.settings)
        self._snap_service = SnapService(None)  # shift_mgr set after construction
        self._bridge = VireloBridge(self._settings_state, self._snap_service, parent=self)
        self._bridge.set_main_window(self)
        self._bridge.set_capture_guard(self._capture_guard)

        self.webview = VireloWebView(self._bridge, parent=self)

        # Central widget is just the webview -- React handles all UI
        self.setCentralWidget(self.webview)

        # Route snap_key_status signal to bridge
        self.snap_key_status.connect(self._bridge.snap_status.emit)

        # Folder view tasks restart Explorer; bring the autosize worker back
        # afterward (queued from the task's worker thread to the GUI thread).
        self._bridge.explorer_service_restart.connect(self._update_explorer_autosize_thread)

        # Shortcuts
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, activated=self._toggle_theme)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self._test_snap)
        QtGui.QShortcut(QtGui.QKeySequence("F1"), self, activated=self._show_help)

        # MultiPressHotkeyListener + SnapRestoreController (per D-01/D-02/D-03)
        self._hotkey_listener = MultiPressHotkeyListener(self.settings)
        self.shift_mgr = SnapRestoreController(self.settings)
        self._hotkey_listener.triggered.connect(self.shift_mgr.perform)
        self.shift_mgr.blocked.connect(lambda message: self.snap_key_status.emit(message, 3000))
        self._snap_service.set_manager(self.shift_mgr)
        self._snap_service.set_listener(self._hotkey_listener)

        # ExplorerService (per D-07/D-08/D-09)
        self._explorer_service = ExplorerService(self.settings, parent=self)
        self._update_explorer_enabled_state()

        self._apply_theme_mode(self._theme_mode)

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
            LOG.exception("Waiting for folder view task failed")
        self._stop_capture_worker()
        self._explorer_service.stop()
        self._stop_theme_sync()

    # ------------------------------------------------------------------
    # Key capture (preserved -- uses bridge signals for status updates)
    # ------------------------------------------------------------------

    def _start_key_capture(self) -> bool:
        return self._begin_key_capture("snap", "Press desired snap key... (Esc to cancel)")

    def _start_restore_key_capture(self) -> bool:
        return self._begin_key_capture("restore", "Press desired restore key... (Esc to cancel)")

    def _begin_key_capture(self, target: str, message: str) -> bool:
        """Start a key capture session. Returns True when capture began."""
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
            LOG.exception("Key capture worker construction failed")
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

    def _on_capture_key(self, key: str):
        key_str = str(key).lower()
        target_key = "restore_key" if self._capture_target == "restore" else "snap_key"
        self._settings_state.apply_draft({target_key: key_str})
        self._bridge.settings_changed.emit(self._settings_state.get_json())
        self._bridge.dirty_changed.emit(True)
        self._bridge.capture_status.emit("done")
        label = "Restore" if self._capture_target == "restore" else "Snap"
        self._bridge.snap_status.emit(f"{label} key set to {key_str.upper()}.", 3000)

    def _on_capture_cancelled(self, reason: str):
        message = "Key capture timed out." if reason == "timeout" else "Key capture cancelled."
        self._bridge.capture_status.emit("cancelled" if reason != "timeout" else "timeout")
        self._bridge.snap_status.emit(message, 2000)

    def _on_capture_finished(self):
        self._capture_guard.finish()
        self._capture_thread = None
        self._capture_worker = None
        self._capture_target = None

    def _stop_capture_worker(self):
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
    # Business logic actions (preserved)
    # ------------------------------------------------------------------

    def _test_snap(self):
        try:
            self.shift_mgr.perform(False)
            self._bridge.snap_status.emit("Snap test applied to the active window.", 2000)
        except Exception:
            self._bridge.snap_status.emit("Could not snap the active window.", 2000)

    def _reset_defaults(self):
        """Reset all settings to defaults (called from bridge.reset_defaults)."""
        defaults = DEFAULTS.copy()
        for key, val in defaults.items():
            setattr(self.settings, key, val)
        self.settings.save()
        self.snap_enabled = bool(defaults["enable_snap"])
        self._update_snap_enabled_state()
        self._update_explorer_autosize_thread()
        self._apply_theme_mode(defaults["theme"])
        if hasattr(self, "_hotkey_listener"):
            self._hotkey_listener.update_binding(defaults["snap_key"])
            self._hotkey_listener.update_restore_key(defaults["restore_key"])
            self._hotkey_listener.update_press_limit(defaults["snap_presses"])
        self._bridge.settings_changed.emit(self._settings_state.get_json())
        self._bridge.snap_status.emit("Defaults loaded.", 3000)

    def _show_help(self):
        QtWidgets.QMessageBox.information(
            self,
            "Virelo -- Help",
            "* Press Count & Interval: how many times and how fast to press the Snap Key.\n"
            "* Hold the Restore Key while pressing to restore original window size.\n"
            "* Width/Height: snapped window size as % of the current monitor.\n"
            "* Explorer Auto-Size: auto-fit columns on folder change (Details view).\n"
            "* Game Mode: when enabled, fullscreen windows (typically games) are skipped.\n\n"
            "Shortcuts:\n"
            "  Ctrl+S = Save Settings,  Ctrl+T = Toggle Theme,\n"
            "  Ctrl+Enter = Test Snap,  F1 = Help",
        )

    # ------------------------------------------------------------------
    # Enable/disable state (delegates to pages)
    # ------------------------------------------------------------------

    def _update_snap_enabled_state(self):
        pass  # React reads snap_enabled from settings via bridge

    def _update_explorer_enabled_state(self):
        self._explorer_service.start()

    def _update_explorer_autosize_thread(self, *args):
        """Start/stop the Explorer autosize background thread."""
        self._explorer_service.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_snap_enabled_state()
        self._update_explorer_enabled_state()
        if self.is_first_show:
            self.is_first_show = False
            # Defer centering to the next event-loop turn instead of forcing a
            # reentrant processEvents() inside the show handler.
            QtCore.QTimer.singleShot(0, self.center_on_screen)

    def _toggle_minimize_on_exit(self):
        checked = self.action_minimize_on_exit.isChecked()
        result = self._settings_state.apply_draft({"minimize_to_tray": checked})
        if result.get("ok"):
            commit_result = self._settings_state.commit_draft()
            if commit_result.get("ok"):
                self._bridge.settings_changed.emit(self._settings_state.get_json())
                self._bridge.dirty_changed.emit(False)
                self._bridge._apply_side_effects(commit_result.get("applied", {}))
            else:
                self.action_minimize_on_exit.setChecked(not checked)
        else:
            self.action_minimize_on_exit.setChecked(not checked)

    def _toggle_run_at_startup(self):
        checked = self.action_run_at_startup.isChecked()
        result = self._settings_state.apply_draft({"run_at_startup": checked})
        if result.get("ok"):
            commit_result = self._settings_state.commit_draft()
            if commit_result.get("ok"):
                self._bridge.settings_changed.emit(self._settings_state.get_json())
                self._bridge.dirty_changed.emit(False)
                self._bridge._apply_side_effects(commit_result.get("applied", {}))
            else:
                self.action_run_at_startup.setChecked(not checked)
        else:
            self.action_run_at_startup.setChecked(not checked)

    def _toggle_theme(self):
        new_mode = toggle_theme_mode(self._theme_mode, get_windows_theme())
        self._apply_theme_mode(new_mode)

    def _apply_theme_mode(self, mode: str):
        self._theme_mode = normalize_theme_mode(mode, DEFAULTS["theme"])
        if self._theme_mode == "system":
            self._start_theme_sync()
        else:
            self._stop_theme_sync()
            self.set_theme(self._theme_mode)

    def _start_theme_sync(self):
        self._sync_system_theme()

    def _stop_theme_sync(self):
        pass  # Theme changes arrive via colorSchemeChanged; nothing to stop.

    def _sync_system_theme(self):
        if self._theme_mode != "system":
            return
        effective = resolve_theme("system", get_windows_theme())
        if effective != self._theme_state:
            self.set_theme(effective)

    def set_theme(self, theme: str):
        self._theme_state = theme
        self._bridge.theme_applied.emit(theme)

    def center_on_screen(self):
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
    # Resizable window via WM_NCHITTEST
    # ------------------------------------------------------------------

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                # Convert screen coords to window coords
                pos = self.mapFromGlobal(QtCore.QPoint(x, y))
                rect = self.rect()
                BORDER = 4  # 4px grab zone
                result = 0
                # Edges and corners
                if pos.x() <= BORDER:
                    if pos.y() <= BORDER:
                        result = 13  # HTTOPLEFT
                    elif pos.y() >= rect.height() - BORDER:
                        result = 16  # HTBOTTOMLEFT
                    else:
                        result = 10  # HTLEFT
                elif pos.x() >= rect.width() - BORDER:
                    if pos.y() <= BORDER:
                        result = 14  # HTTOPRIGHT
                    elif pos.y() >= rect.height() - BORDER:
                        result = 17  # HTBOTTOMRIGHT
                    else:
                        result = 11  # HTRIGHT
                elif pos.y() <= BORDER:
                    result = 12  # HTTOP
                elif pos.y() >= rect.height() - BORDER:
                    result = 15  # HTBOTTOM
                if result:
                    return True, result

                # Title bar drag zone (D-01, D-02, D-03)
                if (
                    pos.y() < TITLE_BAR_HEIGHT
                    and pos.x() >= BORDER
                    and pos.x() < rect.width() - CONTROLS_WIDTH
                ):
                    return True, 2  # HTCAPTION

        return super().nativeEvent(event_type, message)
