import threading


class CaptureGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = False

    def try_start(self) -> bool:
        with self._lock:
            if self._active:
                return False
            self._active = True
            return True

    def finish(self) -> None:
        with self._lock:
            self._active = False
