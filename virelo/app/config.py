APP_NAME = "Virelo"
ORGANIZATION = "Yusuf Qwareeq"
APP_DISPLAY_NAME = "Virelo"
APP_VERSION = "1.5.0"
APP_EXECUTABLE_NAME = "Virelo.exe"
APP_DIST_DIR_NAME = "Virelo"
APP_PUBLISHER = "Yusuf Qwareeq"
APP_SUPPORT_URL = "https://github.com/yusufqwareeq/virelo"
APP_SETTINGS_ORG = "Yusuf Qwareeq"
APP_LOG_DIR = "Virelo"
APP_LOG_FILE = "virelo.log"
APP_ID = "com.yusufqwareeq.virelo"
LOG_DIR = "Virelo"
LOG_FILE = "virelo.log"
SETTINGS_GROUP = "Settings"

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
    """Coerce to an int in [1, 10]; out-of-range counts silently disable snapping."""
    try:
        val = int(value)
    except Exception:
        return DEFAULTS["snap_presses"]
    return max(1, min(10, val))
