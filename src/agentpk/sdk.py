"""agentpk Python SDK

The programmatic interface to agentpk. All CLI commands are thin wrappers
over these functions.

Quick start:
    from agentpk import pack, analyze, validate, init

    r = init('my-agent', dest='/tmp', runtime='python')
    v = validate(r.project_dir)
    print('valid:', v.valid)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# -- Result Types -----------------------------------------------------------

@dataclass(frozen=True)
class DiscrepancyRecord:
    """A single discrepancy found during analysis."""
    type: str            # undeclared | unconfirmed | scope_mismatch
    severity: str        # minor | major | critical
    source: str          # static | llm | sandbox | static+llm | triple-confirmed
    capability: str      # human-readable description
    file: str            # source file where signal was found
    line: int            # line number
    evidence: str        # human-readable evidence string
    penalty: float       # effective penalty after weight modifiers
    requires_review: bool = False


@dataclass(frozen=True)
class AnalysisResult:
    """Result of running --analyze on an agent directory."""
    trust_score: int                              # 0-100
    trust_label: str                              # Verified | High | Moderate | Low | Unverified
    levels_run: list[int]                         # e.g. [1, 2, 3]
    levels_skipped: list[dict[str, str]]          # [{"level": "4", "reason": "Docker not available"}]
    discrepancy_count: int
    discrepancy_records: list[DiscrepancyRecord]
    analysis_timestamp: str                       # ISO 8601
    extractor_warnings: list[str]                 # non-fatal warnings from extractors


@dataclass(frozen=True)
class PackResult:
    """Result of packing an agent directory into a .agent archive."""
    package_path: Path
    manifest_hash: str
    packaged_at: str
    source_file_count: int
    analysis: AnalysisResult | None
    warnings: list[str] = field(default_factory=list)

    @property
    def trust_score(self) -> int | None:
        return self.analysis.trust_score if self.analysis else None

    @property
    def trust_label(self) -> str | None:
        return self.analysis.trust_label if self.analysis else None


@dataclass(frozen=True)
class ValidateResult:
    """Result of validating an agent directory or .agent archive."""
    valid: bool
    errors: list[str]
    warnings: list[str]
    manifest_path: Path | None
    schema_version: str | None


@dataclass(frozen=True)
class InspectResult:
    """Result of inspecting a .agent archive."""
    name: str
    version: str
    language: str
    entry_point: str
    capabilities: dict[str, Any]
    packaged_at: str
    manifest_hash: str
    analysis: AnalysisResult | None
    source_files: list[str]
    package_size_bytes: int


@dataclass(frozen=True)
class InitResult:
    """Result of scaffolding a new agent project."""
    project_dir: Path
    runtime: str
    files_created: list[Path]


@dataclass(frozen=True)
class DiffResult:
    """Result of comparing two .agent archives."""
    added_capabilities: list[str]
    removed_capabilities: list[str]
    trust_score_delta: int | None
    manifest_changes: list[str]
    source_changed: bool


# -- Exceptions -------------------------------------------------------------

class AgentpkError(Exception):
    """Base class for all agentpk SDK errors."""


class ManifestError(AgentpkError):
    """Manifest is missing, malformed, or schema-invalid."""


class PackagingError(AgentpkError):
    """Packaging operation failed."""


class ValidationError(AgentpkError):
    """Agent directory or archive failed validation."""


class AnalysisError(AgentpkError):
    """Analysis pipeline encountered a non-recoverable error."""


class PackageNotFoundError(AgentpkError):
    """Specified .agent archive does not exist."""


# -- Core SDK Functions -----------------------------------------------------

def pack(
    source: str | Path,
    *,
    out_dir: str | Path | None = None,
    analyze: bool = False,
    levels: list[int] | None = None,
    strict: bool = False,
    sandbox_timeout: int = 30,
    sandbox_harness: str | Path | None = None,
    validate_llm: bool = False,
    dry_run: bool = False,
) -> PackResult:
    """Pack an agent directory into a .agent archive."""
    from agentpk._internal.packer import run_pack
    return run_pack(
        source=Path(source),
        out_dir=Path(out_dir) if out_dir else None,
        analyze=analyze,
        levels=levels,
        strict=strict,
        sandbox_timeout=sandbox_timeout,
        sandbox_harness=Path(sandbox_harness) if sandbox_harness else None,
        validate_llm=validate_llm,
        dry_run=dry_run,
    )


def analyze(
    source: str | Path,
    *,
    levels: list[int] | None = None,
    strict: bool = False,
    sandbox_timeout: int = 30,
    sandbox_harness: str | Path | None = None,
    validate_llm: bool = False,
) -> AnalysisResult:
    """Run behavioral verification on an agent directory without packaging."""
    from agentpk._internal.analyzer_runner import run_analysis
    return run_analysis(
        source=Path(source),
        levels=levels,
        strict=strict,
        sandbox_timeout=sandbox_timeout,
        sandbox_harness=Path(sandbox_harness) if sandbox_harness else None,
        validate_llm=validate_llm,
    )


def validate(source: str | Path) -> ValidateResult:
    """Validate an agent directory or .agent archive against the manifest schema."""
    from agentpk._internal.validator import run_validate
    return run_validate(Path(source))


def inspect_package(package: str | Path) -> InspectResult:
    """Inspect the contents and metadata of a .agent archive."""
    from agentpk._internal.inspector import run_inspect
    path = Path(package)
    if not path.exists():
        raise PackageNotFoundError(f"Package not found: {path}")
    return run_inspect(path)


def init(
    name: str,
    *,
    dest: str | Path | None = None,
    runtime: str = "python",
    force: bool = False,
) -> InitResult:
    """Scaffold a new agent project directory."""
    from agentpk._internal.scaffolder import run_init
    return run_init(
        name=name,
        dest=Path(dest) if dest else Path.cwd(),
        runtime=runtime,
        force=force,
    )


def diff(
    package_a: str | Path,
    package_b: str | Path,
) -> DiffResult:
    """Compare two .agent archives."""
    from agentpk._internal.differ import run_diff
    return run_diff(Path(package_a), Path(package_b))


def sign(
    package: str | Path,
    *,
    key: str | Path,          # Ed25519 private key (.pem)
    signer: str | None = None,
    out: str | Path | None = None,
) -> Path:
    """
    Sign a .agent archive with an Ed25519 private key.

    Args:
        package:  Path to .agent file
        key:      Path to Ed25519 private key (.pem) — from agent keygen
        signer:   Optional signer name embedded in the .sig metadata
        out:      Output path for .sig file (default: package_path + .sig)

    Returns:
        Path to .sig file
    """
    from agentpk._internal.signer import run_sign
    return run_sign(Path(package), key=Path(key), signer=signer,
                    out=Path(out) if out else None)


def verify(
    package: str | Path,
    *,
    key: str | Path,          # Ed25519 public key (.pub.pem)
) -> bool:
    """
    Verify the Ed25519 signature on a .agent archive.

    Args:
        package:  Path to .agent file
        key:      Path to Ed25519 public key (.pub.pem) — from agent keygen

    Returns:
        True if signature is valid, False if invalid
    """
    from agentpk._internal.signer import run_verify
    return run_verify(Path(package), key=Path(key))
