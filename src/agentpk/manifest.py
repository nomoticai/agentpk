"""Manifest parsing, serialization, and hash computation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from agentpk.exceptions import ManifestNotFoundError, ManifestParseError
from agentpk.models import AgentManifest


def load_manifest(manifest_path: Path) -> AgentManifest:
    """Read and parse a manifest.yaml into an :class:`AgentManifest`.

    The ``_package`` block in YAML is mapped to the ``package_metadata``
    field on the model.

    Raises:
        ManifestNotFoundError: If *manifest_path* does not exist.
        ManifestParseError: If YAML is invalid or Pydantic validation fails.
    """
    if not manifest_path.exists():
        raise ManifestNotFoundError(f"Manifest not found: {manifest_path}")

    raw = manifest_path.read_text(encoding="utf-8")

    try:
        data: dict[str, Any] = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ManifestParseError(f"Invalid YAML in {manifest_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestParseError(
            f"Expected a YAML mapping at top level, got {type(data).__name__}"
        )

    try:
        return AgentManifest.model_validate(data)
    except PydanticValidationError as exc:
        raise ManifestParseError(str(exc)) from exc


def compute_manifest_hash(manifest_path: Path) -> str:
    """Compute SHA-256 over zones 1 and 2 of a manifest (excluding ``_package``).

    Returns a string of the form ``"sha256:<hex>"``.

    Raises:
        ManifestNotFoundError: If *manifest_path* does not exist.
        ManifestParseError: If YAML cannot be parsed.
    """
    if not manifest_path.exists():
        raise ManifestNotFoundError(f"Manifest not found: {manifest_path}")

    raw = manifest_path.read_text(encoding="utf-8")

    # Strip the _package block before hashing.
    # We re-parse, remove the key, and re-dump to get deterministic bytes.
    try:
        data: dict[str, Any] = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ManifestParseError(f"Invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestParseError("Expected top-level YAML mapping")

    data.pop("_package", None)

    # Dump with sorted keys for deterministic output
    canonical = yaml.dump(data, default_flow_style=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def detect_language(source_dir: Path) -> str | None:
    """Infer runtime language from file extension distribution.

    Returns language string or None if ambiguous.
    """
    ext_counts: dict[str, int] = {}
    for f in source_dir.rglob("*"):
        if f.is_file():
            # Skip common non-source dirs
            parts = f.relative_to(source_dir).parts
            if any(
                part in ("node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build")
                for part in parts
            ):
                continue
            ext = f.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    EXT_MAP = {
        ".py": "python",
        ".js": "nodejs",
        ".mjs": "nodejs",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
    }

    lang_counts: dict[str, int] = {}
    for ext, count in ext_counts.items():
        lang = EXT_MAP.get(ext)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + count

    if not lang_counts:
        return None

    top_lang = max(lang_counts, key=lang_counts.get)  # type: ignore[arg-type]
    return top_lang


def dump_manifest(manifest: AgentManifest, manifest_path: Path) -> None:
    """Write an :class:`AgentManifest` to a YAML file.

    The ``package_metadata`` field is serialised as ``_package`` in the
    output YAML.
    """
    data: dict[str, Any] = manifest.model_dump(
        exclude_none=True, by_alias=True
    )

    manifest_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
