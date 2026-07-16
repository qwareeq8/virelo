"""Key capture session and worker.

KeyCaptureSession is pure Python (no PySide6 dependency).
KeyCaptureWorker wraps it in a QObject for use on a QThread.
"""

import logging
import threading
import time

LOG = logging.getLogger("Virelo")


class KeyCaptureSession:
    def __init__(self, keyboard, cancel_key="esc", timeout_s=15.0, poll_interval=0.01):
        self._keyboard = keyboard
        self._cancel_key = cancel_key
        self._timeout_s = timeout_s
        self._poll_interval = poll_interval
        self._done = threading.Event()
        self._stop = threading.Event()
        self._result = None
        self._reason = None

    def stop(self):
        if self._reason is None:
            self._reason = "stopped"
        self._stop.set()
        self._done.set()

    def run(self):
        self._result = None
        self._reason = None
        self._done.clear()
        self._stop.clear()
        hook_id = None
        start = time.monotonic()
        try:
            hook_id = self._keyboard.hook(self._on_event)
            while not self._done.is_set():
                if self._stop.is_set():
                    if self._reason is None:
                        self._reason = "stopped"
                    break
                if self._timeout_s is not None and time.monotonic() - start >= self._timeout_s:
                    self._reason = "timeout"
                    break
                self._done.wait(self._poll_interval)
        except Exception:
            LOG.exception("Key capture hook failed")
            self._reason = "error"
        finally:
            if hook_id is not None:
                try:
                    self._keyboard.unhook(hook_id)
                except Exception:
                    pass
        if self._reason is None:
            self._reason = "captured" if self._result else "stopped"
        return self._result, self._reason

    def _on_event(self, event):
        if self._done.is_set():
            return
        event_type = getattr(event, "event_type", "") or ""
        if event_type and event_type != "down":
            return
        name = getattr(event, "name", "") or ""
        key = str(name).lower()
        if not key:
            return
        if key == self._cancel_key:
            self._reason = "esc"
            self._done.set()
            return
        self._result = key
        self._reason = "captured"
        self._done.set()


# Conditional PySide6 import for CI compatibility (D-10)
try:
    from PySide6 import QtCore
except Exception:  # pragma: no cover - PySide6 unavailable in some test envs
    QtCore = None


if QtCore is not None:

    class KeyCaptureWorker(QtCore.QObject):
        captured = QtCore.Signal(str)
        cancelled = QtCore.Signal(str)
        finished = QtCore.Signal()

        def __init__(self, keyboard_module=None, cancel_key="esc", timeout_s=15.0):
            super().__init__()
            if keyboard_module is None:
                import keyboard as keyboard_module
            self._session = KeyCaptureSession(
                keyboard_module,
                cancel_key=cancel_key,
                timeout_s=timeout_s,
            )

        @QtCore.Slot()
        def run(self):
            # finished must ALWAYS emit or the CaptureGuard stays locked and
            # the capture QThread never quits.
            try:
                key, reason = self._session.run()
                if key:
                    self.captured.emit(key)
                else:
                    self.cancelled.emit(reason)
            except Exception:
                LOG.exception("Key capture session crashed")
                self.cancelled.emit("error")
            finally:
                self.finished.emit()

        def stop(self):
            self._session.stop()
