from PySide6 import QtCore

from virelo.app.config import APP_NAME, DEFAULTS, ORGANIZATION, SETTINGS_GROUP
from virelo.platform.theme import normalize_theme_mode


class Settings:
    """Persistent application settings using QSettings."""

    def __init__(self):
        self._qs = QtCore.QSettings(ORGANIZATION, APP_NAME)
        self._qs.beginGroup(SETTINGS_GROUP)
        self.snap_key = str(self._qs.value("snap_key", DEFAULTS["snap_key"], str))
        self.restore_key = str(self._qs.value("restore_key", DEFAULTS["restore_key"], str))
        self.enable_snap = _safe_bool(
            self._qs.value("enable_snap", DEFAULTS["enable_snap"], bool),
            DEFAULTS["enable_snap"],
        )
        # Bounds mirror SettingsState.KEYS: a corrupted or hand-edited registry
        # value must not reach the geometry math (width_pct=0 would create a
        # zero-size window; 150 would push it off-screen).
        self.snap_presses = _safe_int(
            self._qs.value("snap_presses", DEFAULTS["snap_presses"], int),
            DEFAULTS["snap_presses"],
            bounds=(1, 10),
        )
        self.snap_interval = _safe_int(
            self._qs.value("snap_interval", DEFAULTS["snap_interval"], int),
            DEFAULTS["snap_interval"],
            bounds=(100, 5000),
        )
        self.width_pct = _safe_int(
            self._qs.value("width_pct", DEFAULTS["width_pct"], int),
            DEFAULTS["width_pct"],
            bounds=(10, 100),
        )
        self.height_pct = _safe_int(
            self._qs.value("height_pct", DEFAULTS["height_pct"], int),
            DEFAULTS["height_pct"],
            bounds=(10, 100),
        )
        self.ex_auto_size = _safe_bool(
            self._qs.value("ex_auto_size", DEFAULTS["ex_auto_size"], bool),
            DEFAULTS["ex_auto_size"],
        )
        self.game_mode_enabled = _safe_bool(
            self._qs.value("game_mode_enabled", DEFAULTS["game_mode_enabled"], bool),
            DEFAULTS["game_mode_enabled"],
        )
        self.run_at_startup = _safe_bool(
            self._qs.value("run_at_startup", DEFAULTS["run_at_startup"], bool),
            DEFAULTS["run_at_startup"],
        )
        self.theme = normalize_theme_mode(
            self._qs.value("theme", DEFAULTS["theme"], str),
            DEFAULTS["theme"],
        )
        self.accent = str(self._qs.value("accent", DEFAULTS["accent"], str))
        self.density = str(self._qs.value("density", DEFAULTS["density"], str))
        self.minimize_to_tray = _safe_bool(
            self._qs.value("minimize_to_tray", DEFAULTS["minimize_to_tray"], bool),
            DEFAULTS["minimize_to_tray"],
        )
        self._qs.endGroup()

    def clear(self):
        self._qs.beginGroup(SETTINGS_GROUP)
        self._qs.remove("")
        self._qs.endGroup()

    def save(self):
        self.clear()
        self._qs.beginGroup(SETTINGS_GROUP)
        self._qs.setValue("snap_key", self.snap_key)
        self._qs.setValue("restore_key", self.restore_key)
        self._qs.setValue("enable_snap", self.enable_snap)
        self._qs.setValue("snap_presses", self.snap_presses)
        self._qs.setValue("snap_interval", self.snap_interval)
        self._qs.setValue("width_pct", self.width_pct)
        self._qs.setValue("height_pct", self.height_pct)
        self._qs.setValue("ex_auto_size", self.ex_auto_size)
        self._qs.setValue("run_at_startup", self.run_at_startup)
        self._qs.setValue("game_mode_enabled", self.game_mode_enabled)
        self._qs.setValue("theme", self.theme)
        self._qs.setValue("accent", self.accent)
        self._qs.setValue("density", self.density)
        self._qs.setValue("minimize_to_tray", self.minimize_to_tray)
        self._qs.endGroup()
        # Flush to the backing store and surface a write failure to the caller
        # instead of silently reporting a clean save.
        self._qs.sync()
        if self._qs.status() != QtCore.QSettings.Status.NoError:
            raise OSError(f"QSettings write failed: {self._qs.status()}")


def _safe_int(val, default, bounds=None):
    """Coerce to int, falling back to default; clamp into bounds when given."""
    try:
        if val is None:
            return default
        result = int(val)
    except Exception:
        return default
    if bounds is not None:
        lo, hi = bounds
        result = max(lo, min(hi, result))
    return result


def _safe_bool(val, default):
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    text = str(val).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    try:
        return bool(int(val))
    except Exception:
        return default
