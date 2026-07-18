"""Policy tests for the isolated ARM64 upstream-watch workflow."""

from __future__ import annotations

import re
from pathlib import Path


def test_upstream_watch_is_scheduled_manual_and_read_only() -> None:
    """The advisory watcher has no broad event or repository-write authority."""
    repository_root = Path(__file__).resolve().parents[2]
    workflow = (repository_root / ".github" / "workflows" / "arm64-upstream-watch.yml").read_text(
        encoding="utf-8"
    )

    assert "  schedule:\n" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "  push:\n" not in workflow
    assert "  pull_request:\n" not in workflow
    assert "permissions:\n  contents: read\n" in workflow
    permissions_block = workflow.split("permissions:\n", maxsplit=1)[1].split(
        "\n\n",
        maxsplit=1,
    )[0]
    assert permissions_block == "  contents: read"


def test_every_upstream_watch_action_is_pinned_by_full_digest() -> None:
    """Every third-party workflow action is immutable under repository policy."""
    repository_root = Path(__file__).resolve().parents[2]
    workflow = (repository_root / ".github" / "workflows" / "arm64-upstream-watch.yml").read_text(
        encoding="utf-8"
    )
    action_references = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", workflow, re.MULTILINE)

    assert action_references
    for reference in action_references:
        _action, separator, revision = reference.partition("@")
        assert separator == "@"
        assert re.fullmatch(r"[0-9a-f]{40}", revision)


def test_upstream_watch_cannot_mutate_release_inputs_or_matrix() -> None:
    """The watcher only invokes read-only verifier and inventory scripts."""
    repository_root = Path(__file__).resolve().parents[2]
    workflow = (repository_root / ".github" / "workflows" / "arm64-upstream-watch.yml").read_text(
        encoding="utf-8"
    )

    assert "watch_pyside6_arm64.py" in workflow
    assert "pip install" not in workflow
    assert "git push" not in workflow
    assert "package-matrix" not in workflow
