"""Tests for the non-mutating PySide6 ARM64 upstream watcher."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.probe_qt_webengine_capability import REQUIRED_RECORD_ENTRIES
from scripts.verify_arm64_webengine_contract import load_review_contract
from scripts.watch_pyside6_arm64 import (
    EXIT_CURRENT,
    EXIT_INDETERMINATE,
    EXIT_REVIEW_NEEDED,
    exit_code_for_status,
    inspect_upstream,
)

_COHORT = ("PySide6", "PySide6-Addons", "PySide6-Essentials", "shiboken6")
_OFFICIAL_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/test/pyside6_addons-6.12.0-cp310-abi3-win_arm64.whl"
)


def _wheel_bytes(entries: tuple[str, ...]) -> bytes:
    """Build a minimal in-memory wheel ZIP with the requested filenames."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in entries:
            archive.writestr(entry, b"fixture")
    return output.getvalue()


def _metadata(
    *,
    versions: Mapping[str, str],
    wheel_version: str,
    wheel_payload: bytes,
    wheel_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return fake PyPI project documents for the four-package cohort."""
    filename = f"pyside6_addons-{wheel_version}-cp310-abi3-win_arm64.whl"
    wheel = {
        "filename": filename,
        "url": _OFFICIAL_WHEEL_URL.replace("6.12.0", wheel_version),
        "size": len(wheel_payload),
        "digests": {"sha256": wheel_sha256 or hashlib.sha256(wheel_payload).hexdigest()},
        "packagetype": "bdist_wheel",
        "yanked": False,
    }
    return {
        distribution: {
            "info": {"version": versions[distribution]},
            "urls": [wheel] if distribution == "PySide6-Addons" else [],
        }
        for distribution in _COHORT
    }


def test_reviewed_pypi_head_does_not_download_the_wheel() -> None:
    """An unchanged official head validates metadata and performs no wheel download."""
    contract = load_review_contract()
    versions = dict.fromkeys(_COHORT, contract.reviewed_version)
    payload = _wheel_bytes(("fixture",))
    metadata = _metadata(
        versions=versions,
        wheel_version=contract.reviewed_version,
        wheel_payload=payload,
        wheel_sha256=contract.sha256,
    )
    metadata["PySide6-Addons"]["urls"][0]["filename"] = contract.wheel_filename

    def unexpected_download(_url: str, _limit: int) -> bytes:
        raise AssertionError("The reviewed PyPI head must not be downloaded again.")

    report = inspect_upstream(
        contract,
        fetch_json=metadata.__getitem__,
        fetch_bytes=unexpected_download,
    )

    assert report["status"] == "current"
    assert report["candidate"] is None
    assert report["errors"] == []
    assert exit_code_for_status(str(report["status"])) == EXIT_CURRENT


def test_new_wheel_is_hashed_and_inventory_requires_human_review() -> None:
    """A new cohort head produces evidence and deliberately fails for review."""
    contract = load_review_contract()
    versions = dict.fromkeys(_COHORT, "6.12.0")
    payload = _wheel_bytes(REQUIRED_RECORD_ENTRIES)
    metadata = _metadata(
        versions=versions,
        wheel_version="6.12.0",
        wheel_payload=payload,
    )

    report = inspect_upstream(
        contract,
        fetch_json=metadata.__getitem__,
        fetch_bytes=lambda _url, _limit: payload,
    )

    candidate = report["candidate"]
    assert report["status"] == "review-needed"
    assert isinstance(candidate, dict)
    assert candidate["completeRequiredPayload"] is True
    assert candidate["computedSha256"] == hashlib.sha256(payload).hexdigest()
    assert candidate["zipEntryCount"] == len(REQUIRED_RECORD_ENTRIES)
    assert exit_code_for_status(str(report["status"])) == EXIT_REVIEW_NEEDED


def test_candidate_hash_mismatch_is_indeterminate() -> None:
    """Downloaded bytes must match the digest published in official metadata."""
    contract = load_review_contract()
    versions = dict.fromkeys(_COHORT, "6.12.0")
    payload = _wheel_bytes(("PySide6/QtWebEngineCore.pyd",))
    metadata = _metadata(
        versions=versions,
        wheel_version="6.12.0",
        wheel_payload=payload,
        wheel_sha256="0" * 64,
    )

    report = inspect_upstream(
        contract,
        fetch_json=metadata.__getitem__,
        fetch_bytes=lambda _url, _limit: payload,
    )

    assert report["status"] == "indeterminate"
    assert "SHA-256" in str(report["errors"])
    assert exit_code_for_status(str(report["status"])) == EXIT_INDETERMINATE


def test_watcher_help_works_in_isolated_mode() -> None:
    """The watcher requires only the standard library and repository scripts."""
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "scripts" / "watch_pyside6_arm64.py"

    process = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr
    assert "usage:" in process.stdout
