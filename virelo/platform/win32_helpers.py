"""Win32 utility functions: DPI, monitor rect, fullscreen detection, window geometry."""

import ctypes
import logging
from ctypes import wintypes

import win32api
import win32con
import win32gui

LOG = logging.getLogger("Virelo")

# ctypes.windll only exists on Windows. Guard the module-level access so the
# package can be imported for unit-test collection on Linux CI, where these
# functions are never actually called.
try:
    USER32 = ctypes.windll.user32
    KERNEL32 = ctypes.windll.kernel32
except AttributeError:  # pragma: no cover - non-Windows import path
    USER32 = None
    KERNEL32 = None

if USER32 is not None:
    # Explicit signatures for the calls we use with window handles. Without a
    # restype, ctypes truncates HWNDs to a signed 32-bit int, which breaks
    # equality checks against Qt's unsigned winId().
    USER32.GetForegroundWindow.restype = wintypes.HWND
    USER32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    USER32.GetWindowRect.restype = wintypes.BOOL
    USER32.MoveWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.BOOL,
    ]
    USER32.MoveWindow.restype = wintypes.BOOL

LVM_FIRST = 0x1000
LVM_GETHEADER = LVM_FIRST + 31
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_SETCOLUMNWIDTH = LVM_FIRST + 30

LVSCW_AUTOSIZE = -1
LVSCW_AUTOSIZE_USEHEADER = -2

HDM_FIRST = 0x1200
HDM_GETITEMCOUNT = HDM_FIRST + 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDBLCLK = 0x0203
SMTO_ABORTIFHUNG = 0x0002

UIA_BoundingRectanglePropertyId = 30001
UIA_ControlTypePropertyId = 30003
UIA_NativeWindowHandlePropertyId = 30020
UIA_HeaderItemControlTypeId = 50035

TreeScope_Children = 2
TreeScope_Subtree = 7


def _enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_monitor_rect(hwnd: int, use_work_area: bool = True) -> tuple[int, int, int, int] | None:
    """
    Get monitor rectangle for a given window.

    Args:
        hwnd: Window handle
        use_work_area: If True, return work area (taskbar-adjusted).
                      If False, return full monitor bounds (for fullscreen detection).

    Returns:
        (left, top, right, bottom) tuple or None
    """
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info = win32api.GetMonitorInfo(monitor)
        if use_work_area:
            # Prefer work area for normal snapping (respects taskbar)
            return info.get("Work") or info.get("Monitor")
        else:
            # Prefer full monitor for fullscreen detection (ignores taskbar)
            return info.get("Monitor") or info.get("Work")
    except Exception:
        return None


def _get_window_dwm_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """
    Get window rect using DWM extended frame bounds if available.

    DWM extended frame bounds exclude invisible borders and give the true
    visual bounds of the window, which is more accurate for fullscreen detection.

    Falls back to GetWindowRect if DWM attributes are not available.

    Returns:
        (left, top, right, bottom) tuple or None
    """
    try:
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        rect = wintypes.RECT()
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if result == 0:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    # Fallback to standard GetWindowRect
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
    """
    Check if window is fullscreen using true monitor bounds.

    Uses DWM extended frame bounds for accurate window rect,
    and full monitor bounds (not work area) for comparison.

    Args:
        hwnd: Window handle
        rect: Optional pre-fetched window rect (for optimization)
        monitor_rect: Optional pre-fetched monitor rect (must be FULL monitor bounds)

    Returns:
        True if window appears to be fullscreen
    """
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if monitor_rect is None:
            # IMPORTANT: Use full monitor bounds, not work area
            monitor_rect = get_monitor_rect(hwnd, use_work_area=False)
        if monitor_rect is None:
            return False

        # Try DWM extended frame bounds first for accuracy
        if rect is None:
            dwm_rect = _get_window_dwm_rect(hwnd)
            if dwm_rect:
                return _rect_matches_monitor(dwm_rect, monitor_rect)
            # Fallback to standard GetWindowRect
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


def _exit_fullscreen(hwnd: int):
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


def _as_hwnd(v: int) -> int:
    try:
        return int(ctypes.c_size_t(int(v)).value or 0)
    except Exception:
        return 0


def _get_children(hwnd: int):
    try:
        child = win32gui.GetWindow(hwnd, win32con.GW_CHILD)
        while child:
            yield child
            child = win32gui.GetWindow(child, win32con.GW_HWNDNEXT)
    except Exception:
        LOG.debug("GetWindow failed for hwnd=%s", hwnd, exc_info=True)
        return


def _class_name(hwnd: int) -> str:
    try:
        return win32gui.GetClassName(hwnd)
    except Exception:
        return ""


def _get_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        rc = wintypes.RECT()
        if USER32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return rc.left, rc.top, rc.right, rc.bottom
    except Exception:
        pass
    return None


def _area(hwnd: int) -> int:
    r = _get_rect(hwnd)
    if not r:
        return 0
    left_edge, top_edge, right_edge, bottom_edge = r
    return max(0, right_edge - left_edge) * max(0, bottom_edge - top_edge)


def _ancestor_classes(hwnd: int, depth: int = 8) -> tuple[str, ...]:
    out = []
    try:
        cur = hwnd
        for _ in range(depth):
            cur = win32gui.GetParent(cur)
            if not cur:
                break
            out.append(_class_name(cur))
    except Exception:
        pass
    return tuple(out)


def _find_descendant_by_class(
    hwnd_start: int, class_names: tuple, max_depth: int = 12
) -> int | None:
    try:
        class_names = tuple(n.lower() for n in class_names)
        queue = [(hwnd_start, 0)]
        visited = set()
        while queue:
            hwnd, depth = queue.pop(0)
            if hwnd in visited or depth > max_depth:
                continue
            visited.add(hwnd)
            try:
                cname = win32gui.GetClassName(hwnd).lower()
            except Exception:
                cname = ""
            if cname in class_names and hwnd != hwnd_start:
                return hwnd
            for ch in _get_children(hwnd):
                queue.append((ch, depth + 1))
    except Exception as e:
        LOG.exception("find_descendant_by_class failed", exc_info=e)
    return None


def _collect_descendants_by_class(
    hwnd_start: int, class_names: tuple, max_depth: int = 12
) -> tuple[int, ...]:
    found = []
    try:
        class_names = tuple(n.lower() for n in class_names)
        queue = [(hwnd_start, 0)]
        visited = set()
        while queue:
            hwnd, depth = queue.pop(0)
            if hwnd in visited or depth > max_depth:
                continue
            visited.add(hwnd)
            try:
                cname = win32gui.GetClassName(hwnd).lower()
            except Exception:
                cname = ""
            if cname in class_names and hwnd != hwnd_start:
                found.append(hwnd)
            for ch in _get_children(hwnd):
                queue.append((ch, depth + 1))
    except Exception as e:
        LOG.exception("collect_descendants_by_class failed", exc_info=e)
    return tuple(found)


def _is_window_interactive(hwnd: int) -> bool:
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


def _looks_like_preview(hwnd: int) -> bool:
    """Heuristic: any ancestor class mentions 'preview'."""
    try:
        for cls in _ancestor_classes(hwnd, depth=10):
            if "preview" in (cls or "").lower():
                return True
    except Exception:
        pass
    return False


def _find_best_folder_listview(top_hwnd: int) -> int | None:
    """
    Prefer the FolderView listview under SHELLDLL_DefView.
    If multiple SysListView32 exist (e.g., Preview pane), choose the largest non-preview one.
    """
    defview = _find_descendant_by_class(top_hwnd, ("SHELLDLL_DefView",), max_depth=12)
    candidates = []
    if defview:
        candidates = list(_collect_descendants_by_class(defview, ("SysListView32",), max_depth=6))
    if not candidates:
        candidates = list(_collect_descendants_by_class(top_hwnd, ("SysListView32",), max_depth=14))
    if not candidates:
        return None

    filtered = [h for h in candidates if _is_window_interactive(h) and not _looks_like_preview(h)]
    if not filtered:
        filtered = [h for h in candidates if _is_window_interactive(h)]
    if not filtered:
        filtered = candidates

    best = max(filtered, key=_area, default=None)
    return _as_hwnd(best) if best else None
