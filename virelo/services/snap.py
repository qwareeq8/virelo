"""Snap service, MultiPressHotkeyListener, and SnapRestoreController engine.

MultiPressHotkeyListener detects multi-press keyboard patterns and emits a trigger signal.
SnapRestoreController performs window snap and restore operations.
SnapService wraps both so bridge.py can trigger snap actions without depending
on class internals.
"""

import ctypes
import logging
import threading
import time
from collections import deque
from ctypes import wintypes

import keyboard
import win32con
import win32gui
from PySide6 import QtCore

from virelo.app.config import normalize_snap_presses
from virelo.platform.win32_helpers import (
    USER32,
    _exit_fullscreen,
    _is_window_fullscreen,
    _should_skip_snap_for_game,
    get_monitor_rect,
)

LOG = logging.getLogger("Virelo")


def calculate_snap_position(
    monitor_left: int,
    monitor_top: int,
    monitor_width: int,
    monitor_height: int,
    width_pct: int,
    height_pct: int,
) -> tuple:
    """Calculate snap target position (x, y, w, h) for a resizable window."""
    w = monitor_width * width_pct // 100
    h = monitor_height * height_pct // 100
    x = monitor_left + (monitor_width - w) // 2
    y = monitor_top + (monitor_height - h) // 2
    return (x, y, w, h)


class MultiPressHotkeyListener(QtCore.QObject):
    """Detects multi-press keyboard patterns and emits trigger signal."""

    triggered = QtCore.Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._press_times: deque[float] = deque(
            maxlen=normalize_snap_presses(self.settings.snap_presses)
        )
        self._press_lock = threading.Lock()
        self._held = False
        self.current_key = str(settings.snap_key)
        self.restore_key = str(getattr(settings, "restore_key", "ctrl"))
        self._press_hook = keyboard.on_press_key(self.current_key, self._on_press)
        self._release_hook = keyboard.on_release_key(self.current_key, self._on_release)

    def cleanup(self):
        try:
            keyboard.unhook(self._press_hook)
        except Exception:
            pass
        try:
            keyboard.unhook(self._release_hook)
        except Exception:
            pass

    def update_binding(self, new_key: str):
        try:
            keyboard.unhook(self._press_hook)
        except Exception:
            pass
        try:
            keyboard.unhook(self._release_hook)
        except Exception:
            pass
        self.current_key = new_key
        self._press_hook = keyboard.on_press_key(self.current_key, self._on_press)
        self._release_hook = keyboard.on_release_key(self.current_key, self._on_release)
        with self._press_lock:
            self._press_times = deque(
                self._press_times,
                maxlen=normalize_snap_presses(self.settings.snap_presses),
            )

    def update_restore_key(self, new_key: str):
        self.restore_key = new_key

    def update_press_limit(self, new_limit: int):
        with self._press_lock:
            self._press_times = deque(self._press_times, maxlen=new_limit)

    def _on_press(self, event):
        if not self.settings.enable_snap:
            return
        if not self._held:
            self._held = True
            now = time.time()
            interval = int(self.settings.snap_interval) / 1000.0
            press_target = normalize_snap_presses(self.settings.snap_presses)
            should_trigger = False
            restore = False
            with self._press_lock:
                self._press_times = deque(
                    [t for t in self._press_times if now - t <= interval],
                    maxlen=press_target,
                )
                self._press_times.append(now)
                if len(self._press_times) >= press_target:
                    self._press_times.clear()
                    restore = keyboard.is_pressed(self.restore_key)
                    should_trigger = True
            if should_trigger:
                self.triggered.emit(restore)

    def _on_release(self, event):
        self._held = False


# ------------------------------------------------------------------------------
# SHIFT triple-press snap and restore
# ------------------------------------------------------------------------------


class SnapRestoreController(QtCore.QObject):
    """Performs window snap and restore operations."""

    blocked = QtCore.Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._orig_sizes: dict[int, dict[str, tuple[int, int, int, int] | bool]] = {}
        self._fetch_open_windows()

    def _fetch_open_windows(self):
        def enum_windows_callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            try:
                placement = win32gui.GetWindowPlacement(hwnd)
                rc = wintypes.RECT()
                USER32.GetWindowRect(hwnd, ctypes.byref(rc))
                if placement[1] == win32con.SW_MAXIMIZE:
                    self._orig_sizes[hwnd] = {
                        "rect": (
                            rc.left,
                            rc.top,
                            rc.right - rc.left,
                            rc.bottom - rc.top,
                        ),
                        "maximized": True,
                    }
                else:
                    if rc.right - rc.left > 0 and rc.bottom - rc.top > 0:
                        self._orig_sizes[hwnd] = {
                            "rect": (
                                rc.left,
                                rc.top,
                                rc.right - rc.left,
                                rc.bottom - rc.top,
                            ),
                            "maximized": False,
                        }
            except Exception as e:
                LOG.exception("EnumWindows callback failed.", exc_info=e)
            return True

        self._orig_sizes.clear()
        win32gui.EnumWindows(enum_windows_callback, None)

    def _prune_closed_windows(self):
        existing = set()

        def enum_cb(hwnd, _):
            existing.add(hwnd)
            return True

        win32gui.EnumWindows(enum_cb, None)
        stale = [hwnd for hwnd in list(self._orig_sizes.keys()) if hwnd not in existing]
        for hwnd in stale:
            self._orig_sizes.pop(hwnd, None)

    @QtCore.Slot(bool)
    def perform(self, restore: bool):
        self._prune_closed_windows()
        hwnd = USER32.GetForegroundWindow()
        if not hwnd:
            return
        try:
            if restore:
                self._restore(hwnd)
            else:
                self._snap(hwnd)
        except Exception as e:
            LOG.exception("SnapRestoreController.perform failed.", exc_info=e)

    def _snap(self, hwnd: int):
        from PySide6 import QtWidgets

        for widget in QtWidgets.QApplication.topLevelWidgets():
            if int(widget.winId()) == hwnd:
                LOG.debug("Snap: skipping Virelo's own window hwnd=%s", hwnd)
                return  # Skip entirely per SNAP-03

        def refresh_rect():
            rect = wintypes.RECT()
            USER32.GetWindowRect(hwnd, ctypes.byref(rect))
            return rect

        rc = refresh_rect()
        if hwnd not in self._orig_sizes:
            placement = win32gui.GetWindowPlacement(hwnd)
            was_maximized = placement[1] == win32con.SW_MAXIMIZE
            self._orig_sizes[hwnd] = {
                "rect": (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top),
                "maximized": was_maximized,
            }

        # Get full monitor bounds for accurate fullscreen detection
        mon_full = get_monitor_rect(hwnd, use_work_area=False)
        if not mon_full:
            return

        # Check if window is fullscreen using full monitor bounds
        full_screen = _is_window_fullscreen(hwnd, rect=rc, monitor_rect=mon_full)

        # Skip snapping if game mode enabled and window is fullscreen borderless
        if _should_skip_snap_for_game(hwnd, self.settings, full_screen):
            LOG.info("Game mode: skipped snap for fullscreen window hwnd=%s", hwnd)
            self.blocked.emit("Game mode: fullscreen window not moved")
            return

        # Get work area for normal snapping sizing
        mon = get_monitor_rect(hwnd, use_work_area=True)
        if not mon:
            return
        left_edge, top_edge, right_edge, bottom_edge = [int(x) for x in mon]
        monitor_width = int(right_edge - left_edge)
        monitor_height = int(bottom_edge - top_edge)

        # If not a game but is fullscreen, exit fullscreen first (existing behavior for apps)
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if full_screen:
            _exit_fullscreen(hwnd)
            rc = refresh_rect()

        is_resizable = bool(style & win32con.WS_SIZEBOX)

        if is_resizable:
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] == win32con.SW_MAXIMIZE:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            w = int(monitor_width * int(self.settings.width_pct) // 100)
            h = int(monitor_height * int(self.settings.height_pct) // 100)
            x = left_edge + ((monitor_width - w) // 2)
            y = top_edge + ((monitor_height - h) // 2)
            if (rc.right - rc.left, rc.bottom - rc.top, rc.left, rc.top) != (
                w,
                h,
                x,
                y,
            ):
                USER32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)
        else:
            w = max(660, int(monitor_width * 0.35))
            h = max(260, int(monitor_height * 0.25))
            x = left_edge + ((monitor_width - w) // 2)
            y = top_edge + ((monitor_height - h) // 2)
            USER32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)

    def _restore(self, hwnd: int):
        from PySide6 import QtWidgets

        for widget in QtWidgets.QApplication.topLevelWidgets():
            if int(widget.winId()) == hwnd:
                LOG.debug("Restore: skipping Virelo's own window hwnd=%s", hwnd)
                return  # Skip entirely per D-05
        orig = self._orig_sizes.pop(hwnd, None)
        if not orig:
            return
        was_maximized = orig.get("maximized", False) if isinstance(orig, dict) else False
        rect = orig["rect"] if isinstance(orig, dict) else orig
        mon = get_monitor_rect(hwnd)
        if not mon:
            return
        left_edge, top_edge, right_edge, bottom_edge = mon
        monitor_width, monitor_height = (
            right_edge - left_edge,
            bottom_edge - top_edge,
        )

        rc = wintypes.RECT()
        USER32.GetWindowRect(hwnd, ctypes.byref(rc))
        win_left, win_top, win_right, win_bottom = rc.left, rc.top, rc.right, rc.bottom
        if (
            win_left <= left_edge
            and win_top <= top_edge
            and win_right >= right_edge
            and win_bottom >= bottom_edge
        ):
            return

        if was_maximized:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        else:
            left, top, width, height = rect
            x = left_edge + ((monitor_width - width) // 2)
            y = top_edge + ((monitor_height - height) // 2)
            USER32.MoveWindow(hwnd, x, y, width, height, True)


class SnapService:
    """Narrow API surface for snap/restore actions."""

    def __init__(self, shift_mgr):
        """Accept a SnapRestoreController instance (or None during early init)."""
        self._mgr = shift_mgr
        self._listener = None

    def set_manager(self, mgr):
        """Set or replace the SnapRestoreController instance."""
        self._mgr = mgr

    def set_listener(self, listener):
        """Set or replace the MultiPressHotkeyListener instance."""
        self._listener = listener

    def test_snap(self) -> dict:
        """Trigger a test snap (same as pressing "Test snap" button)."""
        if self._mgr is None:
            return {"ok": False, "error": "Snap manager not initialized"}
        try:
            self._mgr.perform(False)
            return {"ok": True, "message": "Snap test applied to the active window."}
        except Exception as e:
            LOG.exception("test_snap failed")
            return {"ok": False, "error": str(e)}

    def update_binding(self, key: str):
        """Update the snap key binding."""
        if self._listener:
            self._listener.update_binding(key)

    def update_restore_key(self, key: str):
        """Update the restore key binding."""
        if self._listener:
            self._listener.update_restore_key(key)

    def update_press_limit(self, count: int):
        """Update the snap press count."""
        if self._listener:
            self._listener.update_press_limit(count)
