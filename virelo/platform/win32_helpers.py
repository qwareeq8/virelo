"""Win32 utility functions for monitor, fullscreen, and window geometry."""

import ctypes
from ctypes import wintypes

import win32api
import win32con
import win32gui

from virelo.platform.win32_abi import DWMAPI, USER32


def get_monitor_rect(hwnd: int, use_work_area: bool = True) -> tuple[int, int, int, int] | None:
    """Return the monitor rectangle nearest a window.

    Args:
        hwnd: Window handle.
        use_work_area: If True, return work area (taskbar-adjusted).
            If False, return full monitor bounds for fullscreen detection.

    Returns:
        The ``(left, top, right, bottom)`` rectangle, or ``None`` on failure.
    """
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info = win32api.GetMonitorInfo(monitor)
        if use_work_area:
            # Prefer the work area for normal snapping so the taskbar remains visible.
            return info.get("Work") or info.get("Monitor")
        # Prefer full monitor bounds for fullscreen detection.
        return info.get("Monitor") or info.get("Work")
    except Exception:
        return None


def _get_window_dwm_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return a window's DWM extended frame bounds when available.

    DWM extended frame bounds exclude invisible borders and give the true
    visual bounds of the window, which is more accurate for fullscreen detection.

    Falls back to GetWindowRect if DWM attributes are not available.

    Returns:
        The ``(left, top, right, bottom)`` rectangle, or ``None`` on failure.
    """
    try:
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        rect = wintypes.RECT()
        result = DWMAPI.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if result == 0:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    # Fall back to the standard ``GetWindowRect`` API.
    return _get_rect(hwnd)


FULLSCREEN_TOLERANCE = 3


def _rect_matches_monitor(
    rect: tuple[int, int, int, int], monitor: tuple[int, int, int, int]
) -> bool:
    left, top, right, bottom = rect
    left_edge, top_edge, right_edge, bottom_edge = monitor
    return (
        abs(left - left_edge) <= FULLSCREEN_TOLERANCE
        and abs(top - top_edge) <= FULLSCREEN_TOLERANCE
        and abs(right - right_edge) <= FULLSCREEN_TOLERANCE
        and abs(bottom - bottom_edge) <= FULLSCREEN_TOLERANCE
    )


def _is_window_fullscreen(
    hwnd: int,
    rect: wintypes.RECT | None = None,
    monitor_rect: tuple[int, int, int, int] | None = None,
) -> bool:
    """Return whether a window covers its monitor's full bounds.

    DWM extended frame bounds provide an accurate visible rectangle. The full
    monitor bounds, rather than the work area, provide the comparison target.

    Args:
        hwnd: Window handle.
        rect: Optional pre-fetched window rectangle.
        monitor_rect: Optional pre-fetched full monitor rectangle.

    Returns:
        ``True`` if the window appears to be fullscreen.
    """
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if monitor_rect is None:
            # Use full monitor bounds instead of the taskbar-adjusted work area.
            monitor_rect = get_monitor_rect(hwnd, use_work_area=False)
        if monitor_rect is None:
            return False

        # Prefer DWM extended frame bounds for visual accuracy.
        if rect is None:
            dwm_rect = _get_window_dwm_rect(hwnd)
            if dwm_rect:
                return _rect_matches_monitor(dwm_rect, monitor_rect)
            # Fall back to the standard ``GetWindowRect`` API.
            rect = wintypes.RECT()
            USER32.GetWindowRect(hwnd, ctypes.byref(rect))

        rect_vals = (rect.left, rect.top, rect.right, rect.bottom)
        return _rect_matches_monitor(rect_vals, monitor_rect)
    except Exception:
        return False


def _looks_like_game_window(hwnd: int) -> bool:
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    except Exception:
        return False
    has_caption = bool(style & win32con.WS_CAPTION or style & win32con.WS_BORDER)
    is_popup = bool(style & win32con.WS_POPUP)
    return is_popup and not has_caption


def _should_skip_snap_for_game(hwnd: int, settings, full_screen: bool) -> bool:
    return (
        full_screen
        and getattr(settings, "game_mode_enabled", True)
        and _looks_like_game_window(hwnd)
    )


def _exit_fullscreen(hwnd: int) -> None:
    """Restore a maximized or borderless window before repositioning it."""
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] in (win32con.SW_MAXIMIZE, win32con.SW_SHOWMAXIMIZED):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if not style & win32con.WS_CAPTION:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass


def _get_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return a raw Win32 window rectangle, or ``None`` on failure."""
    try:
        rc = wintypes.RECT()
        if USER32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return rc.left, rc.top, rc.right, rc.bottom
    except Exception:
        pass
    return None


def _is_window_interactive(hwnd: int) -> bool:
    """Return whether a window is visible, restored, and nonempty."""
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if not win32gui.IsWindowVisible(hwnd):
            return False
        if win32gui.IsIconic(hwnd):
            return False
        rc = wintypes.RECT()
        USER32.GetWindowRect(hwnd, ctypes.byref(rc))
        return (rc.right - rc.left) > 0 and (rc.bottom - rc.top) > 0
    except Exception:
        return False
