"""Full 6-stage validation pipeline for .agent packages.

Stages
------
1. Pre-flight   — directory exists, manifest parseable, spec_version known
2. Identity     — name, version, description, runtime presence
3. File presence — entry_point and dependencies files exist on disk
4. Consistency  — field values match allowed enums, cross-field rules
5. Checksums    — checksum file present and all hashes match  *(package only)*
6. Post-package — _package.manifest_hash matches zone 1         *(package only)*
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentpk.checksums import verify_checksums
from agentpk.constants import (
    CHECKSUMS_FILENAME,
    FORMAT_VERSION,
    MANIFEST_FILENAME,
    VALID_EXECUTION_TYPES,
    VALID_LANGUAGES,
    VALID_NETWORK,
    VALID_SCOPES,
)
from agentpk.exceptions import ValidationError
from agentpk.manifest import compute_manifest_hash

# ---------------------------------------------------------------------------
# Regexes used by the validator (intentionally separate from models.py so
# the validator can run against raw dicts without Pydantic).
# ---------------------------------------------------------------------------
_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")
_HOURS_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Outcome of a single validation stage."""

    name: str
    status: str  # "pass", "fail", "skip"
    message: str = ""


@dataclass
class ValidationResult:
    """Accumulates errors (fatal) and warnings from validation stages."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str, field: str | None = None) -> None:
        self.errors.append(ValidationError(message, field=field, severity="fatal"))

    def add_warning(self, message: str, field: str | None = None) -> None:
        self.warnings.append(ValidationError(message, field=field, severity="warning"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts."""
    current: Any = data
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k, default)
    return current


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


def _stage1_preflight(source_dir: Path, result: ValidationResult) -> dict | None:
    """Stage 1 — Pre-flight checks.  Returns parsed YAML dict or ``None``."""

    if not source_dir.exists() or not source_dir.is_dir():
        result.add_error(
            f"Source directory does not exist: {source_dir}", field="source_dir"
        )
        return None

    manifest_path = source_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        result.add_error(
            f"{MANIFEST_FILENAME} not found in {source_dir}",
            field=MANIFEST_FILENAME,
        )
        return None

    raw = manifest_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        result.add_error(f"Invalid YAML: {exc}", field=MANIFEST_FILENAME)
        return None

    if not isinstance(data, dict):
        result.add_error(
            f"Expected top-level YAML mapping, got {type(data).__name__}",
            field=MANIFEST_FILENAME,
        )
        return None

    spec = data.get("spec_version")
    if spec is None:
        result.add_error("spec_version is missing", field="spec_version")
        return None

    if str(spec) != FORMAT_VERSION:
        result.add_error(
            f"Unrecognised spec_version: {spec!r} (expected {FORMAT_VERSION!r})",
            field="spec_version",
        )
        return None

    return data


def _stage2_identity(data: dict, result: ValidationResult) -> None:
    """Stage 2 — Identity fields."""

    name = data.get("name")
    if name is None:
        result.add_error("name is required", field="name")
    elif not _NAME_RE.match(str(name)):
        result.add_error(
            f"name must match ^[a-z0-9][a-z0-9-]*[a-z0-9]$, got {name!r}",
            field="name",
        )

    version = data.get("version")
    if version is None:
        result.add_error("version is required", field="version")
    elif not _SEMVER_RE.match(str(version)):
        result.add_error(
            f"version must be semantic (x.y.z), got {version!r}",
            field="version",
        )

    desc = data.get("description")
    if not desc:
        result.add_error("description is required and must be non-empty", field="description")

    runtime = data.get("runtime")
    if runtime is None:
        result.add_error("runtime section is required", field="runtime")
    elif not isinstance(runtime, dict):
        result.add_error("runtime must be a mapping", field="runtime")
    else:
        if not runtime.get("entry_point"):
            result.add_error(
                "runtime.entry_point is required", field="runtime.entry_point"
            )


def _stage3_file_presence(
    data: dict, source_dir: Path, result: ValidationResult
) -> None:
    """Stage 3 — Referenced files exist on disk."""

    runtime = data.get("runtime")
    if not isinstance(runtime, dict):
        return

    entry_point = runtime.get("entry_point")
    if entry_point and not (source_dir / entry_point).exists():
        result.add_error(
            f"Entry-point file not found: {entry_point}",
            field="runtime.entry_point",
        )

    deps = runtime.get("dependencies")
    if deps and not (source_dir / deps).exists():
        result.add_error(
            f"Dependencies file not found: {deps}",
            field="runtime.dependencies",
        )


def _stage4_consistency(data: dict, result: ValidationResult) -> None:
    """Stage 4 — Manifest field consistency."""

    # execution.type
    exec_block = data.get("execution") or {}
    exec_type = exec_block.get("type")
    if exec_type is not None and exec_type not in VALID_EXECUTION_TYPES:
        result.add_error(
            f"execution.type must be one of {VALID_EXECUTION_TYPES}, got {exec_type!r}",
            field="execution.type",
        )

    # execution.schedule required for "scheduled"
    if exec_type == "scheduled" and not exec_block.get("schedule"):
        result.add_error(
            "execution.schedule is required when type is 'scheduled'",
            field="execution.schedule",
        )

    # runtime.language
    lang = _get(data, "runtime", "language")
    if lang is not None and lang not in VALID_LANGUAGES:
        result.add_error(
            f"runtime.language must be one of {VALID_LANGUAGES}, got {lang!r}",
            field="runtime.language",
        )

    # resources.network
    network = _get(data, "resources", "network")
    if network is not None and network not in VALID_NETWORK:
        result.add_error(
            f"resources.network must be one of {VALID_NETWORK}, got {network!r}",
            field="resources.network",
        )

    # tool scopes
    tools = _get(data, "capabilities", "tools") or []
    if isinstance(tools, list):
        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                continue
            scope = tool.get("scope")
            if scope is not None and scope not in VALID_SCOPES:
                result.add_error(
                    f"Tool {tool.get('id', i)}: scope must be one of "
                    f"{VALID_SCOPES}, got {scope!r}",
                    field=f"capabilities.tools[{i}].scope",
                )

    # permitted_windows.hours format
    windows = exec_block.get("permitted_windows") or []
    if isinstance(windows, list):
        for i, w in enumerate(windows):
            if not isinstance(w, dict):
                continue
            hours = w.get("hours")
            if hours and not _HOURS_RE.match(str(hours)):
                result.add_error(
                    f"permitted_windows[{i}].hours must match HH:MM-HH:MM, "
                    f"got {hours!r}",
                    field=f"execution.permitted_windows[{i}].hours",
                )

    # environments.allowed / denied overlap
    perms = data.get("permissions") or {}
    env = perms.get("environments") or {} if isinstance(perms, dict) else {}
    allowed = set(env.get("allowed") or []) if isinstance(env, dict) else set()
    denied = set(env.get("denied") or []) if isinstance(env, dict) else set()
    overlap = allowed & denied
    if overlap:
        result.add_error(
            f"environments.allowed and environments.denied overlap: {overlap}",
            field="permissions.environments",
        )


def _stage5_checksums(
    source_dir: Path, result: ValidationResult
) -> None:
    """Stage 5 — Checksum verification."""

    checksums_path = source_dir / CHECKSUMS_FILENAME
    if not checksums_path.exists():
        result.add_error(
            f"{CHECKSUMS_FILENAME} not found in package",
            field=CHECKSUMS_FILENAME,
        )
        return

    errors = verify_checksums(checksums_path, source_dir)
    for err in errors:
        result.errors.append(err)


def _stage6_manifest_hash(
    source_dir: Path, data: dict, result: ValidationResult
) -> None:
    """Stage 6 — Post-package manifest hash verification."""

    pkg = data.get("_package")
    if not isinstance(pkg, dict):
        return  # Nothing to verify if no _package block

    expected_hash = pkg.get("manifest_hash")
    if expected_hash is None:
        return

    manifest_path = source_dir / MANIFEST_FILENAME
    actual_hash = compute_manifest_hash(manifest_path)
    if actual_hash != expected_hash:
        result.add_error(
            f"Manifest hash mismatch: expected {expected_hash}, got {actual_hash}",
            field="_package.manifest_hash",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_directory(source_dir: Path) -> ValidationResult:
    """Run stages 1–4 against an unpacked agent directory.

    This is what runs during ``agent pack`` before packaging.  Stage 1
    failures abort immediately; later stages accumulate all issues.
    """
    result = ValidationResult()

    # Stage 1 — Pre-flight (abort on failure)
    err_before = len(result.errors)
    data = _stage1_preflight(source_dir, result)
    if data is None:
        result.stages.append(StageResult("Pre-flight", "fail"))
        result.stages.append(StageResult("Identity", "skip"))
        result.stages.append(StageResult("File presence", "skip"))
        result.stages.append(StageResult("Consistency", "skip"))
        return result
    result.stages.append(StageResult("Pre-flight", "pass"))

    # Stage 2 — Identity
    err_before = len(result.errors)
    _stage2_identity(data, result)
    s2_failed = len(result.errors) > err_before
    result.stages.append(StageResult("Identity", "fail" if s2_failed else "pass"))

    # Stage 3 — File presence
    err_before = len(result.errors)
    _stage3_file_presence(data, source_dir, result)
    s3_failed = len(result.errors) > err_before
    result.stages.append(StageResult("File presence", "fail" if s3_failed else "pass"))

    # Stage 4 — Consistency
    err_before = len(result.errors)
    _stage4_consistency(data, result)
    s4_failed = len(result.errors) > err_before
    result.stages.append(StageResult("Consistency", "fail" if s4_failed else "pass"))

    return result


def validate_package(package_path: Path) -> ValidationResult:
    """Run all 6 stages against a ``.agent`` file.

    Extracts the archive to a temporary directory, runs
    :func:`validate_directory` (stages 1–4), then stages 5 and 6.
    The temporary directory is cleaned up regardless of outcome.
    """
    result = ValidationResult()

    if not package_path.exists():
        result.add_error(f"Package file not found: {package_path}")
        return result

    if not zipfile.is_zipfile(package_path):
        result.add_error(f"Not a valid .agent archive: {package_path}")
        return result

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile as exc:
            result.add_error(f"Corrupt .agent archive: {exc}")
            return result

        # Stages 1–4
        dir_result = validate_directory(tmp_dir)
        result.errors.extend(dir_result.errors)
        result.warnings.extend(dir_result.warnings)
        result.stages.extend(dir_result.stages)

        if not dir_result.is_valid:
            result.stages.append(StageResult("Checksums", "skip"))
            result.stages.append(StageResult("Package integrity", "skip"))
            return result

        # Re-read raw data for stage 6
        manifest_path = tmp_dir / MANIFEST_FILENAME
        raw_data: dict = yaml.safe_load(
            manifest_path.read_text(encoding="utf-8")
        )

        # Stage 5 — Checksums
        err_before = len(result.errors)
        _stage5_checksums(tmp_dir, result)
        s5_failed = len(result.errors) > err_before
        result.stages.append(StageResult("Checksums", "fail" if s5_failed else "pass"))

        # Stage 6 — Post-package manifest hash
        err_before = len(result.errors)
        _stage6_manifest_hash(tmp_dir, raw_data, result)
        s6_failed = len(result.errors) > err_before
        result.stages.append(StageResult("Package integrity", "fail" if s6_failed else "pass"))

    return result
