"""QWebEngineView host for the Virelo React frontend.

Provides VireloWebView which:
  - Creates a QWebEngineView sized to fill its parent
  - Sets up QWebChannel with the VireloBridge QObject registered as "bridge"
  - Detects dev mode (Vite dev server on localhost:5173) vs release mode
    (static files from frontend/dist/ loaded via file:// URL)
  - Provides a custom QWebEnginePage that routes JS console messages to Python logging

Usage in MainWindow:
    self.webview = VireloWebView(bridge, parent=self)
    # Add self.webview to the central widget layout
"""

import logging
import os

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from virelo.bridge import VireloBridge
from virelo.platform.resources import resource_path

LOG = logging.getLogger("Virelo")

# Dev mode detection: requires explicit VIRELO_DEV=1 environment variable
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


def _get_frontend_url():
    """Return the URL for the React frontend, or None if missing in release mode."""
    if _is_dev_mode():
        LOG.info("WebView: dev mode -- loading from %s", DEV_SERVER_URL)
        return QUrl(DEV_SERVER_URL)
    else:
        # Release mode: load from frontend/dist/index.html via file://
        dist_path = resource_path(os.path.join("frontend", "dist", "index.html"))
        if not os.path.exists(dist_path):
            # Fallback: try relative to script directory
            dist_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "frontend", "dist", "index.html"
            )
        if not os.path.exists(dist_path):
            LOG.error("WebView: frontend build missing at %s", dist_path)
            return None
        LOG.info("WebView: release mode -- loading from %s", dist_path)
        return QUrl.fromLocalFile(dist_path)


class VireloWebPage(QWebEnginePage):
    """Custom page that routes JS console to Python logging and filters navigation."""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """Block all navigation except local and dev-mode localhost URLs."""
        scheme = url.scheme().lower()
        # Allow file:// (release mode local files)
        if scheme == "file":
            return True
        # Allow data: (used internally by setHtml for error pages)
        if scheme == "data":
            return True
        # Allow localhost in dev mode only (Vite dev server)
        if scheme in ("http", "https") and url.host() == "localhost" and _is_dev_mode():
            return True
        # Block everything else
        LOG.warning(
            "Blocked navigation to: %s (type=%s, main_frame=%s)",
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

    Creates a QWebChannel and registers the provided VireloBridge as "bridge".
    Handles dev mode (Vite dev server) vs release mode (local files).

    Public API:
      - bridge: the VireloBridge instance
      - reload_frontend(): reload the page (useful after dev changes)
    """

    def __init__(self, bridge: VireloBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge

        # Custom page for JS console routing
        page = VireloWebPage(self)

        # Configure web settings
        settings = page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, _is_dev_mode()
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        # Set up QWebChannel
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", bridge)
        page.setWebChannel(self._channel)

        self.setPage(page)

        # Disable context menu in release mode (no Inspect Element access)
        if not _is_dev_mode():
            from PySide6.QtCore import Qt

            self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Load the frontend
        url = _get_frontend_url()
        if url is None:
            page.setHtml(_MISSING_FRONTEND_HTML)
            LOG.warning("VireloWebView: showing missing frontend error page")
        else:
            self.setUrl(url)
            LOG.info("VireloWebView initialized, loading: %s", url.toString())

    def reload_frontend(self):
        """Reload the frontend page."""
        url = _get_frontend_url()
        if url is None:
            self.page().setHtml(_MISSING_FRONTEND_HTML)
            LOG.warning("VireloWebView: showing missing frontend error page")
        else:
            self.setUrl(url)
