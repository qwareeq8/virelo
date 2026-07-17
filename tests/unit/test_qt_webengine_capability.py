"""Tests for the fail-closed native Qt WebEngine capability probe."""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.probe_qt_webengine_capability import (
    EXIT_AVAILABLE,
    EXIT_INDETERMINATE,
    EXIT_UNAVAILABLE,
    REQUIRED_RECORD_ENTRIES,
    exit_code_for_status,
    probe_capability,
)

_ARM64_TAG = "cp310-abi3-win_arm64"
_FINGERPRINT = (
    "PySide6/QtWebChannel.pyd",
    "PySide6/Qt6WebChannel.dll",
    "PySide6/QtPdf.pyd",
    "PySide6/translations/qtwebengine_en.qm",
)


class _FakeDistribution:
    """Minimal installed-wheel metadata used by the capability tests."""

    def __init__(self, *, name: str, root: Path, files: set[str], tag: str = _ARM64_TAG):
        self.metadata = {"Name": name}
        self.version = "6.11.1"
        self.files = [PurePosixPath(path) for path in sorted(files)]
        self._root = root
        self._tag = tag

    def read_text(self, filename: str) -> str | None:
        if filename == "WHEEL":
            return f"Wheel-Version: 1.0\nTag: {self._tag}\n"
        return None

    def locate_file(self, path: str | PurePosixPath) -> Path:
        return self._root / str(path)


def _write_pe(path: Path, machine: int = 0xAA64) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray(0x86)
    payload[0:2] = b"MZ"
    payload[0x3C:0x40] = struct.pack("<I", 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    payload[0x84:0x86] = struct.pack("<H", machine)
    path.write_bytes(payload)


def _distribution_getter(
    tmp_path: Path,
    *,
    addons_files: set[str],
    addons_tag: str = _ARM64_TAG,
):
    distributions = {
        name: _FakeDistribution(
            name=name,
            root=tmp_path,
            files=addons_files if name == "PySide6_Addons" else {f"{name}.marker"},
            tag=addons_tag if name == "PySide6_Addons" else _ARM64_TAG,
        )
        for name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6")
    }
    return distributions.__getitem__


def _materialize(tmp_path: Path, entries: set[str], *, foreign: str | None = None) -> None:
    for entry in entries:
        path = tmp_path / entry
        if path.suffix.casefold() in {".dll", ".exe", ".pyd"}:
            _write_pe(path, machine=0x8664 if entry == foreign else 0xAA64)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")


def _passing_import_result(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    result: dict[str, object] = {
        "qtVersion": "6.11.1",
        "modules": {
            "PySide6.QtWebEngineCore": str((tmp_path / "PySide6/QtWebEngineCore.pyd").resolve()),
            "PySide6.QtWebEngineWidgets": str(
                (tmp_path / "PySide6/QtWebEngineWidgets.pyd").resolve()
            ),
        },
    }
    return result, {"name": "imports", "returnCode": 0, "result": result}


def test_exact_reviewed_arm64_record_omission_is_unavailable(tmp_path: Path) -> None:
    """Only the fingerprinted 6.11.1 ARM64 omission is a known upstream boundary."""
    addons_files = set(_FINGERPRINT)
    _materialize(tmp_path, addons_files)

    def unexpected_import() -> Any:
        raise AssertionError("The missing RECORD payload must short-circuit native imports.")

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
        import_runner=unexpected_import,
    )

    assert report["status"] == "unavailable"
    assert report["available"] is False
    assert report["reasonCode"] == "reviewed-pyside6-arm64-webengine-record-omission"
    assert report["errors"] == []
    assert exit_code_for_status(str(report["status"])) == EXIT_UNAVAILABLE


def test_partial_or_unfingerprinted_record_omission_is_indeterminate(tmp_path: Path) -> None:
    """A similar but unreviewed wheel cannot silently disable the native release job."""
    addons_files = set(_FINGERPRINT)
    addons_files.add(REQUIRED_RECORD_ENTRIES[0])
    _materialize(tmp_path, addons_files)

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
    )

    assert report["status"] == "indeterminate"
    assert "unreviewed Qt WebEngine omission" in str(report["errors"])
    assert exit_code_for_status(str(report["status"])) == EXIT_INDETERMINATE


def test_recorded_but_missing_payload_is_indeterminate(tmp_path: Path) -> None:
    """A damaged installation is not the reviewed upstream wheel omission."""
    addons_files = set(_FINGERPRINT) | set(REQUIRED_RECORD_ENTRIES)
    _materialize(tmp_path, addons_files - {REQUIRED_RECORD_ENTRIES[-1]})

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
    )

    assert report["status"] == "indeterminate"
    assert "missing on disk" in str(report["errors"])


def test_complete_native_arm64_payload_is_available(tmp_path: Path) -> None:
    """Complete imports and ARM64 PE evidence enable native packaging."""
    addons_files = set(_FINGERPRINT) | set(REQUIRED_RECORD_ENTRIES)
    _materialize(tmp_path, addons_files)

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
        import_runner=lambda: _passing_import_result(tmp_path),
    )

    assert report["status"] == "available"
    assert report["available"] is True
    assert report["reasonCode"] == "qt-webengine-capable"
    assert report["errors"] == []
    assert report["peArchitecture"]["status"] == "pass"  # type: ignore[index]
    assert exit_code_for_status(str(report["status"])) == EXIT_AVAILABLE


def test_foreign_webengine_pe_is_indeterminate(tmp_path: Path) -> None:
    """An x64 helper cannot make an ARM64 environment capability-positive."""
    addons_files = set(_FINGERPRINT) | set(REQUIRED_RECORD_ENTRIES)
    foreign = "PySide6/QtWebEngineProcess.exe"
    _materialize(tmp_path, addons_files, foreign=foreign)

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
        import_runner=lambda: _passing_import_result(tmp_path),
    )

    assert report["status"] == "indeterminate"
    assert report["available"] is False
    assert any("is x64" in error for error in report["errors"])


def test_import_failure_is_indeterminate(tmp_path: Path) -> None:
    """A listed payload with a broken native import remains a hard failure."""
    addons_files = set(_FINGERPRINT) | set(REQUIRED_RECORD_ENTRIES)
    _materialize(tmp_path, addons_files)

    report = probe_capability(
        architecture="arm64",
        distribution_getter=_distribution_getter(tmp_path, addons_files=addons_files),
        import_runner=lambda: (
            None,
            {"name": "imports", "returnCode": 1, "stderr": "DLL load failed"},
        ),
    )

    assert report["status"] == "indeterminate"
    assert "DLL load failed" in str(report["errors"])


def test_probe_help_works_in_isolated_mode() -> None:
    """The dependency-light entry point remains runnable before PySide is imported."""
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "scripts" / "probe_qt_webengine_capability.py"

    process = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr
    assert "usage:" in process.stdout
