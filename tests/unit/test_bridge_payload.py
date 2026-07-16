"""Tests for bridge JSON envelope structure (QUAL-03).

Tests the SettingsState methods that the bridge wraps in {ok, data/error}
payloads. Since VireloBridge requires PySide6/Qt, we test the underlying
SettingsState envelope semantics using the MockSettings fixture.
"""

from virelo.app.config import DEFAULTS


def test_get_settings_returns_ok_envelope(settings_state):
    """get_all() returns a dict with all expected keys."""
    result = settings_state.get_all()
    assert isinstance(result, dict)
    assert "snap_key" in result
    assert "width_pct" in result


def test_apply_draft_error_envelope(settings_state):
    """apply_draft returns {ok: False, error: ...} for unknown keys."""
    result = settings_state.apply_draft({"nonexistent": "val"})
    assert result["ok"] is False
    assert "error" in result


def test_apply_draft_success_envelope(settings_state):
    """apply_draft returns {ok: True, applied: {...}} for valid input."""
    result = settings_state.apply_draft({"width_pct": 50})
    assert result["ok"] is True
    assert "applied" in result
    assert result["applied"]["width_pct"] == 50


def test_commit_draft_envelope(settings_state):
    """commit_draft returns {ok: True, ...} after successful draft."""
    settings_state.apply_draft({"width_pct": 50})
    result = settings_state.commit_draft()
    assert result["ok"] is True


def test_reset_defaults_envelope(settings_state):
    """reset_to_defaults returns dict with all default keys."""
    result = settings_state.reset_to_defaults()
    for key in DEFAULTS:
        assert key in result, f"Missing key after reset: {key}"


def test_commit_empty_draft_envelope(settings_state):
    """commit_draft with no pending draft returns {ok: True, applied: {}}."""
    result = settings_state.commit_draft()
    assert result["ok"] is True
    assert result["applied"] == {}
