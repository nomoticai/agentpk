"""Manifest diff for ``agent diff``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentpk.models import AgentManifest
from agentpk.packer import inspect as inspect_package


@dataclass
class ManifestDiff:
    """Represents differences between two manifests."""

    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.removed and not self.changed


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict/list into dot-separated keys."""
    items: dict[str, Any] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else k
            items.update(_flatten(v, key))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            key = f"{prefix}[{i}]"
            items.update(_flatten(v, key))
    else:
        items[prefix] = data
    return items


def diff_manifests(old: AgentManifest, new: AgentManifest) -> ManifestDiff:
    """Compute a field-by-field diff between two manifest models."""
    old_flat = _flatten(old.model_dump(exclude_none=True, by_alias=True))
    new_flat = _flatten(new.model_dump(exclude_none=True, by_alias=True))

    old_keys = set(old_flat)
    new_keys = set(new_flat)

    result = ManifestDiff()

    for k in sorted(new_keys - old_keys):
        result.added[k] = new_flat[k]

    for k in sorted(old_keys - new_keys):
        result.removed[k] = old_flat[k]

    for k in sorted(old_keys & new_keys):
        if old_flat[k] != new_flat[k]:
            result.changed[k] = (old_flat[k], new_flat[k])

    return result


def diff_packages(old_path: Path, new_path: Path) -> ManifestDiff:
    """Compute the diff between manifests of two ``.agent`` files."""
    old_info = inspect_package(old_path)
    new_info = inspect_package(new_path)

    old_manifest: AgentManifest = old_info["manifest"]
    new_manifest: AgentManifest = new_info["manifest"]

    return diff_manifests(old_manifest, new_manifest)
