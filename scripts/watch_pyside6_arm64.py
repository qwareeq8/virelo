"""Watch official PyPI for a new PySide6 ARM64 WebEngine wheel candidate."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

if __package__:
    from .probe_qt_webengine_capability import REQUIRED_RECORD_ENTRIES
    from .verify_arm64_webengine_contract import (
        Arm64WebEngineContract,
        ContractError,
        load_review_contract,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from probe_qt_webengine_capability import (  # type: ignore[no-redef]
        REQUIRED_RECORD_ENTRIES,
    )
    from verify_arm64_webengine_contract import (  # type: ignore[no-redef]
        Arm64WebEngineContract,
        ContractError,
        load_review_contract,
    )

SCHEMA_VERSION = 1
EXIT_CURRENT = 0
EXIT_INDETERMINATE = 1
EXIT_REVIEW_NEEDED = 2

_PYPI_API_ROOT = "https://pypi.org/pypi"
_PYPI_HOST = "pypi.org"
_FILES_HOST = "files.pythonhosted.org"
_PYSIDE_COHORT = ("PySide6", "PySide6-Addons", "PySide6-Essentials", "shiboken6")
_MAX_METADATA_BYTES = 5 * 1024 * 1024
_MAX_WHEEL_BYTES = 250 * 1024 * 1024
_MAX_RECORD_ENTRIES = 100_000
_NETWORK_TIMEOUT_SECONDS = 30
_USER_AGENT = "Virelo-ARM64-upstream-watch/1"

JsonFetcher = Callable[[str], Mapping[str, Any]]
BytesFetcher = Callable[[str, int], bytes]


class WatchError(RuntimeError):
    """Report an untrusted or indeterminate upstream response."""


def _read_official_url(url: str, *, expected_host: str, limit: int) -> bytes:
    """Read a bounded HTTPS response from one exact official PyPI host."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        raise WatchError(f"Refusing nonofficial URL: {url!r}.")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.hostname != expected_host:
                raise WatchError(f"Refusing redirected nonofficial URL: {final_url!r}.")
            length_header = response.headers.get("Content-Length")
            if length_header is not None and int(length_header) > limit:
                raise WatchError(f"Official response exceeds the {limit}-byte limit: {url}.")
            payload = response.read(limit + 1)
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise WatchError(f"Could not read {url}: {error}.") from error
    if len(payload) > limit:
        raise WatchError(f"Official response exceeds the {limit}-byte limit: {url}.")
    return payload


def _fetch_project_json(distribution: str) -> Mapping[str, Any]:
    """Fetch one bounded official PyPI project document."""
    quoted = urllib.parse.quote(distribution, safe="")
    url = f"{_PYPI_API_ROOT}/{quoted}/json"
    payload = _read_official_url(url, expected_host=_PYPI_HOST, limit=_MAX_METADATA_BYTES)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise WatchError(f"PyPI returned invalid JSON for {distribution}: {error}.") from error
    if not isinstance(value, dict):
        raise WatchError(f"PyPI returned a non-object document for {distribution}.")
    return value


def _fetch_wheel(url: str, limit: int) -> bytes:
    """Fetch one bounded official wheel without installing or extracting it."""
    return _read_official_url(url, expected_host=_FILES_HOST, limit=limit)


def _project_version(metadata: Mapping[str, Any], distribution: str) -> str:
    """Return the validated latest version from one PyPI project document."""
    info = metadata.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("version"), str):
        raise WatchError(f"PyPI metadata for {distribution} has no latest version.")
    version = cast(str, info["version"])
    if not version:
        raise WatchError(f"PyPI metadata for {distribution} has an empty latest version.")
    return version


def _arm64_addons_wheels(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return non-yanked ARM64 wheels from the latest Addons release metadata."""
    urls = metadata.get("urls")
    if not isinstance(urls, list):
        raise WatchError("PyPI metadata for PySide6-Addons has no release file list.")
    candidates: list[dict[str, Any]] = []
    for item in urls:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if (
            item.get("packagetype") == "bdist_wheel"
            and item.get("yanked") in (None, False)
            and isinstance(filename, str)
            and filename.casefold().endswith("-win_arm64.whl")
        ):
            candidates.append(item)
    return candidates


def _wheel_metadata(item: Mapping[str, Any]) -> tuple[str, str, int, str]:
    """Return trusted identity fields for one PyPI release file entry."""
    filename = item.get("filename")
    url = item.get("url")
    size = item.get("size")
    digests = item.get("digests")
    sha256 = digests.get("sha256") if isinstance(digests, dict) else None
    if (
        not isinstance(filename, str)
        or not isinstance(url, str)
        or type(size) is not int
        or size <= 0
        or size > _MAX_WHEEL_BYTES
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise WatchError("PyPI returned incomplete or invalid ARM64 wheel metadata.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != _FILES_HOST:
        raise WatchError(f"PyPI returned a nonofficial ARM64 wheel URL: {url!r}.")
    url_filename = urllib.parse.unquote(Path(parsed.path).name)
    if url_filename != filename:
        raise WatchError(
            f"PyPI wheel URL names {url_filename!r}; release metadata names {filename!r}."
        )
    return filename, url, size, sha256


def _base_report(contract: Arm64WebEngineContract | None) -> dict[str, object]:
    """Create a stable report shape for current, review, and error outcomes."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "indeterminate",
        "reasonCode": "indeterminate-upstream-response",
        "reviewedContract": (
            {
                "version": contract.reviewed_version,
                "wheelFilename": contract.wheel_filename,
                "sha256": contract.sha256,
                "expectedStatus": contract.expected_status,
                "expectedReasonCode": contract.expected_reason_code,
            }
            if contract is not None
            else None
        ),
        "latestVersions": {},
        "candidate": None,
        "errors": [],
    }


def _inspect_candidate(
    item: Mapping[str, Any],
    fetch_bytes: BytesFetcher,
) -> dict[str, object]:
    """Hash a candidate and inspect only its ZIP central-directory filenames."""
    filename, url, metadata_size, registry_sha256 = _wheel_metadata(item)
    payload = fetch_bytes(url, _MAX_WHEEL_BYTES)
    computed_sha256 = hashlib.sha256(payload).hexdigest()
    if len(payload) != metadata_size:
        raise WatchError(
            f"Downloaded {filename} is {len(payload)} bytes; PyPI reports {metadata_size}."
        )
    if computed_sha256 != registry_sha256:
        raise WatchError(
            f"Downloaded {filename} has SHA-256 {computed_sha256}; PyPI reports {registry_sha256}."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.namelist()
    except zipfile.BadZipFile as error:
        raise WatchError(f"Downloaded {filename} is not a valid wheel ZIP.") from error
    if len(entries) > _MAX_RECORD_ENTRIES:
        raise WatchError(f"Downloaded {filename} has more than {_MAX_RECORD_ENTRIES} ZIP entries.")
    normalized_entries = {entry.replace("\\", "/") for entry in entries}
    required = [
        {"entry": entry, "listed": entry in normalized_entries} for entry in REQUIRED_RECORD_ENTRIES
    ]
    webengine_entries = sorted(
        entry for entry in normalized_entries if "webengine" in entry.casefold()
    )
    return {
        "filename": filename,
        "url": url,
        "metadataSize": metadata_size,
        "downloadedSize": len(payload),
        "registrySha256": registry_sha256,
        "computedSha256": computed_sha256,
        "zipEntryCount": len(entries),
        "requiredZipEntries": required,
        "completeRequiredPayload": all(cast(bool, item["listed"]) for item in required),
        "qtWebEngineEntryCount": len(webengine_entries),
        "qtWebEngineEntries": webengine_entries,
    }


def inspect_upstream(
    contract: Arm64WebEngineContract,
    *,
    fetch_json: JsonFetcher = _fetch_project_json,
    fetch_bytes: BytesFetcher = _fetch_wheel,
) -> dict[str, object]:
    """Compare official PyPI head with the reviewed contract without changing state."""
    report = _base_report(contract)
    latest_versions = cast(dict[str, str], report["latestVersions"])
    metadata_by_name: dict[str, Mapping[str, Any]] = {}
    try:
        for distribution in _PYSIDE_COHORT:
            metadata = fetch_json(distribution)
            metadata_by_name[distribution] = metadata
            latest_versions[distribution] = _project_version(metadata, distribution)

        addons_metadata = metadata_by_name["PySide6-Addons"]
        candidates = _arm64_addons_wheels(addons_metadata)
        if len(candidates) != 1:
            raise WatchError(
                "Expected exactly one non-yanked PySide6-Addons ARM64 wheel at PyPI head; "
                f"found {len(candidates)}."
            )

        if set(latest_versions.values()) == {contract.reviewed_version}:
            filename, _url, _size, registry_sha256 = _wheel_metadata(candidates[0])
            if filename != contract.wheel_filename:
                raise WatchError(
                    f"PyPI head names the reviewed wheel {filename!r}; expected "
                    f"{contract.wheel_filename!r}."
                )
            if registry_sha256 != contract.sha256:
                raise WatchError(
                    f"PyPI reports SHA-256 {registry_sha256} for the reviewed wheel; "
                    f"expected {contract.sha256}."
                )
            report["status"] = "current"
            report["reasonCode"] = "reviewed-contract-is-pypi-head"
            return report

        if latest_versions["PySide6-Addons"] != contract.reviewed_version:
            report["candidate"] = _inspect_candidate(candidates[0], fetch_bytes)
        report["status"] = "review-needed"
        report["reasonCode"] = "pyside6-cohort-head-changed"
    except WatchError as error:
        cast(list[str], report["errors"]).append(str(error))
    return report


def exit_code_for_status(status: str) -> int:
    """Map a watcher outcome to its stable workflow result."""
    if status == "current":
        return EXIT_CURRENT
    if status == "review-needed":
        return EXIT_REVIEW_NEEDED
    return EXIT_INDETERMINATE


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    """Write watcher evidence atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect official PyPI and intentionally fail when human review is needed."""
    args = build_parser().parse_args(argv)
    try:
        contract = load_review_contract()
    except ContractError as error:
        report = _base_report(None)
        cast(list[str], report["errors"]).append(str(error))
    else:
        report = inspect_upstream(contract)
    _write_report(args.report, report)
    print(json.dumps(report, indent=2))
    return exit_code_for_status(cast(str, report["status"]))


if __name__ == "__main__":
    sys.exit(main())
