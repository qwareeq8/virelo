"""Tests for the reviewed PySide6 ARM64 WebEngine wheel contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_arm64_webengine_contract import (
    DEFAULT_CONSTRAINTS_PATH,
    ContractError,
    contract_from_data,
    load_review_contract,
    verify_contract_files,
)


def _contract_data() -> dict[str, object]:
    """Return one mutable copy of the committed contract fixture."""
    contract_path = (
        Path(__file__).resolve().parents[2] / "requirements" / ("arm64-webengine-contract.json")
    )
    return json.loads(contract_path.read_text(encoding="utf-8"))


def test_committed_contract_matches_all_pyside_cohort_pins() -> None:
    """The reviewed wheel and all four release pins remain synchronized."""
    report = verify_contract_files()

    assert report["status"] == "pass"
    assert report["errors"] == []


def test_constraint_version_drift_fails_closed(tmp_path: Path) -> None:
    """One changed cohort pin invalidates the reviewed wheel contract."""
    constraints = DEFAULT_CONSTRAINTS_PATH.read_text(encoding="utf-8").replace(
        "PySide6-Addons==6.11.1",
        "PySide6-Addons==6.12.0",
    )
    constraints_path = tmp_path / "build-constraints.txt"
    constraints_path.write_text(constraints, encoding="utf-8")

    report = verify_contract_files(constraints_path=constraints_path)

    assert report["status"] == "fail"
    assert "PySide6-Addons must be pinned" in str(report["errors"])


def test_missing_cohort_pins_fail_closed(tmp_path: Path) -> None:
    """An empty constraints file cannot accidentally validate the trust anchor."""
    constraints_path = tmp_path / "build-constraints.txt"
    constraints_path.write_text("# No release pins.\n", encoding="utf-8")

    report = verify_contract_files(constraints_path=constraints_path)

    assert report["status"] == "fail"
    assert len(report["errors"]) == 4


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schemaVersion", 2, "schema must be 1"),
        ("schemaVersion", True, "schema must be 1"),
        ("sha256", "ABC", "64 lowercase hexadecimal digits"),
        ("wheelTag", "cp310-abi3-win_amd64", "Windows ARM64"),
    ],
)
def test_invalid_contract_fields_are_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    """Malformed trust anchors cannot enter the capability decision."""
    data = _contract_data()
    data[field] = value
    if field == "wheelTag":
        data["wheelFilename"] = f"pyside6_addons-6.11.1-{value}.whl"

    with pytest.raises(ContractError, match=message):
        contract_from_data(data)


def test_contract_loader_rejects_non_object_json(tmp_path: Path) -> None:
    """The contract loader requires exactly one JSON object."""
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ContractError, match="one JSON object"):
        load_review_contract(contract_path)


def test_contract_verifier_help_works_in_isolated_mode() -> None:
    """The dependency-free verifier runs before release packages are installed."""
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "scripts" / "verify_arm64_webengine_contract.py"

    process = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr
    assert "usage:" in process.stdout
