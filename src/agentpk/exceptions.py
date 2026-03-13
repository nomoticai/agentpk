"""Custom exception classes for agentpk."""

from __future__ import annotations

from typing import Literal


class AgentPackError(Exception):
    """Base exception for all agentpk errors."""


class ManifestNotFoundError(AgentPackError):
    """Raised when manifest.yaml is missing from a package."""


class ManifestParseError(AgentPackError):
    """Raised when manifest.yaml cannot be parsed."""


class ValidationError(AgentPackError):
    """Raised when manifest or package validation fails.

    Attributes:
        message: Human-readable description of the validation failure.
        field: Dot-separated path to the invalid field (e.g. "agent.name").
        severity: Either "fatal" (blocks packaging) or "warning" (advisory).
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        severity: Literal["fatal", "warning"] = "fatal",
    ) -> None:
        self.message = message
        self.field = field
        self.severity = severity
        super().__init__(message)


class PackageCorruptError(AgentPackError):
    """Raised when a .agent file is structurally invalid or corrupted."""


class ChecksumMismatchError(AgentPackError):
    """Raised when file checksums do not match expected values."""
