"""Focused tests for MainWindow capture, shortcut, and shutdown ownership."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from virelo.bridge.capture_guard import CaptureGuard


class _CaptureThread:
    def __init__(self, *, stops_in_time: bool) -> None:
        self.stops_in_time = stops_in_time
        self.running = True
        self.quit = MagicMock()

    def wait(self, timeout: int) -> bool:
        assert timeout == 2000
        return self.stops_in_time

    def isRunning(self) -> bool:
        return self.running


@pytest.mark.requires_qt
def test_capture_timeout_keeps_thread_ownership_until_finished() -> None:
    """A timed-out hook thread keeps its references and exclusive capture guard."""
    from virelo.app.window import MainWindow

    guard = CaptureGuard()
    assert guard.try_start()
    thread = _CaptureThread(stops_in_time=False)
    worker = SimpleNamespace(stop=MagicMock())
    shortcut = SimpleNamespace(setEnabled=MagicMock())
    window = SimpleNamespace(
        _capture_guard=guard,
        _capture_thread=thread,
        _capture_worker=worker,
        _capture_target="snap",
        _frontend_shortcuts_enabled=True,
        _window_shortcuts=[shortcut],
    )
    window._refresh_window_shortcuts = lambda: MainWindow._refresh_window_shortcuts(window)
    window._on_capture_finished = lambda finished=None: MainWindow._on_capture_finished(
        window, finished
    )

    MainWindow._stop_capture_worker(window)

    assert window._capture_thread is thread
    assert window._capture_worker is worker
    assert guard.is_active

    thread.running = False
    MainWindow._on_capture_finished(window, thread)

    assert window._capture_thread is None
    assert window._capture_worker is None
    assert not guard.is_active
    shortcut.setEnabled.assert_called_with(True)


@pytest.mark.requires_qt
def test_native_shortcuts_are_disabled_during_key_capture() -> None:
    """Qt shortcuts cannot consume Ctrl+Enter while the global capture hook owns input."""
    from virelo.app.window import MainWindow

    guard = CaptureGuard()
    assert guard.try_start()
    shortcut = SimpleNamespace(setEnabled=MagicMock())
    window = SimpleNamespace(
        _capture_guard=guard,
        _frontend_shortcuts_enabled=True,
        _window_shortcuts=[shortcut],
    )

    MainWindow._refresh_window_shortcuts(window)

    shortcut.setEnabled.assert_called_once_with(False)


@pytest.mark.requires_qt
def test_background_shutdown_is_idempotent() -> None:
    """Repeated Qt and atexit cleanup paths perform blocking waits only once."""
    from virelo.app.window import MainWindow

    window = SimpleNamespace(
        _shutdown_started=False,
        _bridge=SimpleNamespace(wait_for_view_task=MagicMock()),
        _stop_capture_worker=MagicMock(),
        _explorer_service=SimpleNamespace(stop=MagicMock()),
        _stop_theme_sync=MagicMock(),
    )

    MainWindow._stop_background_threads(window)
    MainWindow._stop_background_threads(window)

    window._bridge.wait_for_view_task.assert_called_once_with()
    window._stop_capture_worker.assert_called_once_with()
    window._explorer_service.stop.assert_called_once_with()
    window._stop_theme_sync.assert_called_once_with()


@pytest.mark.requires_qt
def test_native_test_snap_uses_explicit_self_test_path() -> None:
    """Ctrl+Enter uses the same self-safe test service as the frontend button."""
    from virelo.app.window import MainWindow

    guard = CaptureGuard()
    service = SimpleNamespace(
        test_snap=MagicMock(
            return_value={
                "ok": True,
                "message": "Snap test applied to the last eligible window.",
            }
        )
    )
    bridge = SimpleNamespace(snap_status=SimpleNamespace(emit=MagicMock()))
    window = SimpleNamespace(_capture_guard=guard, _snap_service=service, _bridge=bridge)

    MainWindow._test_snap(window)

    service.test_snap.assert_called_once_with()
    bridge.snap_status.emit.assert_called_once_with(
        "Snap test applied to the last eligible window.", 2000
    )
