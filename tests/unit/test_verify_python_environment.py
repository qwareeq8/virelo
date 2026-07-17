"""Tests for architecture-aware Python environment checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import cast

from scripts.verify_python_environment import (
    _run_json_child,
    conda_status,
    find_external_critical_dlls,
    find_python_dlls,
    parse_wheel_tags,
    python_version_is_supported,
    wheel_tags_match_architecture,
)


def test_python_release_version_boundary() -> None:
    assert not python_version_is_supported((3, 11, 9))
    assert python_version_is_supported((3, 12, 0))
    assert python_version_is_supported((3, 13, 1))


def test_isolated_import_child_has_a_hard_timeout(monkeypatch) -> None:
    """A hung native import cannot block the release preflight indefinitely."""

    def time_out(*_args, **kwargs):
        raise subprocess.TimeoutExpired(kwargs.get("args", "python"), kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", time_out)

    payload, details = _run_json_child("hung Qt import", "pass")

    assert payload is None
    assert details["timedOut"] is True
    assert details["timeoutSeconds"] == 60


def test_wheel_tags_must_match_the_requested_windows_architecture() -> None:
    tags = parse_wheel_tags(
        "Wheel-Version: 1.0\nTag: cp310-abi3-win_arm64\nTag: cp311-abi3-win_arm64\n"
    )

    assert wheel_tags_match_architecture(tags, "arm64")
    assert not wheel_tags_match_architecture(tags, "x64")
    assert not wheel_tags_match_architecture(["py3-none-any"], "arm64")


def test_ambient_conda_tools_do_not_make_official_python_conda(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "venv-x64"
    base_prefix = tmp_path / "Python312"
    prefix.mkdir()
    base_prefix.mkdir()

    status = conda_status(
        prefix=prefix,
        base_prefix=base_prefix,
        version="3.12.10 (tags/v3.12.10:example) [MSC v.1942 64 bit (AMD64)]",
        environ={"CONDA_EXE": r"C:\Tools\Miniconda3\Scripts\conda.exe"},
    )

    assert status["active"] is False
    assert status["ambientVariables"] == {"CONDA_EXE": r"C:\Tools\Miniconda3\Scripts\conda.exe"}


def test_conda_meta_marks_the_base_interpreter_as_conda(tmp_path: Path) -> None:
    prefix = tmp_path / "venv-arm64"
    base_prefix = tmp_path / "miniforge"
    prefix.mkdir()
    (base_prefix / "conda-meta").mkdir(parents=True)

    status = conda_status(
        prefix=prefix,
        base_prefix=base_prefix,
        version="3.12.12",
        environ={},
    )

    assert status["active"] is True
    assert any("conda-meta" in evidence for evidence in cast(list[str], status["evidence"]))


def test_find_python_dlls_uses_selected_prefixes(tmp_path: Path) -> None:
    base = tmp_path / "Python312"
    expected = base / "python312.dll"
    expected.parent.mkdir()
    expected.write_bytes(b"placeholder")

    result = find_python_dlls([base], major=3, minor=12)

    assert result == [expected.resolve()]


def test_external_runtime_candidates_are_detected_outside_allowed_roots(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "Python312"
    external = tmp_path / "qemu"
    allowed.mkdir()
    external.mkdir()
    (allowed / "libssl-3-x64.dll").write_bytes(b"reviewed")
    leaked = external / "libssl-3-x64.dll"
    leaked.write_bytes(b"unreviewed")

    result = find_external_critical_dlls(
        os.pathsep.join((str(allowed), str(external))),
        allowed_roots=[allowed],
    )

    assert result == [leaked.resolve()]
