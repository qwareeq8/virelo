"""Application entry point: logging, admin elevation, single instance, QApp, MainWindow."""

import argparse
import atexit
import ctypes
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from virelo.app.config import APP_NAME, LOG_DIR, LOG_FILE, ORGANIZATION


def _init_logger() -> logging.Logger:
    """Initialize a rotating file logger in a per-user location."""
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(base, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, LOG_FILE)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)  # Enable DEBUG level by default for troubleshooting
    logger.propagate = False

    existing_handler = None
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(
            handler, "baseFilename", None
        ) == os.path.abspath(log_path):
            existing_handler = handler
            break

    if existing_handler is None:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=512 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        handler.setLevel(logging.DEBUG)  # File handler captures all levels
        logger.addHandler(handler)
        existing_handler = handler

    # Also add a console handler for immediate feedback during development
    console_handler = None
    for h in logger.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler):
            console_handler = h
            break

    if console_handler is None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        console_handler.setLevel(logging.INFO)  # Console shows INFO and above
        logger.addHandler(console_handler)

    logger.log_path = getattr(existing_handler, "baseFilename", log_path)
    return logger


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_smoke_test():
    """Non-interactive boot verification (D-06, D-07, D-08)."""
    from PySide6 import QtCore, QtWidgets

    from virelo.app.config import APP_NAME, ORGANIZATION

    QtCore.QCoreApplication.setOrganizationName(ORGANIZATION)
    QtCore.QCoreApplication.setApplicationName(APP_NAME)
    app = QtWidgets.QApplication(sys.argv)  # noqa: F841 -- needed for Qt subsystems

    passed = 0
    failed = 0

    def check(name, fn):
        nonlocal passed, failed
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name} -- {e}")
            failed += 1

    print("Virelo smoke test")
    print("=" * 40)

    # Check 1: icon.ico resource path resolves and file exists
    def _check_icon():
        from virelo.platform.resources import resource_path

        path = resource_path("icon.ico")
        if not os.path.exists(path):
            raise FileNotFoundError(f"icon.ico not found at {path}")

    check("icon.ico resource path", _check_icon)

    # Check 2: frontend/dist/ exists and contains index.html
    def _check_frontend():
        from virelo.platform.resources import resource_path

        index_path = os.path.join(resource_path("frontend"), "dist", "index.html")
        if not os.path.exists(index_path):
            raise FileNotFoundError(f"frontend/dist/index.html not found at {index_path}")

    check("frontend/dist/index.html exists", _check_frontend)

    # Check 3: QWebEngine can be constructed
    def _check_webengine():
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        assert view is not None

    check("QWebEngine construction", _check_webengine)

    # Check 4: Settings reads/writes without exceptions
    def _check_settings():
        from virelo.settings.persistence import Settings

        s = Settings()
        _ = s.snap_key  # read a known key

    check("Settings read/write", _check_settings)

    # Check 5: SettingsState initializes with valid defaults
    def _check_settings_state():
        from virelo.settings.persistence import Settings
        from virelo.settings.state import SettingsState

        s = Settings()
        state = SettingsState(s)
        json_str = state.get_json()
        assert len(json_str) > 2, "SettingsState.get_json() returned empty"

    check("SettingsState defaults", _check_settings_state)

    # Check 6: VireloBridge initializes without errors
    def _check_bridge():
        from virelo.bridge.bridge import VireloBridge
        from virelo.services.snap import SnapService
        from virelo.settings.persistence import Settings
        from virelo.settings.state import SettingsState

        s = Settings()
        state = SettingsState(s)
        snap_svc = SnapService(None)
        bridge = VireloBridge(state, snap_svc)
        assert bridge is not None

    check("VireloBridge initialization", _check_bridge)

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def main():
    """Application entry point: elevate, init logging, launch MainWindow."""
    # Exit early on non-Windows platforms.
    if sys.platform != "win32":
        print("Virelo requires Windows.")
        sys.exit(1)

    # Parse --smoke-test BEFORE admin elevation (Pitfall 3: avoid UAC loop).
    parser = argparse.ArgumentParser(prog="virelo", add_help=False)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run non-interactive boot verification and exit",
    )
    args, _ = parser.parse_known_args()

    if args.smoke_test:
        sys.exit(_run_smoke_test())

    import faulthandler

    LOG = _init_logger()

    _CRASH_LOG = None
    try:
        crash_log_path = os.path.join(os.path.dirname(getattr(LOG, "log_path", "")), "crash.log")
        _CRASH_LOG = open(crash_log_path, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(_CRASH_LOG)
    except Exception:
        try:
            faulthandler.enable()
        except Exception:
            pass

    def _cleanup_faulthandler():
        if _CRASH_LOG:
            try:
                _CRASH_LOG.close()
            except Exception:
                pass

    atexit.register(_cleanup_faulthandler)

    if not _is_admin():
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            candidate = exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(candidate):
                exe = candidate
        hinst = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, f'"{script}" {params}', None, 1
        )
        if int(hinst) <= 32:
            sys.stderr.write("Elevation failed.\n")
            LOG.error("Elevation failed. ShellExecuteW returned %s.", hinst)
            return
        return  # Elevated child will run the app.

    import win32api
    import win32event
    import winerror
    from PySide6 import QtCore, QtWidgets

    from virelo.app.window import MainWindow
    from virelo.platform.win32_helpers import _enable_dpi_awareness

    _enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.yusufqwareeq.virelo")
    except Exception:
        pass

    QtCore.QCoreApplication.setOrganizationName(ORGANIZATION)
    QtCore.QCoreApplication.setApplicationName(APP_NAME)

    mutex = win32event.CreateMutex(None, False, f"Global\\{APP_NAME}_Mutex")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return

    app = QtWidgets.QApplication(sys.argv)
    # Safer to set after QApplication exists:
    QtWidgets.QApplication.setQuitOnLastWindowClosed(False)

    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        QtWidgets.QMessageBox.critical(None, "Error", "No system tray is available. Exiting.")
        return
    win = MainWindow()

    app.aboutToQuit.connect(lambda: (win._stop_background_threads(), win.shift_mgr.cleanup()))
    atexit.register(lambda: (win._stop_background_threads(), win.shift_mgr.cleanup()))

    win._singleton_mutex = mutex
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
