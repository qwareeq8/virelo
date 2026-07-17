"""Tests for bridge JSON envelope structure (QUAL-03).

Tests the SettingsState methods that the bridge wraps in {ok, data/error}
payloads. Since VireloBridge requires PySide6/Qt, we test the underlying
SettingsState envelope semantics using the MockSettings fixture.
"""

import json
from types import SimpleNamespace

import pytest

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


@pytest.mark.requires_qt
def test_settings_signal_correlates_frontend_transaction_without_staging_metadata(
    settings_state,
):
    """Transaction metadata tags the echo but never enters SettingsState."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    bridge = VireloBridge(settings_state, SnapService(None))
    emitted = []
    bridge.settings_changed.connect(emitted.append)

    response = json.loads(bridge.save_settings('{"width_pct": 63}', "frontend-17"))

    assert response["ok"] is True
    assert json.loads(emitted[-1])["__vireloTransaction"] == "frontend-17"
    assert "__vireloTransaction" not in settings_state.get_all()


@pytest.mark.requires_qt
def test_commit_keeps_draft_when_new_hotkey_hooks_cannot_be_installed(settings_state) -> None:
    """Persistence cannot claim success while the active global hook stays stale."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    listener = SimpleNamespace(update_keys=lambda *_args: False)
    window = SimpleNamespace(
        _hotkey_listener=listener,
        settings=settings_state._settings,
    )
    bridge = VireloBridge(settings_state, SnapService(None))
    bridge.set_main_window(window)
    assert settings_state.apply_draft({"snap_key": "alt"})["ok"]

    result = json.loads(bridge.commit_draft("failed-hook"))

    assert result["ok"] is False
    assert settings_state.has_draft
    assert settings_state._settings.snap_key == "shift"
    assert settings_state.get_all()["snap_key"] == "alt"


@pytest.mark.requires_qt
def test_reset_keeps_persisted_values_when_default_hotkey_hooks_fail(settings_state) -> None:
    """A failed default hook installation aborts reset before persistence."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    settings_state._settings.snap_key = "alt"
    listener = SimpleNamespace(update_keys=lambda *_args: False)
    window = SimpleNamespace(
        _hotkey_listener=listener,
        settings=settings_state._settings,
    )
    bridge = VireloBridge(settings_state, SnapService(None))
    bridge.set_main_window(window)

    result = json.loads(bridge.reset_defaults("failed-reset-hook"))

    assert result["ok"] is False
    assert settings_state._settings.snap_key == "alt"


@pytest.mark.requires_qt
def test_commit_restores_old_hooks_when_persistence_fails(settings_state) -> None:
    """Preinstalled hooks roll back if QSettings cannot persist the matching values."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    calls = []

    def update_keys(snap_key, restore_key):
        calls.append((snap_key, restore_key))
        return True

    def fail_save():
        raise OSError("registry unavailable")

    settings_state._settings.save = fail_save
    window = SimpleNamespace(
        _hotkey_listener=SimpleNamespace(update_keys=update_keys),
        settings=settings_state._settings,
    )
    bridge = VireloBridge(settings_state, SnapService(None))
    bridge.set_main_window(window)
    assert settings_state.apply_draft({"snap_key": "alt"})["ok"]

    result = json.loads(bridge.commit_draft("persistence-failure"))

    assert result["ok"] is False
    assert calls == [("alt", "ctrl"), ("shift", "ctrl")]
    assert settings_state.has_draft


@pytest.mark.requires_qt
def test_commit_keeps_new_hooks_after_post_commit_side_effect_failure(settings_state) -> None:
    """A later runtime refresh cannot undo hooks for already-persisted settings."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    calls = []

    def update_keys(snap_key, restore_key):
        calls.append((snap_key, restore_key))
        return True

    window = SimpleNamespace(
        _hotkey_listener=SimpleNamespace(update_keys=update_keys),
        settings=settings_state._settings,
    )
    bridge = VireloBridge(settings_state, SnapService(None))
    bridge.set_main_window(window)
    bridge._apply_side_effects = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("runtime refresh failed")
    )
    assert settings_state.apply_draft({"snap_key": "alt"})["ok"]

    result = json.loads(bridge.commit_draft("post-commit-failure"))

    assert result["ok"] is True
    assert calls == [("alt", "ctrl")]
    assert not settings_state.has_draft
    assert settings_state._settings.snap_key == "alt"


@pytest.mark.requires_qt
def test_reset_keeps_default_hooks_after_post_reset_side_effect_failure(settings_state) -> None:
    """A later runtime refresh cannot undo hooks after defaults are persisted."""

    from virelo.bridge.bridge import VireloBridge
    from virelo.services.snap import SnapService

    calls = []

    def update_keys(snap_key, restore_key):
        calls.append((snap_key, restore_key))
        return True

    settings_state._settings.snap_key = "alt"
    settings_state._settings.save()
    window = SimpleNamespace(
        _hotkey_listener=SimpleNamespace(update_keys=update_keys),
        settings=settings_state._settings,
    )
    bridge = VireloBridge(settings_state, SnapService(None))
    bridge.set_main_window(window)
    bridge._apply_side_effects = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("runtime refresh failed")
    )

    result = json.loads(bridge.reset_defaults("post-reset-failure"))

    assert result["ok"] is True
    assert calls == [(DEFAULTS["snap_key"], DEFAULTS["restore_key"])]
    assert settings_state._settings.snap_key == DEFAULTS["snap_key"]
