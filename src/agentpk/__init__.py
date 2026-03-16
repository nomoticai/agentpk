"""agentpk - Package AI agents into portable .agent files."""

__version__ = "0.2.0"

from agentpk.sdk import (
    pack,
    analyze,
    validate,
    inspect_package,
    init,
    diff,
    sign,
    verify,
    # Result types
    PackResult,
    AnalysisResult,
    ValidateResult,
    InspectResult,
    InitResult,
    DiffResult,
    DiscrepancyRecord,
    # Exceptions
    AgentpkError,
    ManifestError,
    PackagingError,
    ValidationError,
    AnalysisError,
    PackageNotFoundError,
)

__all__ = [
    "pack", "analyze", "validate", "inspect_package", "init", "diff", "sign", "verify",
    "PackResult", "AnalysisResult", "ValidateResult", "InspectResult",
    "InitResult", "DiffResult", "DiscrepancyRecord",
    "AgentpkError", "ManifestError", "PackagingError",
    "ValidationError", "AnalysisError", "PackageNotFoundError",
]
