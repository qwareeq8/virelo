"""Tests for the autosize engine's idle poll backoff."""

from virelo.workers.explorer import ExplorerAutosizeEngine


def _make_engine(tabs_fn):
    return ExplorerAutosizeEngine(
        tabs_fn,
        lambda hwnd, target_path: (True, "com", False),
        lambda hwnd, target_path: (True, "com", False),
        lambda hwnd: True,
    )


def test_idle_backoff_decays_without_activity():
    """With a stable (empty) window set, the poll interval decays to 1 second."""
    engine = _make_engine(lambda: [])
    t = 1000.0
    fast = engine.step(t)
    assert fast <= 0.2
    settled = engine.step(t + 10.0)
    assert settled == 0.5
    idle = engine.step(t + 60.0)
    assert idle == 1.0


def test_activity_resets_backoff():
    """A window-set change restores the fast poll interval."""
    tabs = []
    engine = _make_engine(lambda: list(tabs))
    t = 1000.0
    engine.step(t)
    assert engine.step(t + 60.0) == 1.0

    tabs.append((12345, 1, r"C:\somewhere", 4))
    delay = engine.step(t + 61.0)
    assert delay <= 0.2
