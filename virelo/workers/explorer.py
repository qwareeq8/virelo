"""Explorer column auto-size engine and worker.

The module contains the tab-aware ``ExplorerAutosizeEngine``, per-tab
``TabAutosizeState``, and background ``ExplorerAutosizeWorker`` QObject.

Under COM threading constraint D-07, ``ExplorerAutosizeWorker.run()`` must keep
COM initialization, Shell.Application caching, tab iteration, and COM-dependent
closures in this file. COM initialization and usage must remain on one thread.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from virelo.platform.paths import canonicalize_path, resolve_explorer_location

LOG = logging.getLogger("Virelo")

# Rate-limiting constants.
MIN_AUTOSIZE_INTERVAL_PER_TAB_MS = 200  # Minimum milliseconds between per-tab attempts.
GLOBAL_AUTOSIZE_RATE_LIMIT_PER_SEC = 10  # Maximum global attempts per second.
SETTLE_DELAY_MS = 150  # A path must remain stable for this duration.
DEBOUNCE_DELAY_MS = 50  # This is the initial delay after navigation.

# Retry constants.
MAX_CONSECUTIVE_FAILURES = 5
BACKOFF_BASE_MS = 200  # This is the initial backoff duration.
BACKOFF_MAX_MS = 3000  # This is the maximum backoff duration.

# Deduplication lifetime.
DEDUPE_TTL_SECONDS = 300  # Entries remain valid for five minutes.


@dataclass(frozen=True)
class DedupeKey:
    """Key for deduplication: (HWND, tab index, path, view mode)."""

    hwnd: int
    tab_id: int
    path: str
    view_mode: int | None


@dataclass
class DedupeEntry:
    """Entry in deduplication cache with TTL."""

    key: DedupeKey
    timestamp: float


@dataclass
class TabAutosizeState:
    """Track navigation, timing, and retry state for one Explorer tab.

    The consecutive-failure count provides the bounded retry circuit.
    """

    tab_id: int
    target_index: int
    hwnd: int
    path: str = ""
    view_mode: int | None = None
    # Timing state.
    path_stable_since: float = 0.0  # This records when the path became stable.
    last_autosize_attempt: float = 0.0

    # Retry state.
    pending_retry: bool = False
    retry_attempt: int = 0
    next_retry_at: float = 0.0

    # Circuit-breaker state.
    consecutive_failures: int = 0


def _resolve_explorer_path(window) -> str:
    """Return the best normalized location string from an Explorer COM window."""
    return resolve_explorer_location(window).strip()


class _ComIdentityRegistry:
    """Assign stable numeric tokens to worker-owned COM identities."""

    def __init__(self) -> None:
        self._next_token = 1
        self._identities: dict[int, object] = {}

    def resolve(self, identity: object) -> int:
        """Return the existing token for an equal IUnknown identity."""
        for token, known in self._identities.items():
            try:
                if identity == known:
                    return token
            except Exception:
                continue
        token = self._next_token
        self._next_token += 1
        self._identities[token] = identity
        return token

    def retain(self, live_tokens: set[int]) -> None:
        """Release COM references for tabs absent from a complete poll."""
        self._identities = {
            token: identity for token, identity in self._identities.items() if token in live_tokens
        }

    def clear(self) -> None:
        """Release every retained COM identity before COM uninitializes."""
        self._identities.clear()


class ExplorerAutosizeEngine:
    """Autosize Explorer columns after tab navigation settles.

    Windows 11 tabs are keyed by COM identity rather than HWND alone. The
    engine debounces navigation, applies per-tab and global rate limits, uses a
    bounded retry budget with exponential backoff, and deduplicates successful
    work by tab, path, and view mode.

    The worker thread owns the single-threaded COM apartment. This engine does
    not initialize or uninitialize COM and invokes autosize callbacks with the
    caller-owned COM contract.
    """

    # The default retry schedule uses 50, 100, 250, 500, and 1,000 milliseconds.
    DEFAULT_SCHEDULE = (0.05, 0.1, 0.25, 0.5, 1.0)

    def __init__(
        self,
        iter_tabs: Callable[[], list],
        autosize_try: Callable[[int, int, str | None], tuple[bool, str, bool]],
        autosize_full: Callable[[int, int, str | None], tuple[bool, str, bool]],
        is_window_interactive: Callable[[int], bool],
        schedule: tuple[float, ...] | None = None,
    ):
        """Initialize the tab-aware autosize engine.

        Args:
            iter_tabs: Return ``(hwnd, tab_id, path, view_mode)`` tab tuples.
            autosize_try: Run a quick attempt and return success, method, and transience.
            autosize_full: Run a full attempt and return success, method, and transience.
            is_window_interactive: Report whether a window is visible and ready.
            schedule: Retry delays in seconds.
        """
        self._iter_tabs = iter_tabs
        self._autosize_try = autosize_try
        self._autosize_full = autosize_full
        self._is_window_interactive = is_window_interactive
        self._schedule = schedule if schedule else self.DEFAULT_SCHEDULE

        # Per-tab state maps an HWND and worker COM identity to its state.
        self.tab_state: dict[tuple[int, int], TabAutosizeState] = {}

        # The deduplication cache expires successful work after its lifetime.
        self._dedupe_cache: dict[DedupeKey, DedupeEntry] = {}

        # Track recent timestamps for global rate limiting.
        self._global_autosize_times: list[float] = []

        # Idle backoff: poll fast only while the Explorer window set is
        # actually changing; a resident tray app must not enumerate COM
        # windows 6+ times per second around the clock.
        self._last_activity = 0.0
        self._prev_live_keys: set[tuple[int, int]] = set()

    def _is_dedupe_valid(self, key: DedupeKey, now: float) -> bool:
        """Check if a deduplication entry is still valid (within TTL)."""
        entry = self._dedupe_cache.get(key)
        if entry is None:
            return False
        if now - entry.timestamp > DEDUPE_TTL_SECONDS:
            # TTL expired
            del self._dedupe_cache[key]
            return False
        return True

    def _record_dedupe(self, key: DedupeKey, now: float) -> None:
        """Record a deduplication entry."""
        self._dedupe_cache[key] = DedupeEntry(key=key, timestamp=now)

    def _clear_dedupe_for_tab(self, hwnd: int, tab_id: int) -> None:
        """Forget successful work when navigation or view mode changes."""
        stale = [key for key in self._dedupe_cache if key.hwnd == hwnd and key.tab_id == tab_id]
        for key in stale:
            del self._dedupe_cache[key]

    @staticmethod
    def _arm_state(state: TabAutosizeState, now: float) -> None:
        """Schedule a fresh debounced attempt for a changed tab."""
        state.path_stable_since = now
        state.pending_retry = True
        state.retry_attempt = 0
        state.next_retry_at = now + DEBOUNCE_DELAY_MS / 1000.0
        state.consecutive_failures = 0

    def _clean_dedupe_cache(self, now: float) -> None:
        """Remove expired entries from deduplication cache."""
        expired = [
            k for k, v in self._dedupe_cache.items() if now - v.timestamp > DEDUPE_TTL_SECONDS
        ]
        for k in expired:
            del self._dedupe_cache[k]

    def _check_global_rate_limit(self, now: float) -> bool:
        """Check if global rate limit allows an autosize attempt."""
        # Clean old entries
        cutoff = now - 1.0
        self._global_autosize_times = [t for t in self._global_autosize_times if t > cutoff]
        return len(self._global_autosize_times) < GLOBAL_AUTOSIZE_RATE_LIMIT_PER_SEC

    def _record_global_autosize(self, now: float) -> None:
        """Record a global autosize attempt."""
        self._global_autosize_times.append(now)

    def _calculate_backoff(self, failures: int) -> float:
        """Calculate exponential backoff time in seconds."""
        if failures <= 0:
            return 0
        backoff_ms = min(BACKOFF_BASE_MS * (2 ** (failures - 1)), BACKOFF_MAX_MS)
        return backoff_ms / 1000.0

    def step(self, now: float) -> float:
        """Process one step of the tab-aware autosize engine.

        Args:
            now: Current ``time.time()`` timestamp.

        Returns:
            Recommended delay before the next step, in seconds.
        """
        log = LOG

        # Periodically clean dedupe cache
        self._clean_dedupe_cache(now)

        try:
            tabs = list(self._iter_tabs() or [])
        except Exception as e:
            log.warning("Explorer tab enumeration failed: %s.", e)
            tabs = []

        if tabs:
            log.debug("Explorer tab enumeration found %d tabs.", len(tabs))

        # Track live tabs by window and stable ShellWindows collection identity
        # so duplicate tabs open to the same folder remain independent.
        live_tab_keys = set()

        for tab_info in tabs:
            # Unpack tab info: (hwnd, tab_id, target_index, path, view_mode).
            if len(tab_info) >= 5:
                hwnd, tab_id, target_index, raw_path, view_mode = tab_info[:5]
            elif len(tab_info) >= 4:
                hwnd, tab_id, raw_path, view_mode = tab_info[:4]
                target_index = tab_id
            elif len(tab_info) >= 3:
                hwnd, tab_id, raw_path = tab_info[:3]
                target_index = tab_id
                view_mode = None
            elif len(tab_info) >= 2:
                # Legacy format: (hwnd, path)
                hwnd, raw_path = tab_info[:2]
                tab_id = hash((hwnd, str(raw_path)))
                target_index = tab_id
                view_mode = None
            else:
                continue

            raw_path = "" if raw_path is None else str(raw_path)
            canonical_path = canonicalize_path(raw_path)

            try:
                tab_id = int(tab_id)
            except (TypeError, ValueError):
                tab_id = hash(tab_id)
            tab_key = (hwnd, tab_id)
            live_tab_keys.add(tab_key)

            # Get or create tab state using the stable key.
            state = self.tab_state.get(tab_key)
            is_new_entry = state is None

            if is_new_entry:
                # Create state for a newly observed tab identity.
                state = TabAutosizeState(
                    tab_id=tab_id,
                    target_index=int(target_index),
                    hwnd=hwnd,
                    path=canonical_path,
                    view_mode=view_mode,
                    path_stable_since=now,
                )
                self.tab_state[tab_key] = state
                log.debug(
                    "Explorer autosizing found a new tab: hwnd=%s; tab=%s; path=%r.",
                    hwnd,
                    tab_id,
                    canonical_path,
                )

                # Schedule debounced autosize
                debounce_delay = DEBOUNCE_DELAY_MS / 1000.0
                state.next_retry_at = now + debounce_delay
                state.pending_retry = True

                log.debug(
                    "Explorer autosizing scheduled a debounced attempt in %.3f seconds "
                    "for hwnd=%s and path=%r.",
                    debounce_delay,
                    hwnd,
                    canonical_path,
                )
                continue  # Don't attempt autosize this iteration

            previous_target_index = state.target_index
            state.target_index = int(target_index)
            if (
                state.target_index != previous_target_index
                and not state.pending_retry
                and state.consecutive_failures > 0
            ):
                # The ShellWindows collection can reorder after another tab
                # closes. A previously exhausted positional lookup may become
                # resolvable at the new index even though path/view are stable.
                self._arm_state(state, now)
            if canonical_path != state.path:
                log.debug(
                    "Explorer navigation changed hwnd=%s and tab=%s from %r to %r.",
                    hwnd,
                    tab_id,
                    state.path,
                    canonical_path,
                )
                self._clear_dedupe_for_tab(hwnd, tab_id)
                state.path = canonical_path
                state.view_mode = view_mode
                self._arm_state(state, now)
                continue

            # Update view_mode if changed (might affect deduplication)
            if view_mode != state.view_mode:
                log.debug(
                    "Explorer view mode changed for hwnd=%s and path=%r from %s to %s.",
                    hwnd,
                    canonical_path,
                    state.view_mode,
                    view_mode,
                )
                state.view_mode = view_mode
                if view_mode == 4:
                    self._clear_dedupe_for_tab(hwnd, tab_id)
                    self._arm_state(state, now)
                elif view_mode is not None:
                    state.pending_retry = False

            # Check if we should attempt autosize for this entry
            if not state.pending_retry:
                continue

            # Check if debounce/retry timer has elapsed
            if now < state.next_retry_at:
                continue

            # Check settle requirement: path must be stable for SETTLE_DELAY_MS
            settle_required = SETTLE_DELAY_MS / 1000.0
            if now - state.path_stable_since < settle_required:
                log.debug(
                    "Explorer autosizing is waiting for hwnd=%s and path=%r to settle.",
                    hwnd,
                    canonical_path,
                )
                state.next_retry_at = state.path_stable_since + settle_required
                continue

            # Check per-tab rate limit
            per_tab_interval = MIN_AUTOSIZE_INTERVAL_PER_TAB_MS / 1000.0
            if now - state.last_autosize_attempt < per_tab_interval:
                log.debug(
                    "Explorer autosizing is rate-limited for hwnd=%s and path=%r.",
                    hwnd,
                    canonical_path,
                )
                state.next_retry_at = state.last_autosize_attempt + per_tab_interval
                continue

            # Check global rate limit
            if not self._check_global_rate_limit(now):
                log.debug("Explorer autosizing reached the global rate limit.")
                state.next_retry_at = now + 0.1
                continue

            # Check deduplication using (hwnd, path, view_mode)
            dedupe_key = DedupeKey(
                hwnd=hwnd,
                tab_id=tab_id,
                path=canonical_path,
                view_mode=view_mode,
            )
            if self._is_dedupe_valid(dedupe_key, now):
                log.debug(
                    "Explorer autosizing found a successful deduplication entry for "
                    "hwnd=%s, path=%r, and view=%s.",
                    hwnd,
                    canonical_path,
                    view_mode,
                )
                state.pending_retry = False
                continue

            # Check if window is interactive
            if not self._is_window_interactive(hwnd):
                log.debug("Explorer autosizing skipped noninteractive hwnd=%s.", hwnd)
                state.next_retry_at = now + 0.5
                continue

            # Attempt autosize
            log.debug(
                "Explorer autosizing is attempting hwnd=%s and path=%r; attempt=%d.",
                hwnd,
                canonical_path,
                state.retry_attempt,
            )

            state.last_autosize_attempt = now
            self._record_global_autosize(now)

            ok = False
            method = "none"
            is_transient = False

            try:
                # Use quick autosize for first few attempts, then full
                # Pass path so the autosize function can find the correct tab
                if state.retry_attempt <= 2:
                    result = self._autosize_try(hwnd, state.target_index, canonical_path)
                else:
                    result = self._autosize_full(hwnd, state.target_index, canonical_path)

                if isinstance(result, tuple):
                    if len(result) >= 3:
                        ok, method, is_transient = result[:3]
                    elif len(result) >= 2:
                        ok, method = result[:2]
                        is_transient = False
                    else:
                        ok = bool(result[0])
                        method = "unknown" if ok else "none"
                        is_transient = False
                else:
                    ok = bool(result)
                    method = "unknown" if ok else "none"
                    is_transient = False

                log.debug(
                    "Explorer autosizing completed an attempt: ok=%s; method=%s; "
                    "transient=%s; hwnd=%s.",
                    ok,
                    method,
                    is_transient,
                    hwnd,
                )
            except Exception as e:
                ok = False
                method = "error"
                is_transient = True  # Assume exceptions are transient
                log.warning("Explorer autosizing raised an exception for hwnd=%s: %s.", hwnd, e)

            if ok:
                # Success!
                state.pending_retry = False
                state.consecutive_failures = 0
                self._record_dedupe(dedupe_key, now)

                log.debug(
                    "Explorer autosizing succeeded for hwnd=%s and path=%r with method=%s.",
                    hwnd,
                    canonical_path,
                    method,
                )
            else:
                # Failure
                state.retry_attempt += 1

                if is_transient:
                    # Transient error - schedule retry with backoff
                    state.consecutive_failures += 1
                    backoff = self._calculate_backoff(state.consecutive_failures)

                    if state.retry_attempt < len(self._schedule):
                        retry_delay = max(self._schedule[state.retry_attempt], backoff)
                        state.next_retry_at = now + retry_delay
                        log.debug(
                            "Explorer autosizing had a transient failure; retrying in %.3f "
                            "seconds for hwnd=%s.",
                            retry_delay,
                            hwnd,
                        )
                    else:
                        if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            state.pending_retry = False
                            log.debug(
                                "Explorer autosizing exhausted the retry budget for hwnd=%s.",
                                hwnd,
                            )
                        else:
                            state.pending_retry = False
                            log.warning(
                                "Explorer autosizing exhausted retries for hwnd=%s and path=%r.",
                                hwnd,
                                canonical_path,
                            )
                else:
                    # Non-transient error (e.g., not in Details view) - don't retry
                    state.pending_retry = False
                    log.debug(
                        "Explorer autosizing had a non-transient failure; hwnd=%s will not retry.",
                        hwnd,
                    )

        # Clean up tab identities that no longer exist.
        closed_entries = [key for key in self.tab_state if key not in live_tab_keys]
        for key in closed_entries:
            del self.tab_state[key]
            log.debug("Explorer autosizing removed closed tab entry %s.", key)

        # Record activity whenever the set of open tab identities changes.
        # Startup counts as activity so a freshly enabled worker responds quickly.
        if self._last_activity == 0.0 or live_tab_keys != self._prev_live_keys:
            self._last_activity = now
            self._prev_live_keys = set(live_tab_keys)

        return self._next_delay(now)

    def _next_delay(self, now: float) -> float:
        """Calculate the delay until the next step should run."""
        # Check if any tabs have pending work
        pending_tabs = [s for s in self.tab_state.values() if s.pending_retry]

        if not pending_tabs:
            # No pending work: decay the poll rate with inactivity. The cost
            # of a poll is a full cross-process COM enumeration, so idle
            # cadence matters more than first-detection latency.
            idle = now - self._last_activity
            if idle < 5.0:
                return 0.15
            if idle < 30.0:
                return 0.5
            return 1.0

        # Find the soonest pending retry
        next_due = min(s.next_retry_at for s in pending_tabs)
        delay = next_due - now

        # Clamp to reasonable bounds
        return max(0.005, min(1.0, delay))


# Import PySide6 conditionally for CI compatibility under D-10.
try:
    from PySide6 import QtCore
except ImportError:  # pragma: no cover - PySide6 is unavailable in some test environments.
    QtCore = None


if QtCore is not None:

    class ExplorerAutosizeWorker(QtCore.QObject):
        """
        Background worker for Explorer column auto-sizing.

        Runs in a separate thread and monitors Explorer windows/tabs for navigation,
        auto-sizing columns on the first visit to each path.

        Windows 11 tab support:
        - Tracks tabs by COM identity (tab_id), not just HWND
        - Properly handles multiple tabs in a single window
        - Includes debounce, settle detection, rate limiting, and circuit breakers
        """

        finished = QtCore.Signal()

        # Default retry schedule: debounce, then 100ms, 250ms, 500ms, 1s
        DEFAULT_SCHEDULE = (0.05, 0.1, 0.25, 0.5, 1.0)

        def __init__(
            self,
            autosize_try: Callable[[int], tuple[bool, str]],
            autosize_full: Callable[[int], tuple[bool, str]],
            is_window_interactive: Callable[[int], bool],
            schedule: tuple[float, ...] | None = None,
        ):
            """
            Initialize the autosize worker.

            Args:
                autosize_try: Quick autosize attempt, returns
                    (success, method) or (success, method, is_transient)
                autosize_full: Full autosize with all fallbacks,
                    returns (success, method) or
                    (success, method, is_transient)
                is_window_interactive: Check if window is visible
                schedule: Retry schedule as tuple of delays in seconds
            """
            super().__init__()
            self._autosize_try_legacy = autosize_try
            self._autosize_full_legacy = autosize_full
            self._is_window_interactive = is_window_interactive
            self._schedule = schedule if schedule else self.DEFAULT_SCHEDULE
            self._stop = threading.Event()
            # Win32 event mirrored with _stop so the worker's message wait can
            # wake immediately on stop instead of polling a Python flag.
            try:
                import win32event

                self._stop_win32_event = win32event.CreateEvent(None, True, False, None)
            except Exception:  # pragma: no cover - pywin32 absent off-Windows
                self._stop_win32_event = None

        def stop(self):
            """Signal the worker to stop."""
            self._stop.set()
            if self._stop_win32_event is not None:
                try:
                    import win32event

                    win32event.SetEvent(self._stop_win32_event)
                except Exception:
                    pass

        @QtCore.Slot()
        def run(self):
            """Run the worker and always notify its lifecycle manager."""
            try:
                self._run_impl()
            except Exception:
                LOG.exception("Explorer autosize worker terminated unexpectedly.")
            finally:
                # An import or setup failure happens before _run_impl's COM
                # cleanup block. Close any resources it managed to create and
                # make sure QThread.quit is invoked through the finished signal.
                if getattr(self, "_worker_com_initialized", False):
                    try:
                        import pythoncom

                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
                    self._worker_com_initialized = False
                stop_handle = self._stop_win32_event
                self._stop_win32_event = None
                if stop_handle is not None:
                    try:
                        stop_handle.Close()
                    except Exception:
                        pass
                self.finished.emit()

        def _run_impl(self):
            """
            Main worker loop with proper COM lifecycle management.

            COM Threading Model:
            - Initializes COM ONCE for this thread (STA apartment)
            - Caches Shell.Application to avoid repeated creation/destruction
            - Pumps COM messages to prevent RPC disconnection errors
            - Uninitializes COM only at shutdown after releasing all objects
            """
            import logging

            import pythoncom
            import pywintypes
            import win32com.client
            import win32con
            import win32event
            import win32gui

            log = logging.getLogger("Virelo")
            log.info("Explorer autosize worker: initializing one STA COM apartment.")

            # COM is initialized ONCE for this worker thread (STA)
            try:
                pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            except Exception:
                # Fallback if CoInitializeEx is unavailable
                pythoncom.CoInitialize()
            self._worker_com_initialized = True
            log.info("Explorer autosize worker: the STA COM apartment is initialized.")

            # Cache Shell.Application to avoid creating/destroying it every poll
            # cycle (avoids RPC errors 0x80010108, 0x800706b5). A creation
            # failure is retried with a cooldown instead of disabling the
            # feature for the process lifetime.
            shell_state = {"app": None, "retry_at": 0.0}
            identity_registry = _ComIdentityRegistry()

            def ensure_shell_app():
                if shell_state["app"] is not None:
                    return shell_state["app"]
                if time.time() < shell_state["retry_at"]:
                    return None
                try:
                    shell_state["app"] = win32com.client.Dispatch("Shell.Application")
                    log.debug("Explorer autosize worker: Shell.Application is cached.")
                except Exception as e:
                    shell_state["retry_at"] = time.time() + 30.0
                    log.warning(
                        "Explorer autosize worker: Shell.Application creation failed; "
                        "retrying in 30 seconds: %s.",
                        e,
                    )
                return shell_state["app"]

            ensure_shell_app()

            try:

                def _get_view_mode(w) -> int | None:
                    """Get view mode safely, returning None if not available."""
                    try:
                        doc = getattr(w, "Document", None)
                        if doc is None:
                            return None
                        return int(getattr(doc, "CurrentViewMode"))
                    except (pywintypes.com_error, OSError, AttributeError, Exception):
                        return None

                def iter_tabs():
                    """
                    Enumerate all Explorer tabs using the cached Shell.Application.

                    Returns: List of
                    (hwnd, stable_tab_id, target_index, path, view_mode) tuples.

                    stable_tab_id comes from COM's canonical IUnknown identity,
                    while target_index is the current per-window collection index
                    used to address that tab in a separate COM enumeration.

                    IMPORTANT: This function checks the stop flag aggressively before
                    every COM call to avoid RPC failures during shutdown.
                    """

                    # Helper to check stop flag - must be checked before EVERY COM call
                    def stopping():
                        return self._stop.is_set()

                    shell_app = None if stopping() else ensure_shell_app()
                    # Exit early if we are stopping to avoid COM calls during teardown
                    if stopping() or shell_app is None:
                        return []

                    out = []
                    windows = None
                    window_list = []

                    # Use cached shell_app instead of creating new instance
                    try:
                        if stopping():
                            return []
                        windows = shell_app.Windows()
                        if windows is None:
                            return out

                        # Get count with stop check
                        if stopping():
                            return []
                        try:
                            count = windows.Count
                        except (
                            pywintypes.com_error,
                            pythoncom.com_error,
                            OSError,
                            Exception,
                        ) as e:
                            log.debug(
                                "Explorer tab enumeration could not read the window count: %s.", e
                            )
                            shell_state["app"] = None
                            shell_state["retry_at"] = time.time() + 1.0
                            return out

                        # Enumerate windows with stop check before each Item() call
                        item_failures = 0
                        for i in range(count):
                            if stopping():
                                log.debug("Explorer tab enumeration is stopping.")
                                return out
                            try:
                                w = windows.Item(i)
                                if w is not None:
                                    window_list.append(w)
                            except (
                                pywintypes.com_error,
                                pythoncom.com_error,
                                OSError,
                                Exception,
                            ):
                                item_failures += 1
                                continue

                        if count and item_failures == count:
                            # A disconnected cached Shell.Application proxy can
                            # expose Count successfully while every Item call
                            # fails. Recreate it on the next poll.
                            shell_state["app"] = None
                            shell_state["retry_at"] = time.time() + 1.0
                            return out

                        log.debug(
                            "Shell.Application returned %d windows.",
                            len(window_list),
                        )
                    except (
                        pywintypes.com_error,
                        pythoncom.com_error,
                        OSError,
                        Exception,
                    ) as e:
                        log.debug("Reading Shell.Application windows failed: %s.", e)
                        # The cached proxy is likely disconnected (Explorer was
                        # restarted). Drop it so ensure_shell_app recreates it
                        # on the next poll instead of reusing a dead proxy.
                        shell_state["app"] = None
                        shell_state["retry_at"] = time.time() + 1.0
                        return out

                    tab_indices: dict[int, int] = {}
                    live_identity_tokens: set[int] = set()
                    poll_complete = item_failures == 0
                    for w in window_list:
                        # Check stop before processing each window
                        if stopping():
                            log.debug("Explorer tab enumeration is stopping during processing.")
                            break

                        try:
                            if stopping():
                                break
                            try:
                                hwnd = int(w.HWND or 0)
                            except (
                                pywintypes.com_error,
                                pythoncom.com_error,
                                OSError,
                                AttributeError,
                                Exception,
                            ):
                                continue

                            if not hwnd:
                                continue

                            # Filter to real Explorer windows by window class.
                            # Cheaper than the Name property (no cross-process
                            # COM call) and immune to lookalikes such as
                            # Internet Explorer.
                            try:
                                if win32gui.GetClassName(hwnd) not in (
                                    "CabinetWClass",
                                    "ExploreWClass",
                                ):
                                    continue
                            except Exception:
                                continue

                            if stopping():
                                break
                            try:
                                path = _resolve_explorer_path(w)
                            except (
                                pywintypes.com_error,
                                pythoncom.com_error,
                                OSError,
                                Exception,
                            ):
                                path = ""

                            if stopping():
                                break

                            # The per-window index addresses the current tab,
                            # but is not a stable identity because an Explorer
                            # tab can be closed and replaced at the same index.
                            target_index = tab_indices.get(hwnd, 0)
                            tab_indices[hwnd] = target_index + 1
                            try:
                                identity = w._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
                            except Exception:
                                # PyIDispatch itself normally compares by COM
                                # identity. Keep it alive in the registry as a
                                # best-effort fallback if QueryInterface is not
                                # exposed by a generated wrapper.
                                identity = getattr(w, "_oleobj_", w)
                            tab_id = identity_registry.resolve(identity)
                            live_identity_tokens.add(tab_id)
                            view_mode = _get_view_mode(w)

                            # Do not return the COM dispatch object because that can trigger
                            # garbage-collection-time COM releases.
                            out.append((hwnd, tab_id, target_index, path, view_mode))
                            log.debug(
                                "Explorer tab enumeration found hwnd=%s, tab_id=%s, path=%r, "
                                "and view=%s.",
                                hwnd,
                                tab_id,
                                path,
                                view_mode,
                            )
                        except (
                            pywintypes.com_error,
                            pythoncom.com_error,
                            OSError,
                            Exception,
                        ) as e:
                            log.debug("Processing an Explorer window failed: %s.", e)
                            poll_complete = False
                            continue

                    # Proactively drop COM references before returning
                    window_list.clear()
                    windows = None
                    # Only a complete poll can prove that a retained COM
                    # identity disappeared. Partial polls keep old references
                    # so a transient COM failure does not manufacture a new
                    # tab identity on the next cycle.
                    if poll_complete and not stopping():
                        identity_registry.retain(live_identity_tokens)
                    # The cached Shell.Application stays owned by the worker thread.

                    return out

                def autosize_try_wrapper(
                    hwnd: int, target_index: int, target_path: str | None
                ) -> tuple[bool, str, bool]:
                    """Wrapper: calls legacy autosize with path, adds transient detection."""
                    if self._stop.is_set():
                        return (False, "stopped", False)
                    try:
                        # The worker owns COM initialization and teardown.
                        result = self._autosize_try_legacy(
                            hwnd,
                            target_path=target_path,
                            target_index=target_index,
                            caller_owns_com=True,
                        )
                        if isinstance(result, tuple) and len(result) >= 2:
                            ok, method = result[:2]
                            # "not-details" is permanent until the user changes
                            # the view; retrying it five times per navigation
                            # is pure COM churn.
                            is_transient = not ok and method in (
                                "none",
                                "error",
                                "not-found",
                                "partial",
                            )
                            return (ok, method, is_transient)
                        return (bool(result), "unknown" if result else "none", True)
                    except Exception as e:
                        log.debug(
                            "The quick autosize callback failed for hwnd=%s and path=%s: %s.",
                            hwnd,
                            target_path,
                            e,
                        )
                        return (False, "error", True)  # Exceptions are transient

                def autosize_full_wrapper(
                    hwnd: int, target_index: int, target_path: str | None
                ) -> tuple[bool, str, bool]:
                    """Wrapper: calls legacy autosize with path, adds transient detection."""
                    if self._stop.is_set():
                        return (False, "stopped", False)
                    try:
                        # The worker owns COM initialization and teardown.
                        result = self._autosize_full_legacy(
                            hwnd,
                            target_path=target_path,
                            target_index=target_index,
                            caller_owns_com=True,
                        )
                        if isinstance(result, tuple) and len(result) >= 2:
                            ok, method = result[:2]
                            is_transient = not ok and method in (
                                "none",
                                "error",
                                "not-found",
                                "partial",
                            )
                            return (ok, method, is_transient)
                        return (bool(result), "unknown" if result else "none", True)
                    except Exception as e:
                        log.debug(
                            "The full autosize callback failed for hwnd=%s and path=%s: %s.",
                            hwnd,
                            target_path,
                            e,
                        )
                        return (False, "error", True)

                log.info("Explorer autosize worker: started with schedule=%s.", self._schedule)
                engine = ExplorerAutosizeEngine(
                    iter_tabs,
                    autosize_try_wrapper,
                    autosize_full_wrapper,
                    self._is_window_interactive,
                    schedule=self._schedule,
                )
                log.debug("Explorer autosize worker: the engine is entering its main loop.")
                loop_count = 0

                while not self._stop.is_set():
                    # Double-check stop flag before any COM work
                    if self._stop.is_set():
                        break
                    try:
                        now = time.time()
                        sleep_for = engine.step(now)
                        loop_count += 1

                        # Log metrics periodically
                        if loop_count <= 5 or loop_count % 50 == 0:
                            log.debug(
                                "Explorer autosize: loop=%d tabs=%d pending=%d "
                                "cache=%d sleep=%.3fs",
                                loop_count,
                                len(engine.tab_state),
                                len([s for s in engine.tab_state.values() if s.pending_retry]),
                                len(engine._dedupe_cache),
                                sleep_for,
                            )
                    except Exception as exc:
                        log.exception(
                            "Explorer autosize worker: an engine step failed.", exc_info=exc
                        )
                        sleep_for = 0.2

                    # Pump COM messages to keep STA apartment responsive
                    # This prevents RPC_E_DISCONNECTED and other STA threading issues
                    try:
                        if pythoncom.PumpWaitingMessages():
                            # WM_QUIT received
                            break
                    except Exception:
                        pass

                    # Sleep without spinning: MsgWaitForMultipleObjects wakes
                    # only for the stop event, an incoming window message
                    # (pumped for the STA), or the timeout. The old loop woke
                    # 200 times per second around the clock.
                    deadline = time.time() + sleep_for
                    while not self._stop.is_set():
                        remaining_ms = int((deadline - time.time()) * 1000)
                        if remaining_ms <= 0:
                            break
                        if self._stop_win32_event is None:
                            time.sleep(min(0.05, remaining_ms / 1000.0))
                            continue
                        rc = win32event.MsgWaitForMultipleObjects(
                            [self._stop_win32_event],
                            False,
                            remaining_ms,
                            win32con.QS_ALLINPUT,
                        )
                        if rc == win32event.WAIT_OBJECT_0:
                            break  # Stop requested.
                        if rc == win32event.WAIT_TIMEOUT:
                            break  # Slept the full delay.
                        # rc == WAIT_OBJECT_0 + 1: window messages are pending.
                        try:
                            if pythoncom.PumpWaitingMessages():
                                self._stop.set()  # WM_QUIT
                                break
                        except Exception:
                            pass
            finally:
                # Release every COM object before uninitializing COM to prevent crashes
                # from lingering references.
                identity_registry.clear()
                shell_state["app"] = None
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
                self._worker_com_initialized = False
                stop_handle = self._stop_win32_event
                self._stop_win32_event = None
                if stop_handle is not None:
                    try:
                        stop_handle.Close()
                    except Exception:
                        pass
                log.info(
                    "Explorer autosize worker: exiting after %d loops.",
                    loop_count if "loop_count" in dir() else 0,
                )
