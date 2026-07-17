"""QWebEngineView host for the Virelo React frontend.

``VireloWebView`` fills its parent, registers ``VireloBridge`` as ``bridge``
through ``QWebChannel``, and routes JavaScript console messages to Python
logging. Development mode connects to the Vite server, while release mode
loads static files from ``frontend/dist``.

Usage in ``MainWindow``::

    self.webview = VireloWebView(bridge, parent=self)
    # Add self.webview to the central widget layout.
"""

import logging
import os

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from virelo.bridge import VireloBridge
from virelo.platform.resources import resource_path
from virelo.platform.web_navigation import is_trusted_document_navigation

LOG = logging.getLogger("Virelo")

# Development mode requires an explicit ``VIRELO_DEV=1`` environment variable.
DEV_SERVER_URL = "http://localhost:5173"

_MISSING_FRONTEND_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Virelo</title>
<style>
  body { font-family: system-ui, sans-serif; background: #1a1a1a; color: #e0e0e0;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .box { max-width: 480px; text-align: center; }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: 12px; }
  p { font-size: 14px; color: #999; line-height: 1.6; }
  code { background: #2a2a2a; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
</style>
</head>
<body>
<div class="box">
  <h1>Frontend build not found</h1>
  <p>The file <code>frontend/dist/index.html</code> is missing.<br>
  Run <code>scripts/build-frontend.ps1</code> to build the frontend.</p>
</div>
</body>
</html>"""


def _is_dev_mode() -> bool:
    """Return True if we should connect to the Vite dev server.

    Dev mode requires explicit opt-in via VIRELO_DEV=1 environment variable.
    Running from source without VIRELO_DEV=1 behaves like release mode.
    """
    return os.environ.get("VIRELO_DEV", "").lower() in ("1", "true", "yes")


def _get_frontend_url() -> QUrl | None:
    """Return the URL for the React frontend, or None if missing in release mode."""
    if _is_dev_mode():
        LOG.info("WebView: development mode is loading from %s.", DEV_SERVER_URL)
        return QUrl(DEV_SERVER_URL)

    # Release mode loads ``frontend/dist/index.html`` through a file URL.
    dist_path = resource_path(os.path.join("frontend", "dist", "index.html"))
    if not os.path.exists(dist_path):
        # Fall back to a path relative to this module.
        dist_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "frontend", "dist", "index.html"
        )
    if not os.path.exists(dist_path):
        LOG.error("WebView: the frontend build is missing at %s.", dist_path)
        return None
    LOG.info("WebView: release mode is loading from %s.", dist_path)
    return QUrl.fromLocalFile(dist_path)


class VireloWebPage(QWebEnginePage):
    """Custom page that routes JS console to Python logging and filters navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frontend_url: str | None = None
        self._dev_mode = False
        self._allow_error_document = False

    def set_navigation_policy(self, frontend_url: QUrl | None, dev_mode: bool) -> None:
        """Pin privileged document navigation to Virelo's selected frontend."""
        self._frontend_url = frontend_url.toString() if frontend_url is not None else None
        self._dev_mode = dev_mode
        self._allow_error_document = frontend_url is None

    def clear_error_document_allowance(self, *_args) -> None:
        """Expire the one-time fallback-document navigation allowance."""
        self._allow_error_document = False

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """Allow only the selected main document to retain bridge access."""
        if not is_main_frame:
            LOG.warning("Blocked subframe navigation to %s.", url.toString())
            return False
        allowed = is_trusted_document_navigation(
            url.toString(),
            frontend_url=self._frontend_url,
            dev_server_url=DEV_SERVER_URL,
            dev_mode=self._dev_mode,
            allow_error_document=self._allow_error_document,
        )
        if allowed:
            if url.scheme().lower() in {"about", "data"}:
                self._allow_error_document = False
            return True
        LOG.warning(
            "Blocked navigation to %s (type=%s, main_frame=%s).",
            url.toString(),
            nav_type,
            is_main_frame,
        )
        return False

    def javaScriptConsoleMessage(self, level, message, line, source):
        prefix = f"[JS:{source}:{line}]"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            LOG.error("%s %s", prefix, message)
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            LOG.warning("%s %s", prefix, message)
        else:
            LOG.debug("%s %s", prefix, message)


class VireloWebView(QWebEngineView):
    """QWebEngineView hosting the Virelo React frontend.

    A ``QWebChannel`` registers the provided ``VireloBridge`` as ``bridge``.
    Development mode uses the Vite server, while release mode uses local files.

    The public ``bridge`` attribute exposes the ``VireloBridge`` instance, and
    ``reload_frontend()`` reloads the page after development changes.
    """

    def __init__(self, bridge: VireloBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge

        frontend_url = _get_frontend_url()
        dev_mode = _is_dev_mode()

        # Use a custom page for JavaScript console routing.
        page = VireloWebPage(self)
        page.set_navigation_policy(frontend_url, dev_mode)
        page.loadFinished.connect(page.clear_error_document_allowance)

        # Configure web settings.
        settings = page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, dev_mode
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        # Set up ``QWebChannel``.
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", bridge)
        page.setWebChannel(self._channel)

        self.setPage(page)

        # Disable the context menu in release mode to prevent inspector access.
        if not dev_mode:
            from PySide6.QtCore import Qt

            self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Load the frontend.
        if frontend_url is None:
            page.setHtml(_MISSING_FRONTEND_HTML)
            LOG.warning("VireloWebView: showing the missing-frontend error page.")
        else:
            self.setUrl(frontend_url)
            LOG.info("VireloWebView initialized and is loading %s.", frontend_url.toString())

    def reload_frontend(self) -> None:
        """Reload the frontend page."""
        url = _get_frontend_url()
        page = self.page()
        if isinstance(page, VireloWebPage):
            page.set_navigation_policy(url, _is_dev_mode())
        if url is None:
            page.setHtml(_MISSING_FRONTEND_HTML)
            LOG.warning("VireloWebView: showing the missing-frontend error page.")
        else:
            self.setUrl(url)
