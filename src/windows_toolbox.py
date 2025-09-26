"""Windows toolbox application entry point.

This module hosts the PyQt-based user interface and the supporting backend
helpers that implement two core features:

* A "Shift" triple-press shortcut that centers and resizes the foreground
  window or restores it to its original dimensions.
* A background Explorer manager that normalises view settings in open Windows
  Explorer instances.

The previous iteration of this module featured dated documentation blocks and
loosely typed helpers. The file has been refreshed to adhere to PEP 8/257 and
NumPy docstring guidelines and now includes richer typing hints so that future
refactors remain maintainable.
"""

from __future__ import annotations

import ctypes
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Final, Iterable, Iterator, Optional, Tuple, TypedDict, cast

from ctypes import wintypes

import keyboard
import psutil
import pywintypes
import win32api
import win32com.client
import win32gui
from PyQt5 import QtCore, QtGui, QtWidgets

if sys.platform != "win32":
    raise OSError("windows_toolbox requires a Windows environment")

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

user32 = ctypes.windll.user32
SW_RESTORE = 9
MONITOR_DEFAULTTONEAREST = 2

PROGRAM_NAME: Final[str] = "windows_toolbox"
SETTINGS_FILENAME: Final[str] = "snap_and_restore_settings.json"
ICON_FILENAME: Final[str] = "icon.ico"


class Settings(TypedDict):
    """Structured settings for the toolbox."""

    enable_snap_restore: bool
    enable_explorer_view: bool
    hotkey: str
    presses: int
    interval: int
    width_pct: int
    height_pct: int
    explorer_viewmode: int
    explorer_sortcolumn: str
    explorer_sortascending: bool
    explorer_enablegrouping: bool
    explorer_autosizecolumns: bool
    explorer_one_shot_ctrl_plus: bool


DEFAULT_SETTINGS: Final[Settings] = {
    "enable_snap_restore": True,
    "enable_explorer_view": True,
    "hotkey": "shift",
    "presses": 3,
    "interval": 1050,
    "width_pct": 76,
    "height_pct": 76,
    "explorer_viewmode": 4,
    "explorer_sortcolumn": "System.ItemNameDisplay",
    "explorer_sortascending": True,
    "explorer_enablegrouping": False,
    "explorer_autosizecolumns": True,
    "explorer_one_shot_ctrl_plus": True,
}


@dataclass(slots=True)
class WindowGeometry:
    """Bounds of a top-level window."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        """Right-most coordinate of the window rectangle."""

        return self.left + self.width

    @property
    def bottom(self) -> int:
        """Bottom coordinate of the window rectangle."""

        return self.top + self.height

#------------------------------------------------------------------------------
#
# Utility functions are defined here
#
#------------------------------------------------------------------------------

def resource_path(relative_path: str) -> Path:
    """Resolve a resource path for frozen and non-frozen deployments.

    Parameters
    ----------
    relative_path
        File name relative to the project root.

    Returns
    -------
    pathlib.Path
        Absolute path to the requested resource.
    """

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def get_settings_file_path() -> Path:
    """Return the expected settings file location."""

    if hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent / SETTINGS_FILENAME
    return Path(__file__).resolve().parent / SETTINGS_FILENAME


def _merge_settings(source: Dict[str, Any], destination: Settings) -> Settings:
    """Merge user settings into defaults while filtering unknown keys."""

    merged: Settings = destination.copy()
    for key, value in source.items():
        if key in destination:
            merged[key] = value
        else:
            logger.debug("Ignoring unknown settings key '%s'", key)
    return merged


def load_settings() -> Settings:
    """Load settings from disk, falling back to defaults on failure."""

    path = get_settings_file_path()
    if not path.exists():
        return cast(Settings, DEFAULT_SETTINGS.copy())

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return cast(Settings, DEFAULT_SETTINGS.copy())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load settings file %s: %s", path, exc)
        return cast(Settings, DEFAULT_SETTINGS.copy())

    if not isinstance(payload, dict):
        logger.warning("Unexpected settings format in %s; using defaults", path)
        return cast(Settings, DEFAULT_SETTINGS.copy())

    return _merge_settings(payload, DEFAULT_SETTINGS)


def save_settings(settings: Settings) -> None:
    """Persist toolbox settings to disk."""

    path = get_settings_file_path()
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
    except OSError as exc:
        logger.error("Unable to save settings to %s: %s", path, exc)

def is_explorer_foreground() -> bool:
    """Return ``True`` if the foreground window belongs to Explorer."""

    fg_hwnd = user32.GetForegroundWindow()
    if not fg_hwnd:
        return False

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
    try:
        process = psutil.Process(pid.value)
        return process.name().lower() == "explorer.exe"
    except (psutil.Error, OSError) as exc:
        logger.debug("Failed to resolve foreground process: %s", exc)
        return False


def send_ctrl_plus() -> None:
    """Simulate a single ``Ctrl`` + ``+`` keyboard press."""

    try:
        keyboard.press_and_release("ctrl+add")
    except (keyboard.KeyboardException, ValueError) as exc:
        logger.debug("Unable to send Ctrl+Plus hotkey: %s", exc)


def unmaximize_if_needed(hwnd: int) -> None:
    """Restore a maximised window before applying custom geometry."""

    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)


def get_window_hash(hwnd: int) -> str:
    """Return a string key that uniquely identifies a window."""

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_value = pid.value
    try:
        class_name = win32gui.GetClassName(hwnd)
        window_text = win32gui.GetWindowText(hwnd)
    except win32gui.error as exc:
        logger.debug("Unable to read window attributes for %s: %s", hwnd, exc)
        return str(pid_value or hwnd)
    return f"{pid_value}_{class_name}_{window_text}"


def find_child_window(parent_hwnd: int, child_class: str) -> Optional[int]:
    """Find the first child window with the supplied class name."""

    direct = win32gui.FindWindowEx(parent_hwnd, 0, child_class, None)
    if direct:
        return direct

    found: list[int] = []

    def enum_callback(hwnd, _):
        try:
            cname = win32gui.GetClassName(hwnd)
        except win32gui.error:
            return
        if cname.lower() == child_class.lower():
            found.append(hwnd)

    win32gui.EnumChildWindows(parent_hwnd, enum_callback, None)
    return found[0] if found else None

#------------------------------------------------------------------------------
#
# SHIFT TRIPLE-PRESS logic is implemented in the following class
#
#------------------------------------------------------------------------------

class ShiftTriplePress(QtCore.QObject):
    """Detect three ``Shift`` taps and toggle the active window geometry.

    Parameters
    ----------
    settings : Settings
        Toolbox settings dictionary.
    parent : QtCore.QObject, optional
        Optional QObject parent used by Qt for ownership tracking.
    """

    def __init__(self, settings: Settings, parent: Optional[QtCore.QObject] = None):
        """Initialise the triple-press handler and register the keyboard hook."""
        super().__init__(parent)
        self.settings: Settings = settings
        self.shift_held = False
        self.press_times: list[float] = []
        self.required_presses = int(self.settings["presses"])
        self.interval_s = float(self.settings["interval"]) / 1000.0

        # Store original window sizes for restoration
        self.original_sizes: dict[str, WindowGeometry] = {}

        hotkey_setting = str(self.settings.get("hotkey", "shift")).strip().lower()
        if hotkey_setting in {"left shift", "right shift"}:
            hotkey_setting = "shift"
        self.hotkey = hotkey_setting
        self._hook: Optional[Any] = None
        try:
            self._hook = keyboard.hook_key(self.hotkey, self.on_shift_event, suppress=False)
        except (keyboard.KeyboardException, ValueError) as exc:
            logger.error("Failed to register hotkey '%s': %s", self.hotkey, exc)

    def on_shift_event(self, event: keyboard.KeyboardEvent) -> None:
        """Handle keyboard events produced by the chosen hotkey."""
        if not self.settings.get("enable_snap_restore", False):
            return

        if event.event_type == 'down':
            if not self.shift_held:
                self.shift_held = True
                now = time.time()
                # Remove old press times outside the interval
                self.press_times = [t for t in self.press_times if now - t <= self.interval_s]
                self.press_times.append(now)
                if len(self.press_times) == self.required_presses:
                    self.press_times.clear()
                    try:
                        ctrl_pressed = keyboard.is_pressed('ctrl')
                    except keyboard.KeyboardException:
                        ctrl_pressed = False
                    if ctrl_pressed:
                        self.center_original_size()
                    else:
                        self.center_and_resize_window()
        elif event.event_type == 'up':
            self.shift_held = False

    def update_timing(self, presses: int, interval_ms: int) -> None:
        """Update cached timing parameters after a settings change."""

        self.required_presses = max(1, int(presses))
        self.interval_s = max(0.0, float(interval_ms) / 1000.0)

    def stop(self) -> None:
        """Detach the keyboard hook when shutting down the application."""

        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def center_and_resize_window(self) -> None:
        """Centre the active window using the configured percentages."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        unmaximize_if_needed(hwnd)

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            logger.debug("GetWindowRect failed for hwnd %s", hwnd)
            return
        original_geometry = WindowGeometry(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

        window_key = get_window_hash(hwnd)
        self.original_sizes.setdefault(window_key, original_geometry)

        width_pct = self.settings["width_pct"] / 100.0
        height_pct = self.settings["height_pct"] / 100.0

        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return
        try:
            monitor_info = win32api.GetMonitorInfo(monitor)
        except win32api.error as exc:
            logger.debug("GetMonitorInfo failed: %s", exc)
            return
        (m_left, m_top, m_right, m_bottom) = monitor_info["Monitor"]
        monitor_width = m_right - m_left
        monitor_height = m_bottom - m_top

        new_width = int(monitor_width * width_pct)
        new_height = int(monitor_height * height_pct)
        new_left = m_left + (monitor_width - new_width) // 2
        new_top = m_top + (monitor_height - new_height) // 2

        if not user32.MoveWindow(hwnd, new_left, new_top, new_width, new_height, True):
            logger.debug("MoveWindow failed when resizing %s", hwnd)

    def center_original_size(self) -> None:
        """Restore stored geometry and centre the window on screen."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        unmaximize_if_needed(hwnd)

        window_key = get_window_hash(hwnd)
        original = self.original_sizes.get(window_key)
        if not original:
            return

        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return
        try:
            monitor_info = win32api.GetMonitorInfo(monitor)
        except win32api.error as exc:
            logger.debug("GetMonitorInfo failed: %s", exc)
            return
        (m_left, m_top, m_right, m_bottom) = monitor_info["Monitor"]
        monitor_width = m_right - m_left
        monitor_height = m_bottom - m_top

        new_left = m_left + (monitor_width - original.width) // 2
        new_top = m_top + (monitor_height - original.height) // 2
        if not user32.MoveWindow(hwnd, new_left, new_top, original.width, original.height, True):
            logger.debug("MoveWindow failed when restoring %s", hwnd)

#------------------------------------------------------------------------------
#
# Explorer View Manager is implemented in the following class
#
#------------------------------------------------------------------------------

class ExplorerViewManager(QtCore.QObject):
    """Normalise view settings across open Explorer windows.

    Parameters
    ----------
    settings : Settings
        Toolbox settings dictionary.
    parent : QtCore.QObject, optional
        Optional QObject parent.
    """

    def __init__(self, settings: Settings, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.settings: Settings = settings
        self.enabled = bool(self.settings["enable_explorer_view"])
        self.last_paths: dict[int, str] = {}

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(4000)  # Poll every 4 seconds
        self.timer.timeout.connect(self.poll_explorer)
        if self.enabled:
            self.timer.start()

    def set_settings(self, settings: Settings) -> None:
        """Replace stored settings and update the enabled state."""

        self.settings = settings
        self.set_enabled(self.settings["enable_explorer_view"])

    def set_enabled(self, enable: bool) -> None:
        """Toggle the polling timer and clear state when disabled."""
        self.enabled = enable
        if enable:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
            self.last_paths.clear()

    def poll_explorer(self) -> None:
        """Inspect Explorer windows and apply configured adjustments."""
        if not self.enabled:
            return

        for hwnd, doc in self._iter_explorer_windows():
            self._handle_folder_change(hwnd, doc)
            self._apply_repeated_adjustments(doc)

    def _iter_explorer_windows(self) -> Iterable[Tuple[int, object]]:
        """Yield handles and documents for active Explorer windows."""

        try:
            shell = win32com.client.Dispatch("Shell.Application")
        except pywintypes.com_error as exc:
            logger.debug("Failed to dispatch Shell.Application: %s", exc)
            return

        for window in shell.Windows():
            if not window:
                continue
            try:
                name_lower = window.Name.lower()
            except (AttributeError, pywintypes.com_error):
                continue
            if "explorer" not in name_lower:
                continue
            try:
                doc = window.Document
            except (AttributeError, pywintypes.com_error):
                continue
            if not doc:
                continue
            yield window.HWND, doc

    def _handle_folder_change(self, hwnd: int, doc: object) -> None:
        """Trigger a one-shot column autosize when the folder path changes."""

        if not self.settings.get("explorer_one_shot_ctrl_plus", False):
            return
        new_path = ""
        try:
            new_path = doc.Folder.Self.Path
        except (AttributeError, pywintypes.com_error):
            return
        old_path = self.last_paths.get(hwnd)
        if new_path and new_path != old_path:
            self.last_paths[hwnd] = new_path
            if is_explorer_foreground():
                send_ctrl_plus()

    def _apply_repeated_adjustments(self, doc: object) -> None:
        """Apply persistent Explorer tweaks such as autosizing columns."""

        if not self.settings.get("explorer_autosizecolumns", False):
            return

        try:
            doc.CurrentViewMode = int(self.settings.get("explorer_viewmode", 4))
        except (AttributeError, pywintypes.com_error, ValueError) as exc:
            logger.debug("Unable to set view mode: %s", exc)

        if not self.settings.get("explorer_enablegrouping", False):
            try:
                doc.GroupBy = "System.Null"
            except (AttributeError, pywintypes.com_error) as exc:
                logger.debug("Unable to disable grouping: %s", exc)
        else:
            try:
                doc.GroupBy = self.settings["explorer_sortcolumn"]
            except (AttributeError, pywintypes.com_error, KeyError) as exc:
                logger.debug("Unable to set grouping: %s", exc)

        try:
            doc.SortColumns = self.settings["explorer_sortcolumn"]
            doc.SortAscending = bool(self.settings["explorer_sortascending"])
        except (AttributeError, pywintypes.com_error, KeyError) as exc:
            logger.debug("Unable to set sorting: %s", exc)

        try:
            mode = int(getattr(doc, "CurrentViewMode", 0))
        except (AttributeError, ValueError):
            mode = 0

        if mode == 4:
            for _ in range(5):
                send_ctrl_plus()
                time.sleep(0.1)

        try:
            doc.Refresh()
        except (AttributeError, pywintypes.com_error) as exc:
            logger.debug("Unable to refresh view: %s", exc)

#------------------------------------------------------------------------------
#
# Main UI is implemented in the following class
#
#------------------------------------------------------------------------------

class ToolboxMainWindow(QtWidgets.QMainWindow):
    """Main window stitching together the toolbox features."""

    def __init__(self) -> None:
        """Build the UI, load settings, and start helper managers."""
        super().__init__()
        icon_file = resource_path(ICON_FILENAME)
        self.setWindowIcon(QtGui.QIcon(str(icon_file)))
        self.setWindowTitle("Windows Toolbox (Repeated Ctrl+ +)")
        self.setGeometry(100, 100, 700, 640)
        self.settings: Settings = load_settings()

        # Initialize SHIFT triple-press manager
        self.shift_manager = ShiftTriplePress(self.settings)
        # Initialize Explorer view manager
        self.explorer_manager = ExplorerViewManager(self.settings)

        main_layout = QtWidgets.QVBoxLayout()

        # Snap & Restore checkbox
        self.snap_checkbox = QtWidgets.QCheckBox("Enable Snap & Restore (SHIFT triple-press)")
        self.snap_checkbox.setChecked(self.settings["enable_snap_restore"])
        self.snap_checkbox.stateChanged.connect(self.toggle_snap)
        main_layout.addWidget(self.snap_checkbox)

        snap_group = QtWidgets.QGroupBox("Snap & Restore Settings")
        snap_layout = QtWidgets.QVBoxLayout()

        # Presses slider and label
        press_layout = QtWidgets.QHBoxLayout()
        self.press_label = QtWidgets.QLabel(f"Times Pressed: {self.settings['presses']}")
        self.press_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.press_slider.setRange(1, 10)
        self.press_slider.setValue(self.settings["presses"])
        self.press_slider.valueChanged.connect(self.update_press_label)
        press_layout.addWidget(self.press_label)
        press_layout.addWidget(self.press_slider)
        snap_layout.addLayout(press_layout)

        # Interval slider and label
        interval_layout = QtWidgets.QHBoxLayout()
        self.interval_label = QtWidgets.QLabel(f"Press Interval (ms): {self.settings['interval']}")
        self.interval_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.interval_slider.setRange(100, 3000)
        self.interval_slider.setValue(self.settings["interval"])
        self.interval_slider.valueChanged.connect(self.update_interval_label)
        interval_layout.addWidget(self.interval_label)
        interval_layout.addWidget(self.interval_slider)
        snap_layout.addLayout(interval_layout)

        # Width percentage slider and label
        horiz_layout = QtWidgets.QHBoxLayout()
        self.horiz_label = QtWidgets.QLabel(f"Width Percentage: {self.settings['width_pct']}%")
        self.horiz_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.horiz_slider.setRange(10, 100)
        self.horiz_slider.setValue(self.settings["width_pct"])
        self.horiz_slider.valueChanged.connect(self.update_horiz_label)
        horiz_layout.addWidget(self.horiz_label)
        horiz_layout.addWidget(self.horiz_slider)
        snap_layout.addLayout(horiz_layout)

        # Height percentage slider and label
        vert_layout = QtWidgets.QHBoxLayout()
        self.vert_label = QtWidgets.QLabel(f"Height Percentage: {self.settings['height_pct']}%")
        self.vert_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.vert_slider.setRange(10, 100)
        self.vert_slider.setValue(self.settings["height_pct"])
        self.vert_slider.valueChanged.connect(self.update_vert_label)
        vert_layout.addWidget(self.vert_label)
        vert_layout.addWidget(self.vert_slider)
        snap_layout.addLayout(vert_layout)

        snap_group.setLayout(snap_layout)
        main_layout.addWidget(snap_group)

        # Explorer Manager checkbox
        self.explorer_checkbox = QtWidgets.QCheckBox("Enable Explorer View Manager")
        self.explorer_checkbox.setChecked(self.settings["enable_explorer_view"])
        self.explorer_checkbox.stateChanged.connect(self.toggle_explorer)
        main_layout.addWidget(self.explorer_checkbox)

        explorer_group = QtWidgets.QGroupBox("Explorer View Settings")
        explorer_layout = QtWidgets.QVBoxLayout()

        # View mode selection
        viewmode_layout = QtWidgets.QHBoxLayout()
        viewmode_label = QtWidgets.QLabel("View Mode:")
        self.viewmode_combo = QtWidgets.QComboBox()
        possible_view_modes = [
            ("Large Icons (1)", 1),
            ("Small Icons (2)", 2),
            ("List (3)", 3),
            ("Details (4)", 4),
            ("Tiles (5)", 5),
            ("Content (7)", 7),
        ]
        for label, val in possible_view_modes:
            self.viewmode_combo.addItem(label, val)
        current_vm = self.settings["explorer_viewmode"]
        idx = 0
        for i in range(self.viewmode_combo.count()):
            if self.viewmode_combo.itemData(i) == current_vm:
                idx = i
                break
        self.viewmode_combo.setCurrentIndex(idx)
        viewmode_layout.addWidget(viewmode_label)
        viewmode_layout.addWidget(self.viewmode_combo)
        explorer_layout.addLayout(viewmode_layout)

        # Sort column configuration
        sortcol_layout = QtWidgets.QHBoxLayout()
        sortcol_label = QtWidgets.QLabel("Sort By Column (PropertyKey):")
        self.sortcol_edit = QtWidgets.QLineEdit(self.settings["explorer_sortcolumn"])
        sortcol_layout.addWidget(sortcol_label)
        sortcol_layout.addWidget(self.sortcol_edit)
        explorer_layout.addLayout(sortcol_layout)

        # Sort ascending option
        self.sortasc_checkbox = QtWidgets.QCheckBox("Sort Ascending (unchecked => descending)")
        self.sortasc_checkbox.setChecked(self.settings["explorer_sortascending"])
        explorer_layout.addWidget(self.sortasc_checkbox)

        # Grouping option
        self.grouping_checkbox = QtWidgets.QCheckBox("Enable Grouping")
        self.grouping_checkbox.setChecked(self.settings["explorer_enablegrouping"])
        explorer_layout.addWidget(self.grouping_checkbox)

        # Repeated approach option
        self.autosize_checkbox = QtWidgets.QCheckBox("Repeated Ctrl+ + calls if in Details view")
        self.autosize_checkbox.setChecked(self.settings["explorer_autosizecolumns"])
        explorer_layout.addWidget(self.autosize_checkbox)

        # One-shot approach option
        self.oneshot_checkbox = QtWidgets.QCheckBox("One-Shot Ctrl+ + on folder changes")
        self.oneshot_checkbox.setChecked(self.settings["explorer_one_shot_ctrl_plus"])
        explorer_layout.addWidget(self.oneshot_checkbox)

        explorer_group.setLayout(explorer_layout)
        main_layout.addWidget(explorer_group)

        save_btn = QtWidgets.QPushButton("Save All Settings")
        save_btn.clicked.connect(self.save_all)
        main_layout.addWidget(save_btn)

        info_lbl = QtWidgets.QLabel(
            "Shift Triple-Press:\n"
            "  - Holding SHIFT doesn't cause multiple presses.\n"
            "  - 3 distinct presses in the interval => snap or restore.\n\n"
            "Explorer Manager:\n"
            "  - If 'Repeated Ctrl+ + calls' is ON, we spam Ctrl+ + multiple times\n"
            "    if Explorer is forced to Details view.\n"
            "  - If 'One-Shot' is ON, we do a single Ctrl+ + when a folder change is detected\n"
            "    (only if Explorer is in foreground).\n"
            "Some folders or templates may ignore these requests.\n"
        )
        main_layout.addWidget(info_lbl)

        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Setup system tray functionality
        icon_ = QtGui.QIcon(str(icon_file))
        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon_)
        self.tray_icon.setToolTip(PROGRAM_NAME)
        tray_menu = QtWidgets.QMenu()
        open_action = tray_menu.addAction("Open " + PROGRAM_NAME)
        open_action.triggered.connect(self.showNormal)
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.close_app)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_double_click)
        self.tray_icon.show()

    def toggle_snap(self, state: int) -> None:
        """Enable or disable the Shift triple-press workflow."""

        self.settings["enable_snap_restore"] = (state == QtCore.Qt.Checked)

    def toggle_explorer(self, state: int) -> None:
        """Enable or disable the Explorer manager."""

        self.settings["enable_explorer_view"] = (state == QtCore.Qt.Checked)
        self.explorer_manager.set_settings(self.settings)

    def update_press_label(self) -> None:
        """Refresh the triple-press count label."""

        val = self.press_slider.value()
        self.press_label.setText(f"Times Pressed: {val}")

    def update_interval_label(self) -> None:
        """Refresh the interval label."""

        val = self.interval_slider.value()
        self.interval_label.setText(f"Press Interval (ms): {val}")

    def update_horiz_label(self) -> None:
        """Refresh the width label."""

        val = self.horiz_slider.value()
        self.horiz_label.setText(f"Width Percentage: {val}%")

    def update_vert_label(self) -> None:
        """Refresh the height label."""

        val = self.vert_slider.value()
        self.vert_label.setText(f"Height Percentage: {val}%")

    def save_all(self) -> None:
        """Persist updated settings and reconfigure managers."""

        self.settings["enable_snap_restore"] = self.snap_checkbox.isChecked()
        self.settings["presses"] = self.press_slider.value()
        self.settings["interval"] = self.interval_slider.value()
        self.settings["width_pct"] = self.horiz_slider.value()
        self.settings["height_pct"] = self.vert_slider.value()
        self.settings["enable_explorer_view"] = self.explorer_checkbox.isChecked()
        view_mode_data = self.viewmode_combo.currentData()
        self.settings["explorer_viewmode"] = int(view_mode_data) if view_mode_data is not None else 4
        self.settings["explorer_sortcolumn"] = self.sortcol_edit.text().strip()
        self.settings["explorer_sortascending"] = self.sortasc_checkbox.isChecked()
        self.settings["explorer_enablegrouping"] = self.grouping_checkbox.isChecked()
        self.settings["explorer_autosizecolumns"] = self.autosize_checkbox.isChecked()
        self.settings["explorer_one_shot_ctrl_plus"] = self.oneshot_checkbox.isChecked()

        save_settings(self.settings)

        # Update SHIFT manager parameters
        self.shift_manager.update_timing(self.settings["presses"], self.settings["interval"])

        # Update Explorer manager settings
        self.explorer_manager.set_settings(self.settings)

    def on_tray_icon_double_click(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        """Restore the window when the tray icon is double-clicked."""

        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def close_app(self) -> None:
        """Tear down managers and exit the application."""

        self.shift_manager.stop()
        self.explorer_manager.set_enabled(False)
        self.tray_icon.hide()
        QtWidgets.QApplication.quit()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Minimise to tray instead of closing immediately."""

        event.ignore()
        self.showMinimized()

    def changeEvent(self, event: QtCore.QEvent) -> None:
        """Hide the window when minimised to reduce clutter."""

        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.isMinimized():
                QtCore.QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

class ToolboxApp(QtWidgets.QApplication):
    """Qt application wrapper that owns the main window."""

    def __init__(self, argv: Iterable[str]):
        """Create the application object and show the main window."""
        super().__init__(argv)
        self.main_window = ToolboxMainWindow()
        self.main_window.show()

def main() -> None:
    """Entrypoint that initialises and executes the Qt event loop."""
    app = ToolboxApp(sys.argv)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
#
# end of file
