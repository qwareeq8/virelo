#!/usr/bin/env python3
"""
Explorer column auto-sizing using COM IColumnManager only (no fallbacks).

This mirrors the standalone explorer_autosize_columns.py logic:
- obtain IColumnManager via IServiceProvider/SID_SFolderView
- set CM_WIDTH_AUTOSIZE for all visible columns.

Windows 11 tab-aware improvements:
- Track tabs by COM IUnknown identity, not just HWND
- Select active tab explicitly using focus detection
- Handle transient COM errors during navigation gracefully
"""

from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Iterable
from ctypes import c_uint, c_void_p, sizeof, wintypes
from dataclasses import dataclass, field

import comtypes
import comtypes.client
from comtypes import COMMETHOD, GUID, HRESULT, POINTER, IUnknown, byref, cast

from virelo.platform.paths import canonicalize_path  # noqa: F401 -- re-exported for consumers

LOG = logging.getLogger("Virelo")

# Transient COM error codes that indicate the view is not ready yet
TRANSIENT_HRESULT_CODES = frozenset(
    [
        0x80004002,  # E_NOINTERFACE
        0x80004005,  # E_FAIL
        0x80070005,  # E_ACCESSDENIED
        0x80070006,  # E_HANDLE (invalid handle)
        0x8001010D,  # RPC_E_SERVER_CANTMARSHAL
        0x8001010E,  # RPC_E_SERVER_CANTUNMARSHAL
        0x80010108,  # RPC_E_DISCONNECTED
        0x800401FD,  # CO_E_OBJNOTCONNECTED
        0x80080005,  # CO_E_SERVER_EXEC_FAILURE
    ]
)


class IServiceProvider(IUnknown):
    _iid_ = GUID("{6D5140C1-7436-11CE-8034-00AA006009FA}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "QueryService",
            (["in"], GUID, "guidService"),
            (["in"], GUID, "riid"),
            (["out"], POINTER(c_void_p), "ppvObject"),
        ),
    ]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [
        ("fmtid", GUID),
        ("pid", wintypes.DWORD),
    ]


class CM_COLUMNINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwMask", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("uWidth", wintypes.UINT),
        ("uDefaultWidth", wintypes.UINT),
        ("uIdealWidth", wintypes.UINT),
        ("wszName", wintypes.WCHAR * 80),
    ]


CM_MASK_WIDTH = 0x00000001
CM_MASK_DEFAULTWIDTH = 0x00000002
CM_MASK_IDEALWIDTH = 0x00000004
CM_MASK_NAME = 0x00000008
CM_MASK_STATE = 0x00000010

CM_ENUM_VISIBLE = 0x00000002

CM_WIDTH_AUTOSIZE = -2

FVM_DETAILS = 4

FOLDERVIEWMODE_NAMES = {
    -1: "FVM_AUTO",
    1: "FVM_ICON",
    2: "FVM_SMALLICON",
    3: "FVM_LIST",
    4: "FVM_DETAILS",
    5: "FVM_THUMBNAIL",
    6: "FVM_TILE",
    7: "FVM_THUMBSTRIP",
    8: "FVM_CONTENT",
}

SID_SFolderView = GUID("{CDE725B0-CCC9-4519-917E-325D72FAB4CE}")


class IColumnManager(IUnknown):
    _iid_ = GUID("{D8EC27BB-3F3B-4042-B10A-4ACFD924D453}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "SetColumnInfo",
            (["in"], POINTER(PROPERTYKEY), "propkey"),
            (["in"], POINTER(CM_COLUMNINFO), "pcmci"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetColumnInfo",
            (["in"], POINTER(PROPERTYKEY), "propkey"),
            (["in", "out"], POINTER(CM_COLUMNINFO), "pcmci"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetColumnCount",
            (["in"], wintypes.DWORD, "dwFlags"),
            (["in"], POINTER(wintypes.UINT), "puCount"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetColumns",
            (["in"], wintypes.DWORD, "dwFlags"),
            (["in"], POINTER(PROPERTYKEY), "rgkeyOrder"),
            (["in"], wintypes.UINT, "cColumns"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "SetColumns",
            (["in"], POINTER(PROPERTYKEY), "rgkeyOrder"),
            (["in"], wintypes.UINT, "cVisible"),
        ),
    ]


def _get_com_identity(dispatch: object) -> int:
    """
    Get the unique COM identity (IUnknown pointer value) for a dispatch object.

    This provides a stable identity for the COM object that can be used to
    distinguish between different tabs in Windows 11 tabbed Explorer, even
    when they share the same top-level HWND.
    """
    try:
        unk = dispatch.QueryInterface(IUnknown)
        # COM identity rule: two references address the same object when their
        # IUnknown pointer values are equal. The wrapper releases its reference
        # on GC; only the raw address is kept.
        return int(cast(unk, c_void_p).value or 0)
    except Exception:
        # Fallback: use Python object id
        return id(dispatch)


def _get_view_mode_safe(dispatch: object) -> int | None:
    """Get view mode, returning None if not ready instead of raising."""
    try:
        doc = getattr(dispatch, "Document", None)
        if doc is None:
            return None
        return int(getattr(doc, "CurrentViewMode"))
    except Exception:
        return None


@dataclass(frozen=True)
class ShellWindow:
    dispatch: object
    hwnd: int
    exe_name: str
    location_url: str
    tab_id: int = field(default=0)  # Unique COM identity for tab tracking
    view_mode: int | None = field(default=None)  # FVM_DETAILS = 4


@dataclass
class TabState:
    """
    Mutable state for a single Explorer tab (identified by tab_id).

    This tracks autosize state per-tab rather than per-window, which is
    essential for Windows 11 tabbed Explorer.
    """

    tab_id: int
    hwnd: int
    path: str = ""
    view_mode: int | None = None
    navigation_token: int = 0
    last_autosize_time: float = 0.0
    settled_since: float = 0.0  # When we first saw this stable path
    failure_count: int = 0
    backoff_until: float = 0.0
    last_error_transient: bool = False


def iter_shell_windows(logger: logging.Logger) -> Iterable[ShellWindow]:
    try:
        shell = comtypes.client.CreateObject("Shell.Application")
    except (OSError, comtypes.COMError, Exception) as e:
        logger.debug("Shell.Application creation failed. Error was: %r", e)
        return

    try:
        windows = shell.Windows()
        if windows is None:
            return
    except (OSError, comtypes.COMError, Exception) as e:
        logger.debug("Shell.Application.Windows() failed. Error was: %r", e)
        return

    try:
        count = int(windows.Count)
    except (OSError, comtypes.COMError, Exception) as e:
        logger.debug("Shell.Application.Windows() count failed. Error was: %r", e)
        return
    logger.debug("Shell.Application.Windows() reported %d windows.", count)
    for i in range(count):
        try:
            w = windows.Item(i)
            if w is None:
                continue
            hwnd = int(w.HWND)
            full_name = str(getattr(w, "FullName", "") or "")
            exe = os.path.basename(full_name).lower()
            loc = str(getattr(w, "LocationURL", "") or "")
            tab_id = _get_com_identity(w)
            view_mode = _get_view_mode_safe(w)
            yield ShellWindow(
                dispatch=w,
                hwnd=hwnd,
                exe_name=exe,
                location_url=loc,
                tab_id=tab_id,
                view_mode=view_mode,
            )
        except (OSError, comtypes.COMError, Exception) as e:
            logger.debug("Shell windows item %d failed. Error was: %r", i, e)
            continue


def iter_explorer_tabs(logger: logging.Logger) -> Iterable[ShellWindow]:
    """
    Iterate all Explorer tabs, yielding each as a ShellWindow with tab_id.

    This handles Windows 11 tabbed Explorer by yielding multiple entries
    for the same HWND (one per tab).
    """
    for sw in iter_shell_windows(logger):
        if sw.exe_name == "explorer.exe":
            yield sw


def find_active_tab_for_hwnd(logger: logging.Logger, hwnd: int) -> ShellWindow | None:
    """
    Find the active tab for a given Explorer top-level HWND.

    In Windows 11 with tabs, multiple tabs can share the same HWND.
    This function attempts to identify the active tab by checking:
    1. If only one tab matches the HWND, return it
    2. Try to match by focus (which tab's view has focus)
    3. Fall back to the first non-empty path

    Returns None if no Explorer tabs match the HWND.
    """
    candidates = [sw for sw in iter_explorer_tabs(logger) if sw.hwnd == hwnd]

    if not candidates:
        logger.debug("find_active_tab_for_hwnd: no candidates for hwnd=%s", hwnd)
        return None

    if len(candidates) == 1:
        logger.debug("find_active_tab_for_hwnd: single candidate for hwnd=%s", hwnd)
        return candidates[0]

    logger.debug(
        "find_active_tab_for_hwnd: %d candidates for hwnd=%s (Windows 11 tabs detected)",
        len(candidates),
        hwnd,
    )

    # Heuristic: prefer tabs in details view with non-empty paths
    scored = []
    for sw in candidates:
        score = 0
        if sw.location_url:
            score += 10
        if sw.view_mode == FVM_DETAILS:
            score += 5
        scored.append((score, sw))

    scored.sort(key=lambda x: (-x[0], x[1].location_url))
    best = scored[0][1] if scored else candidates[0]

    logger.debug(
        "find_active_tab_for_hwnd: selected tab_id=%s path=%s among %d candidates",
        best.tab_id,
        best.location_url,
        len(candidates),
    )
    return best


def find_all_tabs_for_hwnd(logger: logging.Logger, hwnd: int) -> list[ShellWindow]:
    """
    Find all tabs for a given Explorer top-level HWND.

    Returns list of ShellWindow objects, one per tab.
    """
    return [sw for sw in iter_explorer_tabs(logger) if sw.hwnd == hwnd]


def find_explorer_window_by_hwnd(logger: logging.Logger, hwnd: int) -> ShellWindow | None:
    """
    Legacy function: find an Explorer window by HWND.

    For Windows 11 tab support, prefer using find_active_tab_for_hwnd instead.
    This function now delegates to find_active_tab_for_hwnd.
    """
    return find_active_tab_for_hwnd(logger, hwnd)


def find_explorer_tab_by_id(logger: logging.Logger, tab_id: int) -> ShellWindow | None:
    """
    Find a specific Explorer tab by its tab_id (COM identity).

    This is the preferred method for targeting a specific tab.
    """
    for sw in iter_explorer_tabs(logger):
        if sw.tab_id == tab_id:
            return sw
    return None


def find_explorer_tab_by_path(
    logger: logging.Logger, hwnd: int, target_path: str
) -> ShellWindow | None:
    """
    Find a specific Explorer tab by HWND and path.

    This is the preferred method when targeting a specific tab in Windows 11
    where multiple tabs can share the same HWND.

    Args:
        logger: Logger instance
        hwnd: Top-level Explorer window handle
        target_path: The canonical path to match (lowercase, backslashes)

    Returns:
        ShellWindow for the matching tab, or None if not found
    """
    from urllib.parse import unquote

    def normalize_path(p: str) -> str:
        """Normalize a path for comparison."""
        if not p:
            return ""
        # Handle file:// URLs
        if p.startswith("file:///"):
            p = unquote(p[8:])  # Strip file:/// and decode
        elif p.startswith("file://"):
            p = unquote(p[7:])
        # Normalize slashes and case
        return p.replace("/", "\\").lower().rstrip("\\")

    target_normalized = normalize_path(target_path)

    candidates = [sw for sw in iter_explorer_tabs(logger) if sw.hwnd == hwnd]

    if not candidates:
        logger.debug("find_explorer_tab_by_path: no tabs for hwnd=%s", hwnd)
        return None

    # Find exact path match
    for sw in candidates:
        sw_path = normalize_path(sw.location_url)
        if sw_path == target_normalized:
            logger.debug(
                "find_explorer_tab_by_path: found exact match hwnd=%s path='%s'", hwnd, target_path
            )
            return sw

    # No exact match found
    logger.debug(
        "find_explorer_tab_by_path: no match for hwnd=%s path='%s' among %d candidates",
        hwnd,
        target_path,
        len(candidates),
    )
    return None


def _format_hresult(hr: int) -> str:
    return f"0x{(hr & 0xFFFFFFFF):08X}"


def _format_propertykey(pk: PROPERTYKEY) -> str:
    return f"{pk.fmtid}:{int(pk.pid)}"


def query_service_raw(
    logger: logging.Logger,
    dispatch_obj: object,
    service_guid: GUID,
    iid: GUID,
) -> c_void_p:
    unk = dispatch_obj.QueryInterface(IUnknown)
    sp = unk.QueryInterface(IServiceProvider)
    ppv_obj = sp.QueryService(service_guid, iid)
    ptr = ppv_obj.value if hasattr(ppv_obj, "value") else int(ppv_obj)
    logger.debug(
        "QueryService result, source_type=%s, service=%s, riid=%s, ppv=%s.",
        type(dispatch_obj),
        str(service_guid),
        str(iid),
        hex(ptr) if ptr else "0x0",
    )
    if not ptr:
        raise RuntimeError("QueryService returned a null pointer.")
    return c_void_p(ptr)


def get_view_mode_from_document(window_dispatch: object) -> tuple[int | None, str, str]:
    try:
        doc = getattr(window_dispatch, "Document", None)
        if doc is None:
            return None, "UNKNOWN", "Document was None."
        mode = int(getattr(doc, "CurrentViewMode"))
        name = FOLDERVIEWMODE_NAMES.get(mode, f"UNKNOWN({mode})")
        return mode, name, ""
    except Exception as e:
        return None, "UNKNOWN", f"Document.CurrentViewMode failed. Error was: {e!r}."


def get_service_provider_sources(window_dispatch: object) -> list[tuple[str, object]]:
    sources: list[tuple[str, object]] = []
    try:
        doc = getattr(window_dispatch, "Document", None)
        if doc is not None:
            sources.append(("document", doc))
    except Exception:
        pass
    sources.append(("window", window_dispatch))
    return sources


def _dump_visible_columns(
    logger: logging.Logger, cm: POINTER(IColumnManager), keys: ctypes.Array, n: int
) -> None:
    info = CM_COLUMNINFO()
    info.cbSize = sizeof(CM_COLUMNINFO)
    info.dwMask = (
        CM_MASK_NAME | CM_MASK_WIDTH | CM_MASK_DEFAULTWIDTH | CM_MASK_IDEALWIDTH | CM_MASK_STATE
    )
    for i in range(n):
        pk = keys[i]
        try:
            result = cm.GetColumnInfo(byref(pk), info)
            hr = int(result) if isinstance(result, int) else 0
            if hr != 0:
                logger.debug(
                    "GetColumnInfo failed for %s, hr=%s.",
                    _format_propertykey(pk),
                    _format_hresult(hr),
                )
                continue
            name = "".join(info.wszName).rstrip("\0")
            logger.info(
                "Visible column %d/%d, key=%s, name=%r, "
                "width=%d, default_width=%d, ideal_width=%d, state=0x%08X.",
                i + 1,
                n,
                _format_propertykey(pk),
                name,
                int(info.uWidth),
                int(info.uDefaultWidth),
                int(info.uIdealWidth),
                int(info.dwState),
            )
        except Exception as e:
            logger.debug(
                "GetColumnInfo exception for %s. Error was: %r", _format_propertykey(pk), e
            )


def autosize_visible_columns_for_dispatch(
    logger: logging.Logger,
    window_dispatch: object,
    dump_columns: bool,
) -> tuple[int, int]:
    last_error: BaseException | None = None
    for source_name, src in get_service_provider_sources(window_dispatch):
        try:
            logger.debug("Autosize start using source=%s.", source_name)
            ppv = query_service_raw(logger, src, SID_SFolderView, IColumnManager._iid_)
            cm = cast(ppv, POINTER(IColumnManager))
            try:
                count = wintypes.UINT(0)
                logger.debug("Calling IColumnManager.GetColumnCount.")
                hr = int(cm.GetColumnCount(CM_ENUM_VISIBLE, byref(count)))
                if hr != 0:
                    raise comtypes.COMError(hr, "GetColumnCount failed.", None)
                n = int(count.value)
                logger.debug("Visible column count was %d.", n)
                if n <= 0:
                    return (0, 0)
                keys = (PROPERTYKEY * n)()
                logger.debug("Calling IColumnManager.GetColumns for %d columns.", n)
                hr = int(cm.GetColumns(CM_ENUM_VISIBLE, keys, n))
                if hr != 0:
                    raise comtypes.COMError(hr, "GetColumns failed.", None)
                if dump_columns:
                    _dump_visible_columns(logger, cm, keys, n)
                info = CM_COLUMNINFO()
                info.cbSize = sizeof(CM_COLUMNINFO)
                info.dwMask = CM_MASK_WIDTH
                info.dwState = 0
                info.uWidth = c_uint(CM_WIDTH_AUTOSIZE).value
                info.uDefaultWidth = 0
                info.uIdealWidth = 0
                info.wszName = "\0" * 80
                attempted = 0
                succeeded = 0
                for i in range(n):
                    attempted += 1
                    pk = keys[i]
                    try:
                        hr = int(cm.SetColumnInfo(byref(pk), byref(info)))
                        if hr == 0:
                            succeeded += 1
                        else:
                            logger.debug(
                                "SetColumnInfo failed for %s, hr=%s.",
                                _format_propertykey(pk),
                                _format_hresult(hr),
                            )
                    except Exception as e:
                        logger.debug(
                            "SetColumnInfo exception for %s. Error was: %r",
                            _format_propertykey(pk),
                            e,
                        )
                logger.debug("Autosize finished using source=%s.", source_name)
                return (attempted, succeeded)
            finally:
                # Ownership note: QueryService returned exactly one reference,
                # and the comtypes pointer created by cast() releases it when
                # the wrapper is garbage collected. An explicit Release() here
                # would over-release the proxy by one.
                del cm
        except BaseException as e:
            last_error = e
            logger.debug("Autosize failed using source=%s. Error was: %r", source_name, e)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not acquire IColumnManager from any service provider source.")


def _is_transient_error(exc: BaseException) -> bool:
    """
    Check if an exception represents a transient COM error.

    Transient errors occur during navigation, tab switching, or view rebinding
    and should be retried rather than treated as permanent failures.
    """
    if isinstance(exc, comtypes.COMError):
        hr = getattr(exc, "hresult", 0)
        if hr is None:
            hr = 0
        return (hr & 0xFFFFFFFF) in TRANSIENT_HRESULT_CODES

    # Check for null pointer errors
    error_msg = str(exc).lower()
    if "null" in error_msg or "none" in error_msg or "not connected" in error_msg:
        return True

    if isinstance(exc, (AttributeError, TypeError)):
        return True

    return False


@dataclass
class AutosizeResult:
    """
    Detailed result from an autosize attempt.

    Attributes:
        success: True if columns were successfully autosized
        method: Method used (e.g., "com", "none")
        transient_error: True if failure was due to transient state (retry recommended)
        error_message: Human-readable error description
        columns_attempted: Number of columns we tried to autosize
        columns_succeeded: Number of columns successfully autosized
    """

    success: bool
    method: str
    transient_error: bool = False
    error_message: str = ""
    columns_attempted: int = 0
    columns_succeeded: int = 0


def apply_to_window(
    logger: logging.Logger,
    sw: ShellWindow,
    require_details: bool,
    dump_columns: bool,
) -> tuple[int, int, int | None]:
    """Autosize one window's columns. Returns (attempted, succeeded, view_mode).

    The view mode is returned so callers can distinguish "skipped because the
    view is not Details" (permanent until the user changes the view) from a
    genuine failure worth retrying.
    """
    mode, name, err = get_view_mode_from_document(sw.dispatch)
    if mode is not None:
        logger.info("HWND %d, Document view %d (%s), URL %s.", sw.hwnd, mode, name, sw.location_url)
    else:
        logger.info("HWND %d, Document view UNKNOWN, %s, URL %s.", sw.hwnd, err, sw.location_url)
    if require_details and mode is not None and mode != FVM_DETAILS:
        logger.info("Skip HWND %d, effective view was %d (%s).", sw.hwnd, mode, name)
        return (0, 0, mode)
    attempted, succeeded = autosize_visible_columns_for_dispatch(
        logger, sw.dispatch, dump_columns=dump_columns
    )
    return (attempted, succeeded, mode)


def autosize_explorer_columns(
    hwnd: int,
    allow_keyboard_fallback: bool = True,
    require_details: bool = True,
    dump_columns: bool = False,
    target_path: str | None = None,
    caller_owns_com: bool = False,
) -> tuple[bool, str]:
    """
    Auto-size visible columns for a given Explorer window HWND using COM.
    The allow_keyboard_fallback parameter is accepted for compatibility but ignored.

    Args:
        hwnd: Top-level Explorer window handle
        allow_keyboard_fallback: Ignored, kept for compatibility
        require_details: Only autosize if view is in Details mode
        dump_columns: Log column info for debugging
        target_path: If provided, find the tab matching this path (for Windows 11 tabs)
        caller_owns_com: If True, caller manages COM init/uninit (worker thread ownership)
    """
    LOG.info("autosize_explorer_columns: start hwnd=%s target_path=%s", hwnd, target_path)

    if not caller_owns_com:
        comtypes.CoInitialize()

    try:
        # Find the specific tab by path if provided, otherwise use active tab
        if target_path:
            sw = find_explorer_tab_by_path(LOG, hwnd, target_path)
        else:
            sw = find_explorer_window_by_hwnd(LOG, hwnd)
        if sw is None:
            LOG.info(
                "autosize_explorer_columns: Explorer window not found for HWND %s path=%s",
                hwnd,
                target_path,
            )
            return False, "not-found"
        attempted, succeeded, mode = apply_to_window(
            LOG,
            sw,
            require_details=require_details,
            dump_columns=dump_columns,
        )
        if require_details and mode is not None and mode != FVM_DETAILS:
            # Not a failure to retry: the view simply is not Details.
            return False, "not-details"
        ok = attempted > 0 and succeeded > 0
        return (ok, "com" if ok else "none")
    except BaseException as e:
        LOG.debug("autosize_explorer_columns: exception: %r", e, exc_info=True)
        return False, "error"
    finally:
        if not caller_owns_com:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


def autosize_explorer_columns_detailed(
    hwnd: int,
    tab_id: int | None = None,
    require_details: bool = True,
    dump_columns: bool = False,
    caller_owns_com: bool = False,
) -> AutosizeResult:
    """
    Auto-size visible columns with detailed result reporting.

    Args:
        hwnd: Top-level Explorer window handle
        tab_id: Optional tab identifier for multi-tab windows
        require_details: Only autosize if view is in Details mode
        dump_columns: Log column info for debugging
        caller_owns_com: If True, caller manages COM init/uninit (worker thread ownership)

    Returns:
        AutosizeResult with detailed success/failure information
    """
    LOG.info("autosize_explorer_columns_detailed: start hwnd=%s tab_id=%s", hwnd, tab_id)

    if not caller_owns_com:
        comtypes.CoInitialize()

    try:
        # Find the specific tab or the active tab for this window
        if tab_id is not None:
            sw = find_explorer_tab_by_id(LOG, tab_id)
            if sw is None:
                LOG.info("autosize_explorer_columns_detailed: tab_id=%s not found", tab_id)
                return AutosizeResult(
                    success=False,
                    method="none",
                    transient_error=True,  # Tab may have closed, retry may work
                    error_message=f"Tab {tab_id} not found",
                )
        else:
            sw = find_active_tab_for_hwnd(LOG, hwnd)
            if sw is None:
                LOG.info("autosize_explorer_columns_detailed: no tab found for hwnd=%s", hwnd)
                return AutosizeResult(
                    success=False,
                    method="none",
                    transient_error=True,
                    error_message=f"No Explorer tab found for HWND {hwnd}",
                )

        # Check view mode before attempting
        if require_details:
            mode = sw.view_mode
            if mode is None:
                LOG.debug("autosize_explorer_columns_detailed: view mode unknown, will retry")
                return AutosizeResult(
                    success=False,
                    method="none",
                    transient_error=True,
                    error_message="View mode not yet available",
                )
            if mode != FVM_DETAILS:
                LOG.info(
                    "autosize_explorer_columns_detailed: view mode %d != Details, skipping", mode
                )
                return AutosizeResult(
                    success=False,
                    method="none",
                    transient_error=False,
                    error_message=(
                        f"View mode {FOLDERVIEWMODE_NAMES.get(mode, str(mode))} is not Details"
                    ),
                )

        attempted, succeeded, _ = apply_to_window(
            LOG,
            sw,
            require_details=require_details,
            dump_columns=dump_columns,
        )
        ok = attempted > 0 and succeeded > 0
        return AutosizeResult(
            success=ok,
            method="com" if ok else "none",
            transient_error=False,
            error_message="" if ok else "SetColumnInfo failed for all columns",
            columns_attempted=attempted,
            columns_succeeded=succeeded,
        )
    except BaseException as e:
        LOG.debug("autosize_explorer_columns_detailed: exception: %r", e, exc_info=True)
        is_transient = _is_transient_error(e)
        return AutosizeResult(
            success=False, method="none", transient_error=is_transient, error_message=str(e)
        )
    finally:
        if not caller_owns_com:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


def autosize_tab(
    tab_id: int,
    require_details: bool = True,
    caller_owns_com: bool = False,
) -> AutosizeResult:
    """
    Auto-size columns for a specific Explorer tab by its tab_id.

    This is the preferred method for tab-aware autosize operations.

    Args:
        tab_id: Unique tab identifier
        require_details: Only autosize if view is in Details mode
        caller_owns_com: If True, caller manages COM init/uninit
    """
    LOG.info("autosize_tab: tab_id=%s", tab_id)

    if not caller_owns_com:
        comtypes.CoInitialize()

    try:
        sw = find_explorer_tab_by_id(LOG, tab_id)
        if sw is None:
            return AutosizeResult(
                success=False,
                method="none",
                transient_error=True,
                error_message=f"Tab {tab_id} not found",
            )
        return autosize_explorer_columns_detailed(
            sw.hwnd,
            tab_id=tab_id,
            require_details=require_details,
            caller_owns_com=True,  # We already own COM here
        )
    finally:
        if not caller_owns_com:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


# canonicalize_path is imported from virelo.platform.paths (consolidated duplicate)
