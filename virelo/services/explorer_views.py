"""Explorer default folder view management.

Makes Details view the default for every File Explorer folder type using
the same registry mechanism as LesFerch/WinSetView, reduced to a single
opinionated action:

1. Back up the affected registry keys to .reg files.
2. Delete the per-folder view caches (Bags and BagMRU in both hives) and
   the saved view defaults (Streams\\Defaults) so stale states cannot
   shadow the new defaults.
3. Copy HKLM FolderTypes to HKCU (Explorer prefers the HKCU copy) and
   force LogicalViewMode=Details on every TopViews entry.
4. Write Details-view bag entries for This PC, which has no FolderTypes
   GUID of its own.
5. Restart Explorer so the running shell drops its cached view state.

The module separates pure plan construction (testable everywhere) from
the Windows-only executor (winreg is imported lazily so unit tests can
import this module on any platform).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

LOG = logging.getLogger("Virelo")

# Registry paths, all relative to HKCU unless noted otherwise.
SHELL_CLASSES = r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell"
BAGS_KEY = SHELL_CLASSES + r"\Bags"
BAGMRU_KEY = SHELL_CLASSES + r"\BagMRU"
SHELL_LEGACY = r"Software\Microsoft\Windows\Shell"
BAGS_LEGACY_KEY = SHELL_LEGACY + r"\Bags"
BAGMRU_LEGACY_KEY = SHELL_LEGACY + r"\BagMRU"
STREAMS_DEFAULTS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Streams\Defaults"
FOLDER_TYPES_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FolderTypes"

# This PC has no FolderTypes entry; its view lives in a numbered bag.
THIS_PC_GUID = "{5C4F28B5-F869-4E84-8E60-F11DB97C5CC7}"
THIS_PC_PIDL = bytes.fromhex("14001F50E04FD020EA3A6910A2D808002B30309D0000")

# Details view constants (WinSetView SetViewValues index 1).
LOGICAL_VIEW_MODE_DETAILS = 1
MODE_DETAILS = 4
ICON_SIZE_DETAILS = 16
BAG_FFLAGS = 0x41200001
GROUP_BY_FMTID = "{B725F130-47EF-101A-A5F1-02608C9EEBAC}"
GROUP_BY_PID = 4

# Keys removed when clearing cached view state (HKCU-relative).
VIEW_CACHE_KEYS = (
    BAGMRU_KEY,
    BAGS_KEY,
    BAGMRU_LEGACY_KEY,
    BAGS_LEGACY_KEY,
    STREAMS_DEFAULTS_KEY,
    FOLDER_TYPES_KEY,
)

# Keys exported to the backup before anything is modified.
BACKUP_KEYS = VIEW_CACHE_KEYS


@dataclass(frozen=True)
class RegValue:
    """One registry value write, relative to HKCU."""

    key: str
    name: str
    kind: str  # "dword", "sz", or "binary"
    data: int | str | bytes


def this_pc_bag_values() -> list[RegValue]:
    """Build the value writes that force Details view for This PC."""
    values = [
        RegValue(BAGMRU_KEY, "NodeSlots", "binary", b"\x02"),
        RegValue(BAGMRU_KEY, "MRUListEx", "binary", bytes.fromhex("00000000ffffffff")),
        RegValue(BAGMRU_KEY, "0", "binary", THIS_PC_PIDL),
        RegValue(BAGMRU_KEY + r"\0", "NodeSlot", "dword", 1),
    ]
    for bag in (
        rf"{BAGS_KEY}\1\Shell\{THIS_PC_GUID}",
        rf"{BAGS_KEY}\1\ComDlg\{THIS_PC_GUID}",
    ):
        values.extend(
            [
                RegValue(bag, "FFlags", "dword", BAG_FFLAGS),
                RegValue(bag, "LogicalViewMode", "dword", LOGICAL_VIEW_MODE_DETAILS),
                RegValue(bag, "Mode", "dword", MODE_DETAILS),
                RegValue(bag, "GroupView", "dword", 1),
                RegValue(bag, "IconSize", "dword", ICON_SIZE_DETAILS),
                RegValue(bag, "GroupByKey:FMTID", "sz", GROUP_BY_FMTID),
                RegValue(bag, "GroupByKey:PID", "dword", GROUP_BY_PID),
            ]
        )
    return values


def top_view_values(top_view_key: str) -> list[RegValue]:
    """Build the value writes that force Details on one TopViews entry."""
    return [
        RegValue(top_view_key, "LogicalViewMode", "dword", LOGICAL_VIEW_MODE_DETAILS),
        RegValue(top_view_key, "IconSize", "dword", ICON_SIZE_DETAILS),
    ]


def backup_dir_name(now: datetime) -> str:
    """Return the timestamped directory name for a registry backup."""
    return now.strftime("view-backup-%Y%m%d-%H%M%S")


# ----------------------------------------------------------------------------
# Windows-only executor (winreg imported lazily; safe to import cross-platform)
# ----------------------------------------------------------------------------


def _open_winreg():
    import winreg

    return winreg


def _delete_key_tree(winreg, root, path: str) -> None:
    """Recursively delete a registry key. Missing keys are not an error."""
    access = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
    try:
        key = winreg.OpenKey(root, path, 0, access)
    except OSError:
        return
    try:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_key_tree(winreg, root, path + "\\" + child)
    finally:
        key.Close()
    try:
        winreg.DeleteKeyEx(root, path, winreg.KEY_WOW64_64KEY, 0)
    except OSError:
        LOG.warning("Could not delete registry key HKCU\\%s", path)


def _copy_key_tree(winreg, src_root, src_path: str, dst_root, dst_path: str) -> None:
    """Recursively copy a registry key tree, preserving value types."""
    read = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    write = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
    with winreg.OpenKey(src_root, src_path, 0, read) as src:
        with winreg.CreateKeyEx(dst_root, dst_path, 0, write) as dst:
            index = 0
            while True:
                try:
                    name, data, kind = winreg.EnumValue(src, index)
                except OSError:
                    break
                winreg.SetValueEx(dst, name, 0, kind, data)
                index += 1
        index = 0
        while True:
            try:
                child = winreg.EnumKey(src, index)
            except OSError:
                break
            _copy_key_tree(
                winreg, src_root, src_path + "\\" + child, dst_root, dst_path + "\\" + child
            )
            index += 1


def _write_values(winreg, values: list[RegValue]) -> None:
    """Apply a list of RegValue writes under HKCU."""
    kinds = {
        "dword": winreg.REG_DWORD,
        "sz": winreg.REG_SZ,
        "binary": winreg.REG_BINARY,
    }
    access = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
    for value in values:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, value.key, 0, access) as key:
            winreg.SetValueEx(key, value.name, 0, kinds[value.kind], value.data)


def _force_details_on_folder_types(winreg) -> int:
    """Force Details on every TopViews entry of the HKCU FolderTypes copy.

    Returns the number of TopViews entries updated.
    """
    read = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    updated = 0
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FOLDER_TYPES_KEY, 0, read) as folder_types:
        index = 0
        while True:
            try:
                type_guid = winreg.EnumKey(folder_types, index)
            except OSError:
                break
            index += 1
            top_views = rf"{FOLDER_TYPES_KEY}\{type_guid}\TopViews"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, top_views, 0, read) as views:
                    view_index = 0
                    view_guids = []
                    while True:
                        try:
                            view_guids.append(winreg.EnumKey(views, view_index))
                        except OSError:
                            break
                        view_index += 1
            except OSError:
                continue
            for view_guid in view_guids:
                _write_values(winreg, top_view_values(rf"{top_views}\{view_guid}"))
                updated += 1
    return updated


def _backup_registry_state() -> str:
    """Export the affected keys to .reg files. Returns the backup directory."""
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Virelo")
    target = os.path.join(base, backup_dir_name(datetime.now()))
    os.makedirs(target, exist_ok=True)
    for index, key in enumerate(BACKUP_KEYS):
        out_file = os.path.join(target, f"{index:02d}-{key.rsplit(chr(92), 1)[-1]}.reg")
        result = subprocess.run(
            ["reg.exe", "export", "HKCU\\" + key, out_file, "/y", "/reg:64"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
        if result.returncode != 0:
            # Key may simply not exist yet; that is fine for a backup.
            LOG.info("Backup skipped for missing key HKCU\\%s", key)
    return target


def _shell_token():
    """Duplicate the running shell's token so Explorer can be relaunched
    without inheriting this process's elevation. Returns a token handle
    or None."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    hwnd = user32.GetShellWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not process:
        return None
    try:
        TOKEN_DUPLICATE = 0x0002
        TOKEN_QUERY = 0x0008
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            process, TOKEN_DUPLICATE | TOKEN_QUERY, ctypes.byref(token)
        ):
            return None
        try:
            MAXIMUM_ALLOWED = 0x02000000
            SECURITY_IMPERSONATION = 2
            TOKEN_PRIMARY = 1
            primary = wintypes.HANDLE()
            if not advapi32.DuplicateTokenEx(
                token,
                MAXIMUM_ALLOWED,
                None,
                SECURITY_IMPERSONATION,
                TOKEN_PRIMARY,
                ctypes.byref(primary),
            ):
                return None
            return primary
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(process)


def restart_explorer() -> bool:
    """Kill and relaunch Explorer, de-elevating the new shell if possible.

    Returns True if a new Explorer process was started.
    """
    import ctypes
    from ctypes import wintypes

    token = _shell_token()

    result = subprocess.run(
        ["taskkill.exe", "/f", "/im", "explorer.exe"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode not in (0, 128):
        LOG.warning("taskkill explorer.exe returned %s", result.returncode)
    time.sleep(1.0)

    explorer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
    if token is not None:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        startup = STARTUPINFO()
        startup.cb = ctypes.sizeof(STARTUPINFO)
        info = PROCESS_INFORMATION()
        launched = advapi32.CreateProcessWithTokenW(
            token,
            0,
            explorer,
            None,
            0,
            None,
            None,
            ctypes.byref(startup),
            ctypes.byref(info),
        )
        if launched:
            kernel32.CloseHandle(info.hProcess)
            kernel32.CloseHandle(info.hThread)
        kernel32.CloseHandle(token)
        if launched:
            return True
        LOG.warning(
            "CreateProcessWithTokenW failed (error %s); falling back to direct launch",
            ctypes.get_last_error(),
        )

    try:
        subprocess.Popen([explorer], close_fds=True)
        return True
    except OSError:
        LOG.exception("Failed to relaunch Explorer")
        return False


def apply_details_default() -> dict:
    """Make Details view the default for all folders. Restarts Explorer.

    Returns a bridge-style result dict.
    """
    winreg = _open_winreg()
    try:
        backup = _backup_registry_state()

        for key in VIEW_CACHE_KEYS:
            _delete_key_tree(winreg, winreg.HKEY_CURRENT_USER, key)

        _copy_key_tree(
            winreg,
            winreg.HKEY_LOCAL_MACHINE,
            FOLDER_TYPES_KEY,
            winreg.HKEY_CURRENT_USER,
            FOLDER_TYPES_KEY,
        )
        updated = _force_details_on_folder_types(winreg)
        _write_values(winreg, this_pc_bag_values())

        restarted = restart_explorer()
        LOG.info(
            "Details view applied: %d folder views updated, backup at %s, restart=%s",
            updated,
            backup,
            restarted,
        )
        return {
            "ok": True,
            "data": {"updated": updated, "backup": backup, "restarted": restarted},
        }
    except Exception as e:
        LOG.exception("apply_details_default failed")
        return {"ok": False, "error": str(e)}


def reset_folder_views() -> dict:
    """Remove all custom view state so Explorer returns to Windows defaults.

    Restarts Explorer. Returns a bridge-style result dict.
    """
    winreg = _open_winreg()
    try:
        backup = _backup_registry_state()
        for key in VIEW_CACHE_KEYS:
            _delete_key_tree(winreg, winreg.HKEY_CURRENT_USER, key)
        restarted = restart_explorer()
        LOG.info("Folder views reset to defaults, backup at %s, restart=%s", backup, restarted)
        return {"ok": True, "data": {"backup": backup, "restarted": restarted}}
    except Exception as e:
        LOG.exception("reset_folder_views failed")
        return {"ok": False, "error": str(e)}
