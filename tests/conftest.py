"""Use installed native modules on Windows and test stubs on other platforms."""

import importlib
import importlib.util
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub native modules outside Windows or when unavailable in system Python.
# This must happen BEFORE any virelo.* imports so that transitive imports
# through __init__.py files do not fail with ModuleNotFoundError.
# ---------------------------------------------------------------------------

_NATIVE_STUBS = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtGui",
    "keyboard",
    "comtypes",
]

_NATIVE_ROOTS = {name.partition(".")[0] for name in _NATIVE_STUBS}
_MISSING_NATIVE_ROOTS = {
    root
    for root in _NATIVE_ROOTS
    if root not in sys.modules and importlib.util.find_spec(root) is None
}

for mod_name in _NATIVE_STUBS:
    if mod_name not in sys.modules:
        root = mod_name.partition(".")[0]
        if sys.platform == "win32" and root not in _MISSING_NATIVE_ROOTS:
            # Use installed native packages on Windows so ABI and integration
            # tests cannot silently pass against mocks. Import failures from an
            # installed but broken package are deliberately not suppressed.
            importlib.import_module(mod_name)
            continue
        stub = types.ModuleType(mod_name)
        # PySide6.QtCore needs QObject, Signal, Slot for class definitions
        if mod_name == "PySide6.QtCore":

            class _StubQObject:
                """Minimal QObject stand-in that can be subclassed."""

                def __init__(self, *a, **kw):
                    pass

                def __init_subclass__(cls, **kw):
                    pass

            stub.QObject = _StubQObject
            stub.Signal = lambda *a, **kw: MagicMock()
            stub.Slot = lambda *a, **kw: lambda f: f
            stub.Property = lambda *a, **kw: property(lambda self: None)
            stub.QTimer = types.SimpleNamespace(singleShot=MagicMock())
        sys.modules[mod_name] = stub

# Stub win32 modules with enough constants for win32_helpers.py to load
for mod_name in ["win32api", "win32con", "win32gui"]:
    if mod_name not in sys.modules:
        if importlib.util.find_spec(mod_name) is not None:
            importlib.import_module(mod_name)
            continue
        stub = types.ModuleType(mod_name)
        if mod_name == "win32con":
            # Constants used by win32_helpers.py
            stub.MONITOR_DEFAULTTONEAREST = 2
            stub.SW_MAXIMIZE = 3
            stub.SW_SHOWMAXIMIZED = 3
            stub.SW_RESTORE = 9
            stub.GWL_STYLE = -16
            stub.WS_CAPTION = 0x00C00000
            stub.WS_BORDER = 0x00800000
            stub.WS_POPUP = 0x80000000
            stub.WS_SIZEBOX = 0x00040000
            stub.GW_CHILD = 5
            stub.GW_HWNDNEXT = 2
        if mod_name == "win32api":
            stub.MonitorFromWindow = MagicMock()
            stub.GetMonitorInfo = MagicMock()
        if mod_name == "win32gui":
            stub.IsWindow = MagicMock(return_value=True)
            stub.IsWindowVisible = MagicMock(return_value=True)
            stub.IsIconic = MagicMock(return_value=False)
            stub.GetWindowText = MagicMock(return_value="Test")
            stub.GetClassName = MagicMock(return_value="")
            stub.GetWindowLong = MagicMock(return_value=0)
            stub.GetWindowPlacement = MagicMock(return_value=(0, 1, 0, (0, 0), (0, 0)))
            stub.ShowWindow = MagicMock()
            stub.GetWindow = MagicMock(return_value=0)
            stub.GetParent = MagicMock(return_value=0)
            stub.EnumWindows = MagicMock()
        sys.modules[mod_name] = stub


# ---------------------------------------------------------------------------
# Normal conftest fixtures
# ---------------------------------------------------------------------------

import pytest

from virelo.app.config import DEFAULTS


class MockSettings:
    """In-memory Settings replacement for unit tests. No QSettings/Qt dependency."""

    def __init__(self, **overrides):
        for key, val in DEFAULTS.items():
            setattr(self, key, overrides.get(key, val))

    def save(self):
        pass

    def clear(self):
        pass


@pytest.fixture
def mock_settings():
    return MockSettings()


@pytest.fixture
def settings_state(mock_settings):
    from virelo.settings.state import SettingsState

    return SettingsState(mock_settings)
