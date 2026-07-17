"""Tests for startup shortcut helpers that do not require a live COM server."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from virelo.platform.startup import ensure_dispatch, select_pythonw_executable


def test_uninstall_helper_removes_only_current_user_startup_link(
    monkeypatch, tmp_path: Path
) -> None:
    """Installer cleanup removes the original user's Virelo startup link without elevation."""

    from virelo.app import __main__ as app_main

    startup = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True)
    shortcut = startup / "Virelo.lnk"
    shortcut.write_text("test", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert app_main._remove_current_user_startup_shortcut() == 0
    assert not shortcut.exists()


def test_select_pythonw_executable_preserves_mixed_case_prefix() -> None:
    """A mixed-case Python filename is replaced without corrupting its path."""
    executable = r"C:\Tools\Python312\PyThOn.ExE"

    selected = select_pythonw_executable(
        executable,
        exists=lambda path: path == r"C:\Tools\Python312\pythonw.exe",
    )

    assert selected == r"C:\Tools\Python312\pythonw.exe"


def test_select_pythonw_executable_keeps_original_when_sibling_is_missing() -> None:
    """Development startup remains usable when pythonw.exe is unavailable."""
    executable = r"C:\Tools\python.exe"
    assert select_pythonw_executable(executable, exists=lambda _path: False) == executable


def _install_fake_win32com(monkeypatch, dispatch, ensure):
    client = types.ModuleType("win32com.client")
    client.Dispatch = dispatch
    client.gencache = types.SimpleNamespace(EnsureDispatch=ensure)
    win32com = types.ModuleType("win32com")
    win32com.client = client
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)


def test_ensure_dispatch_uses_normal_dispatch_when_cache_is_healthy(monkeypatch) -> None:
    """The normal path does not mutate or regenerate the COM cache."""
    expected = object()
    dispatch = MagicMock(return_value=expected)
    ensure = MagicMock()
    _install_fake_win32com(monkeypatch, dispatch, ensure)

    assert ensure_dispatch("WScript.Shell") is expected
    dispatch.assert_called_once_with("WScript.Shell")
    ensure.assert_not_called()


def test_ensure_dispatch_recovers_from_corrupt_generated_cache(monkeypatch, tmp_path) -> None:
    """An AttributeError purges generated wrappers and retries through gencache."""
    expected = object()
    dispatch = MagicMock(side_effect=AttributeError("corrupt wrapper"))
    ensure = MagicMock(return_value=expected)
    _install_fake_win32com(monkeypatch, dispatch, ensure)

    generated = types.ModuleType("win32com.gen_py.corrupt")
    monkeypatch.setitem(sys.modules, generated.__name__, generated)
    cache = tmp_path / "Temp" / "gen_py"
    cache.mkdir(parents=True)
    (cache / "broken.py").write_text("broken", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert ensure_dispatch("WScript.Shell") is expected
    assert generated.__name__ not in sys.modules
    assert not cache.exists()
    ensure.assert_called_once_with("WScript.Shell")


@pytest.mark.requires_qt
def test_startup_reconciliation_reports_saved_but_unsynchronized_state(monkeypatch) -> None:
    """A failed shortcut update is reported accurately and retried on the next launch."""
    from virelo.app import window as window_module

    monkeypatch.setattr(
        window_module,
        "sync_startup_shortcut",
        MagicMock(side_effect=OSError("shortcut is locked")),
    )
    main_window = window_module.MainWindow.__new__(window_module.MainWindow)
    main_window.settings = SimpleNamespace(run_at_startup=True)
    main_window._bridge = SimpleNamespace(snap_status=MagicMock())

    main_window._reconcile_startup_shortcut()

    message, timeout = main_window._bridge.snap_status.emit.call_args.args
    assert "setting is saved" in message
    assert "retry at the next launch" in message
    assert timeout == 8000
