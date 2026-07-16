"""Explorer column auto-size service.

Manages the ExplorerAutosizeWorker lifecycle. Start/stop gated by the
ex_auto_size setting. COM operations remain in workers/explorer.py
per Phase 3 D-07 constraint.
"""

import logging
import time

from PySide6 import QtCore, QtGui, QtWidgets

from virelo.platform.win32_helpers import _is_window_interactive
from virelo.services.explorer_columns import autosize_explorer_columns
from virelo.workers.explorer import ExplorerAutosizeWorker

LOG = logging.getLogger("Virelo")


# ------------------------------------------------------------------------------
# Explorer autosize wrappers (pass to ExplorerAutosizeWorker)
# ------------------------------------------------------------------------------


def _autosize_explorer_columns_quick(
    top_hwnd: int, target_path: str = None, caller_owns_com: bool = False
) -> tuple:
    """
    Single autosize attempt using COM-based column manager only.
    Returns (success, method).
    """
    return autosize_explorer_columns(
        top_hwnd,
        allow_keyboard_fallback=False,
        target_path=target_path,
        caller_owns_com=caller_owns_com,
    )


def _autosize_explorer_columns_full(
    top_hwnd: int, target_path: str = None, caller_owns_com: bool = False
) -> tuple:
    """
    Full autosize attempt; currently identical to quick (COM-only, no fallbacks).
    Returns (success, method).
    """
    return autosize_explorer_columns(
        top_hwnd,
        allow_keyboard_fallback=False,
        target_path=target_path,
        caller_owns_com=caller_owns_com,
    )


class ExplorerService:
    """Lifecycle manager for the Explorer column auto-size worker.

    Follows the same facade pattern as SnapService. MainWindow creates it,
    passes settings, and delegates start/stop to it.
    """

    def __init__(self, settings, parent=None):
        """Accept settings and optional QObject parent for thread parenting."""
        self._settings = settings
        self._parent = parent
        self._thread = None
        self._worker = None

    def start(self):
        """Start the explorer worker if ex_auto_size is enabled.

        If the setting is disabled, stops any running worker instead.
        If a worker is already running, this is a no-op.
        """
        LOG.info("ExplorerService.start: called")
        app = QtWidgets.QApplication.instance()
        pushed_cursor = False
        if app is not None:
            QtGui.QGuiApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CursorShape.WaitCursor))
            pushed_cursor = True
        try:
            group_enabled = bool(self._settings.ex_auto_size)
            LOG.info("ExplorerService.start: group_enabled=%s", group_enabled)
            if not group_enabled:
                LOG.info("Explorer autosize: stopping (disabled).")
                self.stop()
                return

            if self._thread and self._thread.isRunning():
                LOG.info("Explorer autosize: worker already running.")
                return

            LOG.setLevel(logging.DEBUG)
            LOG.info("Explorer autosize: enabling DEBUG logging for troubleshooting")

            self._thread = QtCore.QThread(self._parent)
            self._worker = ExplorerAutosizeWorker(
                _autosize_explorer_columns_quick,
                _autosize_explorer_columns_full,
                _is_window_interactive,
                schedule=(0.05, 0.1, 0.25, 0.5, 1.0),
            )
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._thread.quit)
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._thread.deleteLater)
            self._thread.finished.connect(self._on_finished)
            self._thread.start()
            LOG.info(
                "Explorer autosize: worker started with tab-aware engine, "
                "schedule=(0.05, 0.1, 0.25, 0.5, 1.0)"
            )
        finally:
            if pushed_cursor:
                QtGui.QGuiApplication.restoreOverrideCursor()

    def stop(self):
        """Stop the explorer worker cleanly."""
        worker = self._worker
        thread = self._thread
        if worker is not None:
            try:
                worker.stop()
            except Exception:
                pass
            time.sleep(0.05)
        if thread is not None:
            thread.quit()
            if not thread.wait(3000):
                LOG.warning("Explorer autosize: thread did not stop in time")
        self._worker = None
        self._thread = None
        LOG.info("Explorer autosize: worker stopped.")

    def is_running(self) -> bool:
        """Return True if the explorer worker thread is currently running."""
        return self._thread is not None and self._thread.isRunning()

    def _on_finished(self):
        """Internal callback when the worker thread finishes."""
        self._worker = None
        self._thread = None
