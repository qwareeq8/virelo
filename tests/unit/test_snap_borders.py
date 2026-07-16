"""Tests for DWM invisible-border compensation in snap centering."""

from virelo.services.snap import window_border_deltas


def test_no_visible_rect_means_zero_borders():
    assert window_border_deltas((0, 0, 100, 100), None) == (0, 0, 0, 0)


def test_typical_win11_borders():
    """A typical window has ~7px invisible borders on the sides and bottom."""
    win = (100, 100, 900, 700)
    visible = (107, 100, 893, 693)
    assert window_border_deltas(win, visible) == (7, 0, 7, 7)


def test_identical_rects_mean_zero_borders():
    rect = (10, 20, 300, 400)
    assert window_border_deltas(rect, rect) == (0, 0, 0, 0)


def test_bogus_dwm_answer_is_clamped():
    """A DWM rect wildly outside the window rect must not fling the window."""
    win = (0, 0, 100, 100)
    visible = (500, -500, -500, 900)
    left, top, right, bottom = window_border_deltas(win, visible)
    assert 0 <= left <= 64
    assert 0 <= top <= 64
    assert 0 <= right <= 64
    assert 0 <= bottom <= 64
