"""Settings state management for the VireloBridge.

Reads all settings keys from QSettings via the existing Settings class
and returns them as a JSON-serializable dict. Validates and writes settings
back via a draft/commit model: changes accumulate in a draft dict, Save
persists to QSettings and applies side effects, Discard reverts to persisted
values.
"""

import json

from virelo.app.config import DEFAULTS, normalize_snap_presses
from virelo.platform.theme import normalize_theme_mode
from virelo.settings.persistence import Settings

_VALID_ACCENTS = ("slate", "teal", "blue", "rust", "purple")
_VALID_DENSITIES = ("compact", "cozy", "comfortable")


def _strict_bool(value):
    """Parse strict boolean values. Raises ValueError for ambiguous input.

    Accepts: True, False, "true", "false", 1, 0
    Rejects: "yes", "no", "on", "off", None, non-boolean strings

    This prevents Python's bool("false") == True pitfall at the bridge boundary.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"Expected 0 or 1, got {value}")
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        raise ValueError(f"Expected 'true' or 'false', got '{value}'")
    raise ValueError(f"Cannot convert {type(value).__name__} to bool")


class SettingsState:
    """Thin wrapper around Settings that provides JSON-friendly read/write.

    Uses a draft/commit model:
    - apply_draft() validates and stores changes in _draft (not persisted)
    - commit_draft() persists _draft to QSettings and clears it
    - discard_draft() clears _draft without persisting
    - get_all() returns persisted settings overlaid with draft values
    - has_draft indicates whether unsaved changes exist
    """

    # Exhaustive key list with (type_coercer, validator_range_or_None)
    KEYS = {
        "snap_key": (str, None),
        "restore_key": (str, None),
        "enable_snap": (_strict_bool, None),
        "snap_presses": (int, (1, 10)),
        "snap_interval": (int, (100, 5000)),
        "width_pct": (int, (10, 100)),
        "height_pct": (int, (10, 100)),
        "ex_auto_size": (_strict_bool, None),
        "game_mode_enabled": (_strict_bool, None),
        "run_at_startup": (_strict_bool, None),
        "theme": (str, None),
        "accent": (str, None),
        "density": (str, None),
        "minimize_to_tray": (_strict_bool, None),
    }

    def __init__(self, settings: Settings):
        self._settings = settings
        self._draft = None  # None = no pending changes

    def get_all(self) -> dict:
        """Return all settings as a JSON-serializable dict.

        Returns persisted settings overlaid with any draft values.
        Normalization applies after the overlay so draft values are
        also normalized.
        """
        result = {}
        for key, (coercer, _) in self.KEYS.items():
            val = getattr(self._settings, key, DEFAULTS.get(key))
            result[key] = coercer(val)
        # Overlay draft values before normalization
        if self._draft:
            result.update(self._draft)
        # Normalize theme
        result["theme"] = normalize_theme_mode(result["theme"], DEFAULTS["theme"])
        # Normalize snap_presses
        result["snap_presses"] = normalize_snap_presses(result["snap_presses"])
        return result

    def get_json(self) -> str:
        """Return all settings as a JSON string."""
        return json.dumps(self.get_all())

    @property
    def has_draft(self) -> bool:
        """Return whether unsaved changes exist."""
        return self._draft is not None and len(self._draft) > 0

    def apply_draft(self, data: dict) -> dict:
        """Validate and store changes in draft (not persisted).

        Returns {"ok": True, "applied": {key: value, ...}} on success.
        Returns {"ok": False, "error": "..."} on validation failure or
        unknown keys.
        """
        # Reject unknown keys up front
        unknown = [k for k in data if k not in self.KEYS]
        if unknown:
            return {"ok": False, "error": f"Unknown keys: {unknown}"}

        validated = {}
        for key, value in data.items():
            coercer, bounds = self.KEYS[key]
            try:
                coerced = coercer(value)
            except (ValueError, TypeError) as e:
                return {"ok": False, "error": f"Invalid type for {key}: {e}"}
            if bounds is not None:
                lo, hi = bounds
                if not (lo <= coerced <= hi):
                    return {
                        "ok": False,
                        "error": f"{key} must be between {lo} and {hi}, got {coerced}",
                    }
            if key == "theme":
                coerced = normalize_theme_mode(coerced, DEFAULTS["theme"])
            if key == "snap_presses":
                coerced = normalize_snap_presses(coerced)
            if key == "accent":
                coerced = coerced.strip().lower()
                if coerced not in _VALID_ACCENTS:
                    coerced = DEFAULTS["accent"]
            if key == "density":
                coerced = coerced.strip().lower()
                if coerced not in _VALID_DENSITIES:
                    coerced = DEFAULTS["density"]
            validated[key] = coerced

        if self._draft is None:
            self._draft = {}
        self._draft.update(validated)

        return {"ok": True, "applied": validated}

    def commit_draft(self) -> dict:
        """Persist draft to QSettings and clear draft. Returns applied changes."""
        if not self._draft:
            return {"ok": True, "applied": {}}
        for key, value in self._draft.items():
            setattr(self._settings, key, value)
        self._settings.save()
        applied = dict(self._draft)
        self._draft = None
        return {"ok": True, "applied": applied}

    def discard_draft(self):
        """Clear draft without persisting."""
        self._draft = None

    def reset_to_defaults(self) -> dict:
        """Reset all settings to defaults and return the new state."""
        self._draft = None
        for key, val in DEFAULTS.items():
            setattr(self._settings, key, val)
        self._settings.save()
        return self.get_all()
