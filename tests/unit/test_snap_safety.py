"""Regression tests for key rebinding, HWND reuse, and center-only snapping."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import win32con
from PySide6 import QtWidgets

from virelo.app.config import DEFAULTS
from virelo.bridge.capture_guard import CaptureGuard
from virelo.services import snap
from virelo.services.snap import (
    MultiPressHotkeyListener,
    SnapRestoreController,
    SnapService,
    calculate_center_position,
    should_center_without_resize,
)


def _settings(**overrides):
    values = {**DEFAULTS, **overrides}
    return SimpleNamespace(**values)


def _install_keyboard_fakes(monkeypatch):
    hooks = []
    unhooked = []

    def add_hook(key, _callback):
        hook = f"{key}-{len(hooks)}"
        hooks.append(hook)
        return hook

    scan_codes = {"shift": (42,), "ctrl": (29,), "alt": (56,)}
    monkeypatch.setattr(
        snap.keyboard,
        "key_to_scan_codes",
        scan_codes.__getitem__,
        raising=False,
    )
    monkeypatch.setattr(snap.keyboard, "on_press_key", add_hook, raising=False)
    monkeypatch.setattr(snap.keyboard, "on_release_key", add_hook, raising=False)
    monkeypatch.setattr(snap.keyboard, "unhook", unhooked.append, raising=False)
    monkeypatch.setattr(snap.keyboard, "is_pressed", lambda _key: False, raising=False)
    return hooks, unhooked


def test_listener_ignores_snap_key_while_capture_guard_is_active(monkeypatch) -> None:
    """Rebinding a key cannot accidentally fire the snap action being rebound."""
    _install_keyboard_fakes(monkeypatch)
    guard = CaptureGuard()
    listener = MultiPressHotkeyListener(_settings(snap_presses=1), guard)
    assert guard.try_start()

    def fail_if_snap_logic_runs():
        raise AssertionError("Capture reached snap timing logic.")

    monkeypatch.setattr(snap.time, "monotonic", fail_if_snap_logic_runs)

    listener._on_press(None)

    assert listener._held is False
    assert list(listener._press_times) == []


def test_test_snap_selects_the_first_safe_external_window_in_z_order(monkeypatch) -> None:
    """The target skips Virelo, shell, hidden, owned, and untitled windows."""
    controller = SnapRestoreController(_settings())
    monkeypatch.setattr(
        QtWidgets,
        "QApplication",
        SimpleNamespace(topLevelWidgets=lambda: [SimpleNamespace(winId=lambda: 10)]),
        raising=False,
    )
    monkeypatch.setattr(snap, "USER32", SimpleNamespace(GetForegroundWindow=lambda: 10))
    z_order = {10: 20, 20: 30, 30: 35, 35: 37, 37: 40, 40: 0}
    monkeypatch.setattr(
        snap.win32gui,
        "GetWindow",
        lambda hwnd, relation: z_order[hwnd] if relation == win32con.GW_HWNDNEXT else 0,
    )
    monkeypatch.setattr(
        snap.win32gui,
        "GetClassName",
        lambda hwnd: "WorkerW" if hwnd == 20 else "ApplicationWindow",
    )
    monkeypatch.setattr(snap.win32gui, "GetParent", lambda hwnd: 999 if hwnd == 35 else 0)
    monkeypatch.setattr(
        snap.win32gui,
        "GetWindowText",
        lambda hwnd: "   " if hwnd == 37 else f"Window {hwnd}",
    )
    monkeypatch.setattr(snap, "_is_window_interactive", lambda hwnd: hwnd != 30)

    assert controller.find_test_snap_target() == 40


def test_test_snap_never_selects_virelo_itself(monkeypatch) -> None:
    """A foreground Virelo window is not a fallback when no external target exists."""
    controller = SnapRestoreController(_settings())
    monkeypatch.setattr(
        QtWidgets,
        "QApplication",
        SimpleNamespace(topLevelWidgets=lambda: [SimpleNamespace(winId=lambda: 10)]),
        raising=False,
    )
    monkeypatch.setattr(snap, "USER32", SimpleNamespace(GetForegroundWindow=lambda: 10))
    monkeypatch.setattr(snap.win32gui, "GetWindow", lambda _hwnd, _relation: 0)
    monkeypatch.setattr(snap.win32gui, "GetClassName", lambda _hwnd: "VireloWindow")
    monkeypatch.setattr(snap, "_is_window_interactive", lambda _hwnd: True)

    assert controller.find_test_snap_target() is None
    assert controller._snap(10) is False


def test_snap_service_uses_the_explicit_external_test_target() -> None:
    """The service snaps the selected HWND without consulting foreground state again."""
    manager = SimpleNamespace(
        find_test_snap_target=MagicMock(return_value=40),
        snap_window_for_test=MagicMock(return_value=True),
        perform=MagicMock(),
    )
    service = SnapService(manager)

    assert service.test_snap() == {
        "ok": True,
        "message": "Snap test applied to the last eligible window.",
    }
    manager.find_test_snap_target.assert_called_once_with()
    manager.snap_window_for_test.assert_called_once_with(40)
    manager.perform.assert_not_called()


def test_snap_service_reports_when_no_external_test_target_exists() -> None:
    """The service gives actionable feedback instead of snapping Virelo as a fallback."""
    manager = SimpleNamespace(
        find_test_snap_target=MagicMock(return_value=None),
        snap_window_for_test=MagicMock(),
    )
    service = SnapService(manager)

    assert service.test_snap() == {
        "ok": False,
        "error": (
            "No window is eligible behind Virelo. Open or restore another window, then try again."
        ),
    }
    manager.snap_window_for_test.assert_not_called()


def test_listener_rejects_same_snap_and_restore_key_without_unhooking(monkeypatch) -> None:
    """A rejected collision leaves both active hooks and settings untouched."""
    hooks, unhooked = _install_keyboard_fakes(monkeypatch)
    listener = MultiPressHotkeyListener(_settings())

    assert listener.update_keys("ctrl", "ctrl") is False

    assert hooks == ["shift-0", "shift-1"]
    assert unhooked == []
    assert (listener.current_key, listener.restore_key) == ("shift", "ctrl")


def test_listener_rolls_back_when_new_release_hook_fails(monkeypatch) -> None:
    """A partial hook install is removed without disturbing the old binding."""
    hooks, unhooked = _install_keyboard_fakes(monkeypatch)
    listener = MultiPressHotkeyListener(_settings())

    def fail_release(key, _callback):
        if key == "alt":
            raise OSError("hook refused")
        hook = f"{key}-{len(hooks)}"
        hooks.append(hook)
        return hook

    monkeypatch.setattr(snap.keyboard, "on_release_key", fail_release)

    assert listener.update_keys("alt", "ctrl") is False

    assert unhooked == ["alt-2"]
    assert (listener.current_key, listener.restore_key) == ("shift", "ctrl")


@pytest.mark.parametrize("process_name", ["GoogleDriveFS.exe", "LIGHTBULB.EXE"])
def test_known_resize_hostile_processes_are_center_only(process_name: str) -> None:
    """Known resize-hostile apps preserve size even when they advertise WS_SIZEBOX."""
    assert should_center_without_resize(win32con.WS_SIZEBOX, process_name)


def test_non_resizable_windows_are_center_only() -> None:
    """A window without WS_SIZEBOX is centered without a resize attempt."""
    assert should_center_without_resize(0, "ordinary.exe")
    assert not should_center_without_resize(win32con.WS_SIZEBOX, "ordinary.exe")


def test_calculate_center_position_preserves_visible_frame_center() -> None:
    """Invisible DWM borders are offset while the raw size stays unchanged."""
    assert calculate_center_position(0, 0, 1920, 1040, 800, 600) == (560, 220)
    assert calculate_center_position(
        0,
        0,
        1920,
        1040,
        814,
        607,
        (7, 0, 7, 7),
    ) == (553, 220)


def test_prune_discards_geometry_when_hwnd_identity_changes(monkeypatch) -> None:
    """A recycled numeric HWND cannot inherit an earlier window's geometry."""
    controller = SnapRestoreController(_settings())
    controller._orig_sizes[42] = {
        "rect": (10, 20, 800, 600),
        "maximized": False,
        "identity": (100, 200, "OldClass"),
    }

    def enumerate_window(callback, context):
        callback(42, context)

    monkeypatch.setattr(snap.win32gui, "EnumWindows", enumerate_window)
    monkeypatch.setattr(snap, "_window_identity", lambda _hwnd: (101, 201, "NewClass"))

    controller._prune_closed_windows()

    assert 42 not in controller._orig_sizes


def test_prune_detects_same_process_hwnd_reuse_from_missing_token(monkeypatch) -> None:
    """The per-window property catches reuse even within one GUI thread and class."""
    controller = SnapRestoreController(_settings())
    identity = (100, 200, "SameClass")
    controller._orig_sizes[42] = {
        "rect": (10, 20, 800, 600),
        "maximized": False,
        "identity": identity,
        "identity_token": 0x1234_5678_ABCD_EF01,
    }

    def enumerate_window(callback, context):
        callback(42, context)

    monkeypatch.setattr(snap.win32gui, "EnumWindows", enumerate_window)
    monkeypatch.setattr(snap, "_window_identity", lambda _hwnd: identity)
    monkeypatch.setattr(
        snap,
        "USER32",
        SimpleNamespace(GetPropW=lambda _hwnd, _name: 0),
    )

    controller._prune_closed_windows()

    assert 42 not in controller._orig_sizes


class _FakeUser32:
    def __init__(
        self,
        rect=(100, 100, 900, 700),
        distort_first_resize=False,
        move_result=True,
    ):
        self.rect = rect
        self.distort_first_resize = distort_first_resize
        self.move_result = move_result
        self.moves = []

    def GetWindowRect(self, _hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = self.rect
        return True

    def MoveWindow(self, _hwnd, x, y, width, height, _repaint):
        self.moves.append((x, y, width, height))
        if not self.move_result:
            return False
        if self.distort_first_resize and len(self.moves) == 1:
            self.rect = (x, y, x + width - 100, y + height - 100)
        else:
            self.rect = (x, y, x + width, y + height)
        return True


def _patch_snap_runtime(monkeypatch, user32, *, process_name: str):
    monkeypatch.setattr(snap, "USER32", user32)
    monkeypatch.setattr(snap, "_window_identity", lambda _hwnd: (100, 200, "TestClass"))
    monkeypatch.setattr(snap, "_window_process_name", lambda _hwnd: process_name)
    monkeypatch.setattr(snap, "_get_window_dwm_rect", lambda _hwnd: None)
    monkeypatch.setattr(snap, "_is_window_fullscreen", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(snap, "_should_skip_snap_for_game", lambda *_args: False)
    monkeypatch.setattr(
        snap,
        "get_monitor_rect",
        lambda _hwnd, use_work_area=True: (
            (0, 0, 1920, 1040) if use_work_area else (0, 0, 1920, 1080)
        ),
    )
    monkeypatch.setattr(
        snap.win32gui,
        "GetWindowPlacement",
        lambda _hwnd: (0, 1, (0, 0), (0, 0), (0, 0, 0, 0)),
    )
    monkeypatch.setattr(
        snap.win32gui,
        "GetWindowLong",
        lambda _hwnd, _index: win32con.WS_SIZEBOX,
    )
    monkeypatch.setattr(
        QtWidgets,
        "QApplication",
        SimpleNamespace(topLevelWidgets=lambda: []),
        raising=False,
    )


def test_google_drive_is_centered_at_current_size(monkeypatch) -> None:
    """Google Drive receives a move-only operation at its original 800 by 600 size."""
    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="googledrivefs.exe")
    controller = SnapRestoreController(_settings())

    assert controller._snap(42)

    assert user32.moves == [(560, 220, 800, 600)]


def test_fullscreen_exit_refreshes_resizable_window_style(monkeypatch) -> None:
    """A restored fullscreen window uses its post-exit resize frame for snapping."""
    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="ordinary.exe")
    fullscreen_state = {"exited": False}
    monkeypatch.setattr(snap, "_is_window_fullscreen", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        snap,
        "_exit_fullscreen",
        lambda _hwnd: fullscreen_state.__setitem__("exited", True),
    )
    monkeypatch.setattr(
        snap.win32gui,
        "GetWindowLong",
        lambda _hwnd, _index: win32con.WS_SIZEBOX if fullscreen_state["exited"] else 0,
    )
    controller = SnapRestoreController(_settings())

    assert controller._snap(42)

    assert fullscreen_state["exited"] is True
    assert user32.moves[0][2:] == (1920 * 76 // 100, 1040 * 76 // 100)


def test_manual_move_between_snaps_refreshes_restore_geometry(monkeypatch) -> None:
    """A second snap restores to the user's latest unsnapped geometry."""

    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="googledrivefs.exe")
    controller = SnapRestoreController(_settings())

    assert controller._snap(42)
    user32.rect = (250, 150, 1150, 850)
    assert controller._snap(42)

    assert controller._orig_sizes[42]["rect"] == (250, 150, 900, 700)
    assert controller._orig_sizes[42]["snapped_rect"] == (510, 170, 900, 700)


def test_failed_monitor_lookup_does_not_arm_restore(monkeypatch) -> None:
    """A snap rejected before any window change leaves no restore record."""

    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="ordinary.exe")
    monkeypatch.setattr(snap, "get_monitor_rect", lambda *_args, **_kwargs: None)
    controller = SnapRestoreController(_settings())

    assert not controller._snap(42)
    assert 42 not in controller._orig_sizes


def test_game_mode_skip_does_not_arm_restore(monkeypatch) -> None:
    """A fullscreen game-mode rejection leaves no synthetic restore action."""

    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="ordinary.exe")
    monkeypatch.setattr(snap, "_should_skip_snap_for_game", lambda *_args: True)
    controller = SnapRestoreController(_settings())

    assert not controller._snap(42)
    assert 42 not in controller._orig_sizes


def test_failed_move_does_not_arm_restore(monkeypatch) -> None:
    """A rejected MoveWindow call leaves no false restore success path."""

    user32 = _FakeUser32(move_result=False)
    _patch_snap_runtime(monkeypatch, user32, process_name="ordinary.exe")
    controller = SnapRestoreController(_settings())

    assert not controller._snap(42)
    assert 42 not in controller._orig_sizes


def test_failed_restore_keeps_original_geometry(monkeypatch) -> None:
    """A failed restore remains retryable and does not consume saved geometry."""

    user32 = _FakeUser32()
    _patch_snap_runtime(monkeypatch, user32, process_name="googledrivefs.exe")
    controller = SnapRestoreController(_settings())
    assert controller._snap(42)
    user32.move_result = False

    assert not controller._restore(42)
    assert 42 in controller._orig_sizes


def test_resize_rejection_falls_back_to_centering_original_size(monkeypatch) -> None:
    """A window that distorts MoveWindow is returned to its original size and centered."""
    user32 = _FakeUser32(distort_first_resize=True)
    _patch_snap_runtime(monkeypatch, user32, process_name="ordinary.exe")
    controller = SnapRestoreController(_settings())

    assert controller._snap(42)

    assert len(user32.moves) == 2
    assert user32.moves[0][2:] == (1920 * 76 // 100, 1040 * 76 // 100)
    assert user32.moves[1] == (560, 220, 800, 600)
