"""Tests for SettingsState validation, draft model, and coercion (QUAL-03, STRUCT-05).

These tests run without PySide6/WebEngine by using the MockSettings fixture.
"""

import pytest

from virelo.app.config import DEFAULTS
from virelo.settings.state import _strict_bool


def test_apply_draft_validates_range(settings_state):
    """width_pct=150 exceeds max 100, should fail."""
    result = settings_state.apply_draft({"width_pct": 150})
    assert result["ok"] is False
    assert "must be between" in result["error"]


def test_apply_draft_validates_range_low(settings_state):
    """width_pct=5 is below min 10, should fail."""
    result = settings_state.apply_draft({"width_pct": 5})
    assert result["ok"] is False
    assert "must be between" in result["error"]


def test_apply_draft_rejects_unknown_keys(settings_state):
    """Unknown keys should be rejected."""
    result = settings_state.apply_draft({"nonexistent_key": "val"})
    assert result["ok"] is False
    assert "Unknown" in result["error"]


def test_apply_draft_coerces_types(settings_state):
    """String '5' should be coerced to int 5 for snap_presses."""
    result = settings_state.apply_draft({"snap_presses": "5"})
    assert result["ok"] is True
    assert result["applied"]["snap_presses"] == 5


def test_apply_draft_valid_values(settings_state):
    """Valid width and height should be accepted."""
    result = settings_state.apply_draft({"width_pct": 50, "height_pct": 80})
    assert result["ok"] is True
    assert result["applied"]["width_pct"] == 50
    assert result["applied"]["height_pct"] == 80


def test_get_all_returns_all_keys(settings_state):
    """get_all should return a dict containing every key from DEFAULTS."""
    result = settings_state.get_all()
    for key in DEFAULTS:
        assert key in result, f"Missing key: {key}"


def test_commit_draft_persists(settings_state):
    """After apply + commit, has_draft should be False."""
    settings_state.apply_draft({"width_pct": 50})
    result = settings_state.commit_draft()
    assert result["ok"] is True
    assert settings_state.has_draft is False


def test_discard_draft_clears(settings_state):
    """After apply + discard, has_draft should be False."""
    settings_state.apply_draft({"width_pct": 50})
    assert settings_state.has_draft is True
    settings_state.discard_draft()
    assert settings_state.has_draft is False


def test_has_draft_initially_false(settings_state):
    """Fresh SettingsState should have no draft."""
    assert settings_state.has_draft is False


def test_get_all_overlays_draft(settings_state):
    """After applying width_pct=50, get_all should reflect the draft value."""
    settings_state.apply_draft({"width_pct": 50})
    result = settings_state.get_all()
    assert result["width_pct"] == 50


def test_reset_to_defaults_clears_draft(settings_state):
    """reset_to_defaults should clear any pending draft."""
    settings_state.apply_draft({"width_pct": 50})
    settings_state.reset_to_defaults()
    assert settings_state.has_draft is False


# --- _strict_bool tests (BRDG-04) ---


def test_strict_bool_accepts_true_false():
    """_strict_bool should accept Python True and False."""
    assert _strict_bool(True) is True
    assert _strict_bool(False) is False


def test_strict_bool_accepts_string_true_false():
    """_strict_bool should accept string 'true'/'false' (case-insensitive)."""
    assert _strict_bool("true") is True
    assert _strict_bool("false") is False
    assert _strict_bool("TRUE") is True
    assert _strict_bool("False") is False


def test_strict_bool_accepts_int_0_1():
    """_strict_bool should accept integers 0 and 1."""
    assert _strict_bool(0) is False
    assert _strict_bool(1) is True


def test_strict_bool_rejects_ambiguous():
    """_strict_bool should reject ambiguous input with ValueError."""
    for bad_value in ("yes", "no", "on", "off", None, "", 2):
        with pytest.raises(ValueError):
            _strict_bool(bad_value)


# --- apply_draft strict bool and new keys tests (BRDG-04, BRDG-06) ---


def test_apply_draft_strict_bool_prevents_false_string_bug(settings_state):
    """apply_draft({'enable_snap': 'false'}) must coerce to False, not True.

    This is the critical bug fix: Python's bool('false') returns True,
    but _strict_bool('false') correctly returns False.
    """
    result = settings_state.apply_draft({"enable_snap": "false"})
    assert result["ok"] is True
    assert result["applied"]["enable_snap"] is False


def test_apply_draft_accent_valid(settings_state):
    """apply_draft({'accent': 'teal'}) should succeed."""
    result = settings_state.apply_draft({"accent": "teal"})
    assert result["ok"] is True
    assert result["applied"]["accent"] == "teal"


def test_apply_draft_accent_invalid_defaults(settings_state):
    """apply_draft({'accent': 'neon'}) should coerce to default 'slate'."""
    result = settings_state.apply_draft({"accent": "neon"})
    assert result["ok"] is True
    assert result["applied"]["accent"] == "slate"


def test_apply_draft_density_valid(settings_state):
    """apply_draft({'density': 'compact'}) should succeed."""
    result = settings_state.apply_draft({"density": "compact"})
    assert result["ok"] is True
    assert result["applied"]["density"] == "compact"


def test_apply_draft_density_invalid_defaults(settings_state):
    """apply_draft({'density': 'huge'}) should coerce to default 'cozy'."""
    result = settings_state.apply_draft({"density": "huge"})
    assert result["ok"] is True
    assert result["applied"]["density"] == "cozy"


def test_apply_draft_minimize_to_tray(settings_state):
    """apply_draft({'minimize_to_tray': True}) should succeed."""
    result = settings_state.apply_draft({"minimize_to_tray": True})
    assert result["ok"] is True
    assert result["applied"]["minimize_to_tray"] is True


def test_apply_draft_minimize_to_tray_rejects_yes(settings_state):
    """apply_draft({'minimize_to_tray': 'yes'}) should fail (strict bool rejects 'yes')."""
    result = settings_state.apply_draft({"minimize_to_tray": "yes"})
    assert result["ok"] is False


def test_get_all_includes_new_keys(settings_state):
    """get_all() result must contain accent, density, minimize_to_tray keys."""
    result = settings_state.get_all()
    assert "accent" in result
    assert "density" in result
    assert "minimize_to_tray" in result


def test_commit_persists_new_keys(settings_state, mock_settings):
    """After apply+commit, mock_settings must have accent/density/minimize_to_tray updated."""
    settings_state.apply_draft(
        {
            "accent": "teal",
            "density": "compact",
            "minimize_to_tray": False,
        }
    )
    result = settings_state.commit_draft()
    assert result["ok"] is True
    assert mock_settings.accent == "teal"
    assert mock_settings.density == "compact"
    assert mock_settings.minimize_to_tray is False
