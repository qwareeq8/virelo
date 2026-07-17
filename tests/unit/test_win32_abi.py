"""Tests for pointer-safe Win32 ABI declarations and call paths."""

from __future__ import annotations

import ctypes
import importlib
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    import comtypes as _comtypes  # type: ignore[import-untyped]
except ImportError:
    _HAS_COMTYPES_ABI = False
else:
    _HAS_COMTYPES_ABI = hasattr(_comtypes, "GUID") and hasattr(_comtypes, "POINTER")

from virelo.platform.win32_abi import (
    ADVAPI32,
    DWMAPI,
    DWORD,
    HANDLE,
    HINSTANCE,
    HWND,
    KERNEL32,
    LPARAM,
    LRESULT,
    PROCESS_INFORMATION,
    SECURITY_ATTRIBUTES,
    SHELL32,
    STARTUPINFOW,
    USER32,
    WPARAM,
    handle_value,
)

HIGH_HWND = 0x1234_5678_ABCD_EF01
HIGH_PROCESS = 0x2234_5678_ABCD_EF02
HIGH_TOKEN = 0x3234_5678_ABCD_EF03
HIGH_PRIMARY_TOKEN = 0x4234_5678_ABCD_EF04


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="A 64-bit process is required.")
def test_pointer_sized_types_preserve_high_handle_bits() -> None:
    """Pointer-sized Win32 aliases preserve values above 32 bits."""

    assert ctypes.sizeof(HANDLE) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(HWND) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(HINSTANCE) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(WPARAM) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(LPARAM) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(LRESULT) == ctypes.sizeof(ctypes.c_void_p)
    assert handle_value(HANDLE(HIGH_HWND)) == HIGH_HWND


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="A 64-bit process is required.")
def test_pointer_sensitive_structures_have_64_bit_windows_layouts() -> None:
    """Process-launch structures retain their documented 64-bit layouts."""

    assert ctypes.sizeof(SECURITY_ATTRIBUTES) == 24
    assert ctypes.sizeof(STARTUPINFOW) == 104
    assert ctypes.sizeof(PROCESS_INFORMATION) == 24


def test_singleton_mutex_path_preserves_high_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    """The singleton check closes the same pointer-sized handle it opened."""

    app_main = importlib.import_module("virelo.app.__main__")
    kernel32 = SimpleNamespace(
        OpenMutexW=MagicMock(return_value=HIGH_PROCESS),
        CloseHandle=MagicMock(return_value=True),
    )
    monkeypatch.setattr(app_main, "KERNEL32", kernel32)

    assert app_main._instance_already_running() is True
    kernel32.CloseHandle.assert_called_once_with(HIGH_PROCESS)


def test_focus_path_preserves_high_hwnd(monkeypatch: pytest.MonkeyPatch) -> None:
    """The focus path finds only a marked Virelo window and preserves its high HWND."""

    app_main = importlib.import_module("virelo.app.__main__")

    def enumerate_windows(callback, context):
        assert not callback(HIGH_HWND, context)
        return True

    user32 = SimpleNamespace(
        EnumWindows=MagicMock(side_effect=enumerate_windows),
        GetPropW=MagicMock(return_value=1),
        ShowWindow=MagicMock(return_value=True),
        SetForegroundWindow=MagicMock(return_value=True),
    )
    monkeypatch.setattr(app_main, "USER32", user32)

    app_main._focus_running_instance()

    user32.ShowWindow.assert_called_once_with(HIGH_HWND, 5)
    user32.SetForegroundWindow.assert_called_once_with(HIGH_HWND)


def test_focus_path_ignores_an_unmarked_same_title_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrelated window cannot be focused merely because its title is Virelo."""

    app_main = importlib.import_module("virelo.app.__main__")

    def enumerate_windows(callback, context):
        assert callback(HIGH_HWND, context)
        return True

    user32 = SimpleNamespace(
        EnumWindows=MagicMock(side_effect=enumerate_windows),
        GetPropW=MagicMock(return_value=0),
        ShowWindow=MagicMock(return_value=True),
        SetForegroundWindow=MagicMock(return_value=True),
    )
    monkeypatch.setattr(app_main, "USER32", user32)

    app_main._focus_running_instance()

    user32.ShowWindow.assert_not_called()
    user32.SetForegroundWindow.assert_not_called()


def _store_dword(pointer: Any, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = value


def _store_handle(pointer: Any, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(HANDLE)).contents.value = value


def test_shell_token_path_preserves_all_high_handles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shell token duplication never narrows HWND, process, or token handles."""

    from virelo.services import explorer_views

    def get_shell_pid(_hwnd: int, pid: Any) -> int:
        _store_dword(pid, 4321)
        return 1

    def open_process_token(_process: int, _access: int, token: Any) -> int:
        _store_handle(token, HIGH_TOKEN)
        return 1

    def duplicate_token(
        _token: Any,
        _access: int,
        _attributes: Any,
        _level: int,
        _kind: int,
        primary: Any,
    ) -> int:
        _store_handle(primary, HIGH_PRIMARY_TOKEN)
        return 1

    user32 = SimpleNamespace(
        GetShellWindow=MagicMock(return_value=HIGH_HWND),
        GetWindowThreadProcessId=MagicMock(side_effect=get_shell_pid),
    )
    kernel32 = SimpleNamespace(
        OpenProcess=MagicMock(return_value=HIGH_PROCESS),
        CloseHandle=MagicMock(return_value=True),
    )
    advapi32 = SimpleNamespace(
        OpenProcessToken=MagicMock(side_effect=open_process_token),
        DuplicateTokenEx=MagicMock(side_effect=duplicate_token),
    )
    monkeypatch.setattr(explorer_views, "USER32", user32)
    monkeypatch.setattr(explorer_views, "KERNEL32", kernel32)
    monkeypatch.setattr(explorer_views, "ADVAPI32", advapi32)

    primary = explorer_views._shell_token()

    assert handle_value(primary) == HIGH_PRIMARY_TOKEN
    assert user32.GetWindowThreadProcessId.call_args.args[0] == HIGH_HWND
    assert advapi32.OpenProcessToken.call_args.args[0] == HIGH_PROCESS
    assert handle_value(advapi32.DuplicateTokenEx.call_args.args[0]) == HIGH_TOKEN
    closed = [handle_value(call.args[0]) for call in kernel32.CloseHandle.call_args_list]
    assert closed == [HIGH_TOKEN, HIGH_PROCESS]


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 DLL prototypes require Windows.")
def test_loaded_dll_functions_have_pointer_safe_prototypes() -> None:
    """The real DLL function objects expose exact handle types."""

    assert KERNEL32.OpenMutexW.restype is HANDLE
    assert KERNEL32.CloseHandle.argtypes == (HANDLE,)
    assert KERNEL32.OpenProcess.restype is HANDLE
    assert KERNEL32.QueryFullProcessImageNameW.argtypes == (
        HANDLE,
        DWORD,
        ctypes.c_wchar_p,
        ctypes.POINTER(DWORD),
    )
    assert USER32.GetForegroundWindow.restype is HWND
    assert USER32.FindWindowW.restype is HWND
    assert USER32.ShowWindow.argtypes[0] is HWND
    assert USER32.SetForegroundWindow.argtypes == (HWND,)
    assert USER32.GetShellWindow.restype is HWND
    assert USER32.GetWindowThreadProcessId.argtypes[0] is HWND
    assert USER32.SetPropW.argtypes == (HWND, ctypes.c_wchar_p, HANDLE)
    assert USER32.GetPropW.restype is HANDLE
    assert USER32.RemovePropW.restype is HANDLE
    assert SHELL32.ShellExecuteW.restype is HINSTANCE
    assert DWMAPI.DwmGetWindowAttribute.argtypes[0] is HWND
    assert ADVAPI32.OpenProcessToken.argtypes[0] is HANDLE
    assert ADVAPI32.DuplicateTokenEx.argtypes[0] is HANDLE
    assert ADVAPI32.CreateProcessWithTokenW.argtypes[0] is HANDLE


@pytest.mark.skipif(
    sys.platform != "win32" or not _HAS_COMTYPES_ABI,
    reason="The real Windows comtypes ABI is required.",
)
def test_query_service_uses_guid_pointers() -> None:
    """IServiceProvider passes both GUID inputs by pointer on every ABI."""

    from comtypes import GUID, POINTER  # type: ignore[import-untyped]

    from virelo.services.explorer_columns import IServiceProvider

    query_service = IServiceProvider._methods_[0]
    assert query_service.argtypes[0] == POINTER(GUID)
    assert query_service.argtypes[1] == POINTER(GUID)
