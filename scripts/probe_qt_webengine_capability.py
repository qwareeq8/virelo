"""Probe whether an installed PySide6 environment can supply native Qt WebEngine."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

if __package__:
    from .pe_arch import normalize_architecture, verify_pe_paths
    from .verify_arm64_webengine_contract import (
        Arm64WebEngineContract,
        ContractError,
        load_review_contract,
    )
    from .verify_python_environment import (
        _run_json_child,
        parse_wheel_tags,
        wheel_tags_match_architecture,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pe_arch import normalize_architecture, verify_pe_paths
    from verify_arm64_webengine_contract import (  # type: ignore[no-redef]
        Arm64WebEngineContract,
        ContractError,
        load_review_contract,
    )
    from verify_python_environment import (  # type: ignore[no-redef]
        _run_json_child,
        parse_wheel_tags,
        wheel_tags_match_architecture,
    )

SCHEMA_VERSION = 1
EXIT_AVAILABLE = 0
EXIT_INDETERMINATE = 1
EXIT_UNAVAILABLE = 2

_PYSIDE_DISTRIBUTIONS = (
    "PySide6",
    "PySide6_Essentials",
    "PySide6_Addons",
    "shiboken6",
)

# These files are the minimum WebEngine payload used by Virelo's source import,
# PyInstaller collection, frozen deployment verification, and smoke test.
REQUIRED_RECORD_ENTRIES = (
    "PySide6/QtWebEngineCore.pyd",
    "PySide6/QtWebEngineWidgets.pyd",
    "PySide6/Qt6WebEngineCore.dll",
    "PySide6/Qt6WebEngineWidgets.dll",
    "PySide6/QtWebEngineProcess.exe",
    "PySide6/resources/qtwebengine_devtools_resources.pak",
    "PySide6/resources/qtwebengine_resources.pak",
    "PySide6/resources/qtwebengine_resources_100p.pak",
    "PySide6/resources/qtwebengine_resources_200p.pak",
    "PySide6/translations/qtwebengine_locales/en-US.pak",
)

_PE_RECORD_ENTRIES = (
    "PySide6/QtWebEngineCore.pyd",
    "PySide6/QtWebEngineWidgets.pyd",
    "PySide6/Qt6WebEngineCore.dll",
    "PySide6/Qt6WebEngineWidgets.dll",
    "PySide6/QtWebEngineProcess.exe",
)

_QT_IMPORT_SCRIPT = r"""
import json
from pathlib import Path

from PySide6 import QtCore, QtWebChannel, QtWebEngineCore, QtWebEngineWidgets, QtWidgets

modules = (QtCore, QtWebChannel, QtWebEngineCore, QtWebEngineWidgets, QtWidgets)
print(json.dumps({
    "qtVersion": QtCore.qVersion(),
    "modules": {module.__name__: str(Path(module.__file__).resolve()) for module in modules},
}))
"""

DistributionGetter = Callable[[str], Any]
ImportRunner = Callable[[], tuple[dict[str, object] | None, dict[str, object]]]


def _normalized_record(distribution: Any) -> set[str]:
    """Return normalized forward-slash paths from one installed wheel RECORD."""
    files = distribution.files
    if files is None:
        raise ValueError(
            f"{distribution.metadata.get('Name', 'The distribution')} has no installed RECORD."
        )
    return {str(path).replace("\\", "/") for path in files}


def _distribution_evidence(
    name: str,
    architecture: str,
    distribution_getter: DistributionGetter,
) -> tuple[Any, dict[str, object], set[str]]:
    """Collect installed version, wheel-tag, location, and RECORD evidence."""
    distribution = distribution_getter(name)
    wheel_text = distribution.read_text("WHEEL") or ""
    tags = parse_wheel_tags(wheel_text)
    record = _normalized_record(distribution)
    evidence: dict[str, object] = {
        "name": distribution.metadata.get("Name", name),
        "version": distribution.version,
        "tags": tags,
        "matchesArchitecture": wheel_tags_match_architecture(tags, architecture),
        "location": str(Path(distribution.locate_file("")).resolve()),
        "recordEntryCount": len(record),
    }
    return distribution, evidence, record


def _run_import_child() -> tuple[dict[str, object] | None, dict[str, object]]:
    """Import Qt WebEngine in an isolated child with the shared hard timeout."""
    return _run_json_child("PySide6 and Qt WebEngine capability imports", _QT_IMPORT_SCRIPT)


def _base_report(architecture: str) -> dict[str, object]:
    """Create the stable top-level report shape for every probe outcome."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "requestedArchitecture": architecture,
        "status": "indeterminate",
        "available": False,
        "reasonCode": "indeterminate-environment",
        "distributions": [],
        "requiredRecordEntries": [],
        "isolatedImport": None,
        "peArchitecture": None,
        "reviewedContract": None,
        "errors": [],
    }


def _entry_evidence(distribution: Any, record: set[str]) -> list[dict[str, object]]:
    """Describe whether every required payload entry is listed and installed."""
    evidence: list[dict[str, object]] = []
    for entry in REQUIRED_RECORD_ENTRIES:
        path = Path(distribution.locate_file(entry)).resolve()
        evidence.append(
            {
                "entry": entry,
                "listed": entry in record,
                "path": str(path),
                "exists": path.is_file(),
            }
        )
    return evidence


def _is_reviewed_arm64_omission(
    *,
    architecture: str,
    version: str,
    tags: Sequence[str],
    record: set[str],
    distribution: Any,
    contract: Arm64WebEngineContract,
) -> bool:
    """Return whether RECORD exactly matches the reviewed ARM64 wheel omission."""
    fingerprint_paths = [
        Path(distribution.locate_file(entry)) for entry in contract.omission_fingerprint
    ]
    return (
        architecture == "arm64"
        and contract.expected_status == "unavailable"
        and version == contract.reviewed_version
        and tuple(tags) == (contract.wheel_tag,)
        and all(entry not in record for entry in REQUIRED_RECORD_ENTRIES)
        and all(entry in record for entry in contract.omission_fingerprint)
        and all(path.is_file() for path in fingerprint_paths)
    )


def probe_capability(
    *,
    architecture: str,
    distribution_getter: DistributionGetter = importlib.metadata.distribution,
    import_runner: ImportRunner = _run_import_child,
    review_contract: Arm64WebEngineContract | None = None,
) -> dict[str, object]:
    """Return evidence for native Qt WebEngine availability in this environment."""
    expected = normalize_architecture(architecture)
    report = _base_report(expected)
    errors = cast(list[str], report["errors"])
    distributions = cast(list[dict[str, object]], report["distributions"])
    installed: dict[str, tuple[Any, dict[str, object], set[str]]] = {}

    if expected == "arm64":
        try:
            review_contract = review_contract or load_review_contract()
        except ContractError as error:
            errors.append(str(error))
            return report
        report["reviewedContract"] = {
            "distribution": review_contract.distribution,
            "reviewedVersion": review_contract.reviewed_version,
            "wheelFilename": review_contract.wheel_filename,
            "wheelTag": review_contract.wheel_tag,
            "sha256": review_contract.sha256,
            "expectedStatus": review_contract.expected_status,
            "expectedReasonCode": review_contract.expected_reason_code,
        }

    for name in _PYSIDE_DISTRIBUTIONS:
        try:
            distribution, evidence, record = _distribution_evidence(
                name,
                expected,
                distribution_getter,
            )
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Required capability distribution is not installed: {name}.")
            continue
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        distributions.append(evidence)
        installed[name] = (distribution, evidence, record)
        if not evidence["matchesArchitecture"]:
            errors.append(
                f"{evidence['name']} {evidence['version']} has incompatible wheel tags: "
                f"{evidence['tags']}."
            )

    if errors or len(installed) != len(_PYSIDE_DISTRIBUTIONS):
        return report

    versions = {str(evidence["version"]) for _, evidence, _ in installed.values()}
    if len(versions) != 1:
        errors.append("The installed PySide6 and Shiboken distributions do not share one version.")
        return report
    installed_version = next(iter(versions))
    if review_contract is not None and installed_version != review_contract.reviewed_version:
        errors.append(
            f"The installed PySide6 cohort is {installed_version}; the reviewed ARM64 wheel "
            f"contract is {review_contract.reviewed_version}."
        )
        return report

    addons, addons_evidence, addons_record = installed["PySide6_Addons"]
    if review_contract is not None and tuple(cast(list[str], addons_evidence["tags"])) != (
        review_contract.wheel_tag,
    ):
        errors.append(
            "The installed PySide6-Addons wheel tags do not match the reviewed ARM64 wheel "
            f"contract: {addons_evidence['tags']}."
        )
        return report
    entry_evidence = _entry_evidence(addons, addons_record)
    report["requiredRecordEntries"] = entry_evidence
    missing_record = [
        cast(str, entry["entry"]) for entry in entry_evidence if not cast(bool, entry["listed"])
    ]

    if missing_record:
        if review_contract is not None and _is_reviewed_arm64_omission(
            architecture=expected,
            version=str(addons_evidence["version"]),
            tags=cast(list[str], addons_evidence["tags"]),
            record=addons_record,
            distribution=addons,
            contract=review_contract,
        ):
            report["status"] = "unavailable"
            report["reasonCode"] = "reviewed-pyside6-arm64-webengine-record-omission"
            return report
        errors.append(
            "PySide6-Addons RECORD has an unreviewed Qt WebEngine omission: "
            + ", ".join(missing_record)
            + "."
        )
        return report

    missing_files = [
        cast(str, entry["entry"]) for entry in entry_evidence if not cast(bool, entry["exists"])
    ]
    if missing_files:
        errors.append(
            "PySide6-Addons RECORD lists Qt WebEngine files that are missing on disk: "
            + ", ".join(missing_files)
            + "."
        )
        return report

    import_result, import_details = import_runner()
    report["isolatedImport"] = import_details
    if import_result is None:
        diagnostics = (
            import_details.get("stderr")
            or import_details.get("parseError")
            or "No diagnostics were produced."
        )
        errors.append(f"The isolated Qt WebEngine import failed: {diagnostics}")
        return report

    modules = cast(Mapping[str, str], import_result.get("modules", {}))
    expected_modules = {
        "PySide6.QtWebEngineCore": Path(
            addons.locate_file("PySide6/QtWebEngineCore.pyd")
        ).resolve(),
        "PySide6.QtWebEngineWidgets": Path(
            addons.locate_file("PySide6/QtWebEngineWidgets.pyd")
        ).resolve(),
    }
    for module_name, expected_path in expected_modules.items():
        actual = modules.get(module_name)
        if actual is None or Path(actual).resolve() != expected_path:
            errors.append(
                f"{module_name} resolved to {actual!r}; expected the selected wheel path "
                f"{expected_path}."
            )
    if errors:
        return report

    pe_paths = [Path(addons.locate_file(entry)).resolve() for entry in _PE_RECORD_ENTRIES]
    pe_report = verify_pe_paths(pe_paths, expected=expected, recursive=False)
    report["peArchitecture"] = pe_report
    pe_errors = cast(list[str], pe_report["errors"])
    if pe_errors:
        errors.extend(pe_errors)
        return report

    report["status"] = "available"
    report["available"] = True
    report["reasonCode"] = "qt-webengine-capable"
    return report


def exit_code_for_status(status: str) -> int:
    """Map a capability outcome to its stable process exit code."""
    if status == "available":
        return EXIT_AVAILABLE
    if status == "unavailable":
        return EXIT_UNAVAILABLE
    return EXIT_INDETERMINATE


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    """Write capability evidence atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", required=True, choices=("x64", "arm64"))
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Qt WebEngine capability probe."""
    args = build_parser().parse_args(argv)
    report = probe_capability(architecture=args.architecture)
    _write_report(args.report, report)
    print(json.dumps(report, indent=2))
    return exit_code_for_status(cast(str, report["status"]))


if __name__ == "__main__":
    sys.exit(main())
