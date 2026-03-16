"""Internal validation implementation for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import ValidateResult


def run_validate(source: Path) -> ValidateResult:
    """Core validation implementation."""
    from agentpk.constants import MANIFEST_FILENAME

    if not source.exists():
        return ValidateResult(
            valid=False,
            errors=[f"Path does not exist: {source}"],
            warnings=[],
            manifest_path=None,
            schema_version=None,
        )

    try:
        if source.is_dir():
            from agentpk.validator import validate_directory
            vr = validate_directory(source)
            manifest_path = source / MANIFEST_FILENAME
        else:
            from agentpk.validator import validate_package
            vr = validate_package(source)
            manifest_path = source
    except Exception as e:
        return ValidateResult(
            valid=False,
            errors=[str(e)],
            warnings=[],
            manifest_path=None,
            schema_version=None,
        )

    errors = [e.message for e in vr.errors]
    warnings = [w.message for w in vr.warnings]

    # Try to extract schema version
    schema_version = None
    if source.is_dir():
        mp = source / MANIFEST_FILENAME
        if mp.exists():
            try:
                import yaml
                data = yaml.safe_load(mp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    schema_version = data.get("spec_version")
            except Exception:
                pass

    return ValidateResult(
        valid=vr.is_valid,
        errors=errors,
        warnings=warnings,
        manifest_path=manifest_path if manifest_path.exists() else None,
        schema_version=schema_version,
    )
