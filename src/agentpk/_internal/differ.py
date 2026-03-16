"""Internal diff implementation for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import DiffResult, PackageNotFoundError


def run_diff(package_a: Path, package_b: Path) -> DiffResult:
    """Core diff implementation."""
    if not package_a.exists():
        raise PackageNotFoundError(f"Package not found: {package_a}")
    if not package_b.exists():
        raise PackageNotFoundError(f"Package not found: {package_b}")

    from agentpk.diff import diff_packages

    d = diff_packages(package_a, package_b)

    added_caps = []
    removed_caps = []
    manifest_changes = []

    for key, value in d.added.items():
        if "tool" in key.lower() or "capability" in key.lower():
            added_caps.append(f"{key}: {value}")
        else:
            manifest_changes.append(f"+ {key}: {value}")

    for key, value in d.removed.items():
        if "tool" in key.lower() or "capability" in key.lower():
            removed_caps.append(f"{key}: {value}")
        else:
            manifest_changes.append(f"- {key}: {value}")

    for key, (old_val, new_val) in d.changed.items():
        manifest_changes.append(f"~ {key}: {old_val} -> {new_val}")

    return DiffResult(
        added_capabilities=added_caps,
        removed_capabilities=removed_caps,
        trust_score_delta=None,
        manifest_changes=manifest_changes,
        source_changed=not d.is_empty,
    )
