"""Verify the reviewed PySide6 ARM64 WebEngine wheel contract and dependency pins."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "requirements" / "arm64-webengine-contract.json"
DEFAULT_CONSTRAINTS_PATH = PROJECT_ROOT / "requirements" / "build-constraints.txt"

_CONTRACT_KEYS = {
    "schemaVersion",
    "distribution",
    "reviewedVersion",
    "wheelFilename",
    "wheelTag",
    "sha256",
    "expectedStatus",
    "expectedReasonCode",
    "omissionFingerprint",
}
_PYSIDE_COHORT = ("PySide6", "PySide6-Addons", "PySide6-Essentials", "shiboken6")
_EXPECTED_REASONS = {
    "available": "qt-webengine-capable",
    "unavailable": "reviewed-pyside6-arm64-webengine-record-omission",
}
_EXACT_PIN = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;#]+)\s*(?:#.*)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_TAG = re.compile(r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-win_arm64$")


class ContractError(ValueError):
    """Report an invalid reviewed-wheel contract."""


@dataclass(frozen=True)
class Arm64WebEngineContract:
    """Identify one reviewed official PySide6-Addons ARM64 wheel."""

    schema_version: int
    distribution: str
    reviewed_version: str
    wheel_filename: str
    wheel_tag: str
    sha256: str
    expected_status: str
    expected_reason_code: str
    omission_fingerprint: tuple[str, ...]


def normalize_distribution_name(value: str) -> str:
    """Return the comparison form defined by Python package name normalization."""
    return re.sub(r"[-_.]+", "", value).casefold()


def _require_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ContractError(f"The ARM64 WebEngine contract field {key!r} must be a string.")
    return value


def contract_from_data(data: Mapping[str, Any]) -> Arm64WebEngineContract:
    """Validate contract JSON data and return its typed representation."""
    keys = set(data)
    if keys != _CONTRACT_KEYS:
        missing = sorted(_CONTRACT_KEYS - keys)
        unexpected = sorted(keys - _CONTRACT_KEYS)
        raise ContractError(
            "The ARM64 WebEngine contract fields do not match schema 1; "
            f"missing={missing}, unexpected={unexpected}."
        )
    if type(data.get("schemaVersion")) is not int or data["schemaVersion"] != SCHEMA_VERSION:
        raise ContractError(f"The ARM64 WebEngine contract schema must be {SCHEMA_VERSION}.")

    distribution = _require_string(data, "distribution")
    if normalize_distribution_name(distribution) != "pyside6addons":
        raise ContractError("The reviewed distribution must be PySide6-Addons.")

    reviewed_version = _require_string(data, "reviewedVersion")
    wheel_filename = _require_string(data, "wheelFilename")
    wheel_tag = _require_string(data, "wheelTag")
    expected_filename = f"pyside6_addons-{reviewed_version}-{wheel_tag}.whl"
    if wheel_filename != expected_filename:
        raise ContractError(
            f"The reviewed wheel filename must be {expected_filename!r}, not {wheel_filename!r}."
        )
    if not _WHEEL_TAG.fullmatch(wheel_tag):
        raise ContractError(f"The reviewed wheel tag is not Windows ARM64: {wheel_tag!r}.")

    sha256 = _require_string(data, "sha256")
    if not _SHA256.fullmatch(sha256):
        raise ContractError("The reviewed wheel SHA-256 must be 64 lowercase hexadecimal digits.")

    expected_status = _require_string(data, "expectedStatus")
    expected_reason_code = _require_string(data, "expectedReasonCode")
    if expected_status not in _EXPECTED_REASONS:
        raise ContractError("The reviewed capability status must be 'available' or 'unavailable'.")
    if expected_reason_code != _EXPECTED_REASONS[expected_status]:
        raise ContractError(
            f"The expected reason code for {expected_status!r} must be "
            f"{_EXPECTED_REASONS[expected_status]!r}."
        )

    fingerprint_value = data.get("omissionFingerprint")
    if not isinstance(fingerprint_value, list) or not fingerprint_value:
        raise ContractError("The reviewed omission fingerprint must be a nonempty list.")
    fingerprint: list[str] = []
    for entry in fingerprint_value:
        if (
            not isinstance(entry, str)
            or not entry.startswith("PySide6/")
            or "\\" in entry
            or ".." in Path(entry).parts
        ):
            raise ContractError(f"The reviewed omission fingerprint path is invalid: {entry!r}.")
        fingerprint.append(entry)
    if len(set(fingerprint)) != len(fingerprint):
        raise ContractError("The reviewed omission fingerprint contains duplicate paths.")

    return Arm64WebEngineContract(
        schema_version=SCHEMA_VERSION,
        distribution=distribution,
        reviewed_version=reviewed_version,
        wheel_filename=wheel_filename,
        wheel_tag=wheel_tag,
        sha256=sha256,
        expected_status=expected_status,
        expected_reason_code=expected_reason_code,
        omission_fingerprint=tuple(fingerprint),
    )


def load_review_contract(path: Path = DEFAULT_CONTRACT_PATH) -> Arm64WebEngineContract:
    """Load and validate the reviewed ARM64 WebEngine wheel contract."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(
            f"Could not read the ARM64 WebEngine contract {path}: {error}."
        ) from error
    if not isinstance(data, dict):
        raise ContractError("The ARM64 WebEngine contract must contain one JSON object.")
    return contract_from_data(data)


def _constraint_versions(path: Path) -> dict[str, str]:
    """Return normalized exact pins from the release constraints file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ContractError(f"Could not read the Python constraints {path}: {error}.") from error

    versions: dict[str, str] = {}
    for line in lines:
        match = _EXACT_PIN.fullmatch(line)
        if match is None:
            continue
        name, version = match.groups()
        normalized = normalize_distribution_name(name)
        if normalized in versions:
            raise ContractError(f"The Python constraints contain a duplicate exact pin for {name}.")
        versions[normalized] = version
    return versions


def verify_contract_files(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    constraints_path: Path = DEFAULT_CONSTRAINTS_PATH,
) -> dict[str, object]:
    """Return fail-closed evidence for the contract and synchronized package pins."""
    errors: list[str] = []
    contract: Arm64WebEngineContract | None = None
    versions: dict[str, str] = {}
    try:
        contract = load_review_contract(contract_path)
    except ContractError as error:
        errors.append(str(error))
    try:
        versions = _constraint_versions(constraints_path)
    except ContractError as error:
        errors.append(str(error))

    if contract is not None:
        for distribution in _PYSIDE_COHORT:
            normalized = normalize_distribution_name(distribution)
            actual = versions.get(normalized)
            if actual != contract.reviewed_version:
                errors.append(
                    f"{distribution} must be pinned to reviewed version "
                    f"{contract.reviewed_version}; found {actual!r}."
                )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "pass" if not errors else "fail",
        "contractPath": str(contract_path.resolve()),
        "constraintsPath": str(constraints_path.resolve()),
        "contract": (
            {
                "schemaVersion": contract.schema_version,
                "distribution": contract.distribution,
                "reviewedVersion": contract.reviewed_version,
                "wheelFilename": contract.wheel_filename,
                "wheelTag": contract.wheel_tag,
                "sha256": contract.sha256,
                "expectedStatus": contract.expected_status,
                "expectedReasonCode": contract.expected_reason_code,
                "omissionFingerprint": list(contract.omission_fingerprint),
            }
            if contract is not None
            else None
        ),
        "constraintVersions": versions,
        "errors": errors,
    }


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    """Write one JSON report atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--constraints", type=Path, default=DEFAULT_CONSTRAINTS_PATH)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify the reviewed contract and exact PySide6 cohort pins."""
    args = build_parser().parse_args(argv)
    report = verify_contract_files(args.contract, args.constraints)
    if args.report is not None:
        _write_report(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
