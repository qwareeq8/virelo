APP_NAME = "Virelo"
ORGANIZATION = "Yusuf Qwareeq"
APP_VERSION = "1.5.0"
LOG_DIR = "Virelo"
LOG_FILE = "virelo.log"
SETTINGS_GROUP = "Settings"
INSTANCE_WINDOW_PROPERTY = "Virelo.InstanceWindow.v1"

DEFAULTS = {
    "snap_key": "shift",
    "restore_key": "ctrl",
    "enable_snap": True,
    "snap_presses": 3,
    "snap_interval": 1050,
    "width_pct": 76,
    "height_pct": 76,
    "ex_auto_size": False,
    "game_mode_enabled": True,
    "run_at_startup": False,
    "theme": "system",
    "accent": "slate",
    "density": "cozy",
    "minimize_to_tray": True,
}


def normalize_snap_presses(value):
    """Coerce a press count to an integer from 1 to 10."""
    try:
        val = int(value)
    except Exception:
        return DEFAULTS["snap_presses"]
    return max(1, min(10, val))
