"""Tests for WM_NCHITTEST signed lParam extraction and hit-zone classification.

Tests cover two behaviors added to MainWindow.nativeEvent:
1. Signed 16-bit coordinate extraction from lParam (multi-monitor support)
2. Hit-zone classification including HTCAPTION title bar drag zone

All tests are pure-logic unit tests that do NOT require Qt or a running desktop.
"""

import sys

import pytest

from virelo.app.window_hit_test import (
    HTBOTTOM,
    HTBOTTOMLEFT,
    HTBOTTOMRIGHT,
    HTCAPTION,
    HTLEFT,
    HTRIGHT,
    HTTOP,
    HTTOPLEFT,
    RESIZE_BORDER,
    TITLE_BAR_CONTROLS_WIDTH,
    TITLE_BAR_HEIGHT,
    TITLE_BAR_INTERACTIVE_WIDTH,
    classify_physical_window_hit,
    classify_window_hit,
    normalize_hit_test_regions,
)

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
# Helper: hit-zone classification
# ---------------------------------------------------------------------------


def classify_hit(pos_x, pos_y, width, height):
    """Call the production hit-zone classifier."""
    return classify_window_hit(pos_x, pos_y, width, height)


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
# Standard window: 1000x620 with production title-bar constants.


class TestClassifyHit:
    """Verify hit-zone classification for NCHITTEST regions."""

    def test_htcaption_center_title_bar(self):
        """Center of title bar returns HTCAPTION."""
        assert classify_hit(500, 10, 1000, 620) == HTCAPTION

    def test_search_area_is_client_content(self):
        """The logo, title, and search area remain clickable client content."""
        assert classify_hit(100, 10, 1000, 620) == 0
        assert classify_hit(TITLE_BAR_INTERACTIVE_WIDTH - 1, 10, 1000, 620) == 0

    def test_drag_region_starts_after_search_area(self):
        """The empty spacer immediately after the search area drags the window."""
        assert classify_hit(TITLE_BAR_INTERACTIVE_WIDTH, 10, 1000, 620) == HTCAPTION

    def test_htleft_edge(self):
        """Left edge of window returns HTLEFT."""
        assert classify_hit(2, 300, 1000, 620) == HTLEFT

    def test_htright_edge(self):
        """Right edge of window returns HTRIGHT."""
        assert classify_hit(998, 300, 1000, 620) == HTRIGHT

    def test_httopleft_corner(self):
        """Top-left corner returns HTTOPLEFT."""
        assert classify_hit(2, 2, 1000, 620) == HTTOPLEFT

    def test_httopright_corner_is_reserved_for_caption_controls(self):
        """The close-button corner remains client content instead of a resize target."""
        assert classify_hit(998, 2, 1000, 620) == 0

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
        """The complete 72-pixel controls area remains clickable."""
        boundary = 1000 - TITLE_BAR_CONTROLS_WIDTH
        assert classify_hit(boundary, 10, 1000, 620) == 0
        assert classify_hit(960, 10, 1000, 620) == 0

    def test_top_edge_of_window_controls_remains_clickable(self):
        """The first pixel after the resize edge is client content."""
        assert classify_hit(960, RESIZE_BORDER, 1000, 620) == 0

    def test_below_title_bar_falls_through(self):
        """Position below the title bar falls through to client handling."""
        assert classify_hit(500, 100, 1000, 620) == 0

    def test_just_before_controls_is_htcaption(self):
        """Position just before the controls area returns HTCAPTION."""
        boundary = 1000 - TITLE_BAR_CONTROLS_WIDTH
        assert classify_hit(boundary - 1, 10, 1000, 620) == HTCAPTION

    def test_left_border_takes_priority_over_title_bar(self):
        """Left border zone takes priority over title bar (pos_x < BORDER)."""
        # pos_x=3 is within BORDER=4, even though pos_y=10 is in title bar
        assert classify_hit(3, 10, 1000, 620) == HTLEFT

    def test_controls_boundary_exact(self):
        """The exact controls boundary returns client handling."""
        assert classify_hit(1000 - TITLE_BAR_CONTROLS_WIDTH, 10, 1000, 620) == 0

    def test_title_bar_boundary_exact(self):
        """The exact 34-pixel title boundary falls through to the page."""
        assert classify_hit(500, TITLE_BAR_HEIGHT, 1000, 620) == 0

    def test_measured_regions_replace_the_fallback_contract(self):
        """Measured frontend widths define the drag spacer without code duplication."""
        assert (
            classify_window_hit(
                400,
                10,
                1000,
                620,
                interactive_width=410,
                controls_width=90,
                title_bar_height=40,
            )
            == 0
        )
        assert (
            classify_window_hit(
                410,
                10,
                1000,
                620,
                interactive_width=410,
                controls_width=90,
                title_bar_height=40,
            )
            == HTCAPTION
        )


def test_physical_hit_testing_handles_negative_origin_at_150_percent() -> None:
    """A physical native point maps to the correct CSS-pixel drag region."""
    window_rect = (-1920, 120, -420, 1050)
    assert classify_physical_window_hit(-1170, 135, window_rect, 1.5) == HTCAPTION


def test_physical_hit_testing_scales_resize_border() -> None:
    """The four-DIP left resize strip becomes six physical pixels at 150 percent."""
    window_rect = (300, 200, 1800, 1130)
    assert classify_physical_window_hit(305, 650, window_rect, 1.5) == HTLEFT
    assert classify_physical_window_hit(306, 650, window_rect, 1.5) == 0


@pytest.mark.parametrize(
    ("regions", "error_type"),
    [
        ((True, 72, 34), TypeError),
        ((320, 0, 34), ValueError),
        ((320, 72, 0), ValueError),
        ((5000, 72, 34), ValueError),
    ],
)
def test_measured_region_validation_rejects_untrusted_values(regions, error_type) -> None:
    """The WebChannel measurement slot accepts only bounded integer CSS pixels."""
    with pytest.raises(error_type):
        normalize_hit_test_regions(*regions)
