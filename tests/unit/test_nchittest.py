"""Tests for WM_NCHITTEST signed lParam extraction and hit-zone classification.

Tests cover two behaviors added to MainWindow.nativeEvent:
1. Signed 16-bit coordinate extraction from lParam (multi-monitor support)
2. Hit-zone classification including HTCAPTION title bar drag zone

All tests are pure-logic unit tests that do NOT require Qt or a running desktop.
"""

import sys

import pytest

# -- WM_NCHITTEST return codes --
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


# ---------------------------------------------------------------------------
# Helper: signed 16-bit extraction (mirrors ctypes.c_short(val & 0xFFFF).value)
# ---------------------------------------------------------------------------


def signed_short(val):
    """Extract a signed 16-bit value from an unsigned integer.

    This mirrors the corrected lParam extraction in nativeEvent:
        ctypes.c_short(msg.lParam & 0xFFFF).value
    """
    import ctypes

    return ctypes.c_short(val & 0xFFFF).value


# ---------------------------------------------------------------------------
# Helper: hit-zone classification (mirrors nativeEvent logic)
# ---------------------------------------------------------------------------


def classify_hit(pos_x, pos_y, width, height, border=4, title_bar_height=35, controls_width=60):
    """Classify a window-relative position into an NCHITTEST result code.

    Mirrors the priority logic in MainWindow.nativeEvent:
    1. Edges and corners (BORDER grab zone) -- highest priority
    2. Title bar drag zone (HTCAPTION) -- below border, excluding controls area
    3. Fall through (return 0) -- let super() handle
    """
    result = 0

    # 1. Edges and corners
    if pos_x <= border:
        if pos_y <= border:
            result = HTTOPLEFT
        elif pos_y >= height - border:
            result = HTBOTTOMLEFT
        else:
            result = HTLEFT
    elif pos_x >= width - border:
        if pos_y <= border:
            result = HTTOPRIGHT
        elif pos_y >= height - border:
            result = HTBOTTOMRIGHT
        else:
            result = HTRIGHT
    elif pos_y <= border:
        result = HTTOP
    elif pos_y >= height - border:
        result = HTBOTTOM

    if result:
        return result

    # 2. Title bar drag zone (HTCAPTION)
    if pos_y < title_bar_height and pos_x >= border and pos_x < width - controls_width:
        return HTCAPTION

    # 3. Fall through
    return 0


# ===========================================================================
# Tests: signed_short extraction
# ===========================================================================


@pytest.mark.skipif(sys.platform != "win32", reason="Win32-only (ctypes.c_short)")
class TestSignedShort:
    """Verify signed 16-bit extraction from unsigned lParam values."""

    def test_negative_monitor_x(self):
        """Unsigned 63616 decodes to signed -1920 (monitor at x=-1920)."""
        assert signed_short(63616) == -1920

    def test_zero(self):
        """Zero stays zero."""
        assert signed_short(0) == 0

    def test_positive_value(self):
        """Positive 500 stays positive."""
        assert signed_short(500) == 500

    def test_max_unsigned_is_minus_one(self):
        """65535 (0xFFFF) decodes to -1."""
        assert signed_short(65535) == -1

    def test_min_signed_short(self):
        """32768 (0x8000) decodes to -32768 (minimum signed short)."""
        assert signed_short(32768) == -32768

    def test_max_signed_short(self):
        """32767 (0x7FFF) decodes to 32767 (maximum signed short)."""
        assert signed_short(32767) == 32767


# ===========================================================================
# Tests: classify_hit (hit-zone classification)
# ===========================================================================
# Standard window: 1000x620, border=4, title_bar_height=35, controls_width=60


class TestClassifyHit:
    """Verify hit-zone classification for NCHITTEST regions."""

    def test_htcaption_center_title_bar(self):
        """Center of title bar returns HTCAPTION."""
        assert classify_hit(500, 10, 1000, 620) == HTCAPTION

    def test_htcaption_left_side_title_bar(self):
        """Left side of title bar (below border) returns HTCAPTION."""
        assert classify_hit(100, 5, 1000, 620) == HTCAPTION

    def test_htleft_edge(self):
        """Left edge of window returns HTLEFT."""
        assert classify_hit(2, 300, 1000, 620) == HTLEFT

    def test_htright_edge(self):
        """Right edge of window returns HTRIGHT."""
        assert classify_hit(998, 300, 1000, 620) == HTRIGHT

    def test_httopleft_corner(self):
        """Top-left corner returns HTTOPLEFT."""
        assert classify_hit(2, 2, 1000, 620) == HTTOPLEFT

    def test_httopright_corner(self):
        """Top-right corner returns HTTOPRIGHT."""
        assert classify_hit(998, 2, 1000, 620) == HTTOPRIGHT

    def test_htbottomleft_corner(self):
        """Bottom-left corner returns HTBOTTOMLEFT."""
        assert classify_hit(2, 618, 1000, 620) == HTBOTTOMLEFT

    def test_htbottomright_corner(self):
        """Bottom-right corner returns HTBOTTOMRIGHT."""
        assert classify_hit(998, 618, 1000, 620) == HTBOTTOMRIGHT

    def test_httop_edge(self):
        """Top edge of window returns HTTOP."""
        assert classify_hit(500, 2, 1000, 620) == HTTOP

    def test_htbottom_edge(self):
        """Bottom edge of window returns HTBOTTOM."""
        assert classify_hit(500, 618, 1000, 620) == HTBOTTOM

    def test_controls_area_not_htcaption(self):
        """Controls area (x >= 940) does NOT return HTCAPTION."""
        assert classify_hit(960, 10, 1000, 620) == 0

    def test_below_title_bar_falls_through(self):
        """Position below title bar (y >= 35) falls through to 0."""
        assert classify_hit(500, 100, 1000, 620) == 0

    def test_just_before_controls_is_htcaption(self):
        """Position just before controls area (x=939) returns HTCAPTION."""
        assert classify_hit(939, 10, 1000, 620) == HTCAPTION

    def test_left_border_takes_priority_over_title_bar(self):
        """Left border zone takes priority over title bar (pos_x <= BORDER)."""
        # pos_x=3 is within BORDER=4, even though pos_y=10 is in title bar
        assert classify_hit(3, 10, 1000, 620) == HTLEFT

    def test_controls_boundary_exact(self):
        """Exact controls boundary (x=940 = 1000-60) returns 0 (in controls)."""
        assert classify_hit(940, 10, 1000, 620) == 0

    def test_title_bar_boundary_exact(self):
        """Exact title bar boundary (y=35) falls through (not < 35)."""
        assert classify_hit(500, 35, 1000, 620) == 0
