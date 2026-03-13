"""Pydantic models for the .agent manifest schema.

Two zones:
  Zone 1 (open core) — runtime, capabilities, permissions, execution, resources
  Zone 2 (package)   — build-time metadata prefixed with ``_`` in YAML
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentpk.constants import (
    VALID_EXECUTION_TYPES,
    VALID_FRAMEWORKS,
    VALID_LANGUAGES,
    VALID_NETWORK,
    VALID_SCOPES,
)

# ---------------------------------------------------------------------------
# Zone 1 — open core
# ---------------------------------------------------------------------------


class RuntimeConfig(BaseModel):
    """Runtime environment configuration."""

    language: str
    language_version: str
    entry_point: str
    entry_function: Optional[str] = "main"
    dependencies: Optional[str] = None

    @field_validator("language")
    @classmethod
    def _check_language(cls, v: str) -> str:
        if v not in VALID_LANGUAGES:
            raise ValueError(f"language must be one of {VALID_LANGUAGES}, got {v!r}")
        return v


class AgentModelConfig(BaseModel):
    """LLM model preferences (named to avoid clash with pydantic ModelConfig)."""

    agnostic: bool = False
    preferred: Optional[str] = None
    minimum_context: Optional[int] = None
    alternatives: list[str] = Field(default_factory=list)


class FrameworkConfig(BaseModel):
    """Agent framework configuration."""

    name: str
    version: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _check_framework(cls, v: str) -> str:
        if v not in VALID_FRAMEWORKS:
            raise ValueError(f"framework name must be one of {VALID_FRAMEWORKS}, got {v!r}")
        return v


class ToolDeclaration(BaseModel):
    """A single tool exposed by the agent."""

    id: str
    description: str
    scope: str
    required: bool
    targets: list[str] = Field(default_factory=list)
    constraints: Optional[dict[str, Any]] = None

    @field_validator("scope")
    @classmethod
    def _check_scope(cls, v: str) -> str:
        if v not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {VALID_SCOPES}, got {v!r}")
        return v


class CapabilitiesConfig(BaseModel):
    """Agent capabilities (tools list)."""

    tools: list[ToolDeclaration] = Field(default_factory=list)


class DataClassDeclaration(BaseModel):
    """A data classification declaration."""

    name: str
    access: str


class EnvironmentPermissions(BaseModel):
    """Allowed/denied environment variable access."""

    allowed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)


class PermissionsConfig(BaseModel):
    """Data-class and environment permissions."""

    data_classes: list[DataClassDeclaration] = Field(default_factory=list)
    environments: EnvironmentPermissions = Field(default_factory=EnvironmentPermissions)


class PermittedWindow(BaseModel):
    """A time window during which execution is permitted."""

    days: list[str]
    hours: str
    timezone: str = "UTC"


class RetryConfig(BaseModel):
    """Retry behaviour on failure."""

    max_attempts: int = 3
    backoff_seconds: int = 60


class ExecutionConfig(BaseModel):
    """Execution type, scheduling, and constraints."""

    type: str
    schedule: Optional[str] = None
    timezone: str = "UTC"
    triggers: Optional[list[dict[str, Any]]] = None
    poll_interval_seconds: Optional[int] = None
    permitted_windows: list[PermittedWindow] = Field(default_factory=list)
    max_concurrent_instances: int = 1
    timeout_minutes: Optional[int] = None
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in VALID_EXECUTION_TYPES:
            raise ValueError(
                f"execution type must be one of {VALID_EXECUTION_TYPES}, got {v!r}"
            )
        return v


class ResourcesConfig(BaseModel):
    """Compute resource requests."""

    memory_mb: Optional[int] = None
    cpu_shares: Optional[int] = None
    network: Optional[str] = None

    @field_validator("network")
    @classmethod
    def _check_network(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_NETWORK:
            raise ValueError(f"network must be one of {VALID_NETWORK}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Zone 2 — package metadata (underscore-prefixed in YAML)
# ---------------------------------------------------------------------------


class PackageMetadata(BaseModel):
    """Build-time package metadata (``_package`` in YAML)."""

    format: str = "agent-package-format"
    format_version: str
    packaged_at: str
    packaged_by: str
    manifest_hash: str
    files_hash: str
    total_files: int
    package_size_bytes: int


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


class AgentManifest(BaseModel):
    """Top-level manifest model representing a complete manifest.yaml.

    Spans two zones:
      - Zone 1 fields are direct attributes (identity, runtime, capabilities, etc.)
      - Zone 2 is the optional ``package_metadata`` (``_package`` in YAML)
    """

    model_config = ConfigDict(populate_by_name=True)

    # identity
    spec_version: str
    name: str
    display_name: Optional[str] = None
    version: str
    description: str
    author: Optional[str] = None
    organization: Optional[str] = None
    license: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    # Zone 1 sections
    runtime: RuntimeConfig
    model: Optional[AgentModelConfig] = None
    framework: Optional[FrameworkConfig] = None
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    execution: ExecutionConfig
    resources: Optional[ResourcesConfig] = None

    # Zone 2 — serialised as ``_package`` in YAML
    package_metadata: Optional[PackageMetadata] = Field(
        default=None, alias="_package"
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                f"name must be lowercase with hyphens/numbers only, got {v!r}"
            )
        return v

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"version must be a valid semantic version, got {v!r}")
        return v
