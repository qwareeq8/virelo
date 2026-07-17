"""Regression tests for key rebinding, HWND reuse, and center-only snapping."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest
import win32con
from PySide6 import QtWidgets

from virelo.app.config import DEFAULTS
from virelo.bridge.capture_guard import CaptureGuard
from virelo.services import snap
from virelo.services.snap import (
    MultiPressHotkeyListener,
    SnapRestoreController,
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

    monkeypatch.setattr(snap.time, "time", fail_if_snap_logic_runs)

    listener._on_press(None)

    assert listener._held is False
    assert list(listener._press_times) == []


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
