"""Core pack/unpack/inspect logic for .agent files."""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from agentpk import __version__
from agentpk.checksums import (
    compute_files_hash,
    generate_checksums,
    write_checksums_file,
)
from agentpk.constants import (
    CHECKSUMS_FILENAME,
    FORMAT_VERSION,
    MANIFEST_FILENAME,
)
from agentpk.exceptions import PackageCorruptError, ValidationError
from agentpk.manifest import compute_manifest_hash, load_manifest
from agentpk.models import AgentManifest
from agentpk.validator import validate_directory, validate_package


@dataclass
class PackResult:
    """Outcome of a :func:`pack` operation."""

    success: bool
    output_path: Optional[Path] = None
    manifest_hash: str = ""
    files_hash: str = ""
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    file_count: int = 0
    size_bytes: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_files(source_dir: Path) -> list[Path]:
    """Return sorted list of all files under *source_dir*."""
    return sorted(p for p in source_dir.rglob("*") if p.is_file())


def _create_zip(source_dir: Path, output_path: Path) -> int:
    """Create a ZIP archive of *source_dir* at *output_path*.

    Returns the archive size in bytes.
    """
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in _collect_files(source_dir):
            arcname = file_path.relative_to(source_dir).as_posix()
            zf.write(file_path, arcname)
    return output_path.stat().st_size


def _inject_package_block(
    manifest_path: Path,
    *,
    manifest_hash: str,
    files_hash: str,
    total_files: int,
    package_size_bytes: int,
    analysis_block: dict[str, Any] | None = None,
) -> None:
    """Add / update the ``_package`` block in a manifest file on disk."""
    raw: dict[str, Any] = yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
    )
    pkg: dict[str, Any] = {
        "format": "agent-package-format",
        "format_version": FORMAT_VERSION,
        "packaged_at": datetime.now(timezone.utc).isoformat(),
        "packaged_by": f"agentpk/{__version__}",
        "manifest_hash": manifest_hash,
        "files_hash": files_hash,
        "total_files": total_files,
        "package_size_bytes": package_size_bytes,
    }
    if analysis_block is not None:
        pkg["analysis"] = analysis_block
    raw["_package"] = pkg
    manifest_path.write_text(
        yaml.dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pack(
    source_dir: Path,
    output_path: Path | None = None,
    dry_run: bool = False,
    analysis_block: dict[str, Any] | None = None,
) -> PackResult:
    """Pack a directory into a ``.agent`` file.

    1. Validate the source directory (stages 1-5).
    2. Generate checksums, inject ``_package`` metadata.
    3. Create a ZIP archive.
    4. Post-verify with :func:`validate_package`.
    5. Restore the source directory to its original state.
    """
    source_dir = source_dir.resolve()

    # ── Stage: pre-pack validation ────────────────────────────────────
    vr = validate_directory(source_dir)
    if not vr.is_valid:
        return PackResult(
            success=False,
            errors=vr.errors,
            warnings=vr.warnings,
        )

    manifest_path = source_dir / MANIFEST_FILENAME
    checksums_path = source_dir / CHECKSUMS_FILENAME

    # Keep a copy of the original manifest for restoration
    original_manifest = manifest_path.read_text(encoding="utf-8")
    had_checksums = checksums_path.exists()

    # ── Determine output path ─────────────────────────────────────────
    manifest = load_manifest(manifest_path)
    if output_path is None:
        filename = f"{manifest.name}-{manifest.version}.agent"
        output_path = source_dir.parent / filename
    output_path = output_path.resolve()

    # Count user files (before we add generated files)
    user_files = [
        p for p in _collect_files(source_dir)
        if p.name != CHECKSUMS_FILENAME
    ]
    file_count = len(user_files)

    # ── Dry run ───────────────────────────────────────────────────────
    if dry_run:
        mhash = compute_manifest_hash(manifest_path)
        fhash = compute_files_hash(user_files, source_dir)
        return PackResult(
            success=True,
            output_path=output_path,
            manifest_hash=mhash,
            files_hash=fhash,
            warnings=vr.warnings,
            file_count=file_count,
            size_bytes=0,
        )

    try:
        # ── Compute hashes ────────────────────────────────────────────
        manifest_hash = compute_manifest_hash(manifest_path)
        files_hash = compute_files_hash(user_files, source_dir)

        # ── First pass: inject _package with size=0, build ZIP ────────
        _inject_package_block(
            manifest_path,
            manifest_hash=manifest_hash,
            files_hash=files_hash,
            total_files=file_count,
            package_size_bytes=0,
            analysis_block=analysis_block,
        )

        checksums = generate_checksums(source_dir)
        write_checksums_file(checksums, checksums_path)

        first_size = _create_zip(source_dir, output_path)

        # ── Second pass: set real size, rebuild ───────────────────────
        _inject_package_block(
            manifest_path,
            manifest_hash=manifest_hash,
            files_hash=files_hash,
            total_files=file_count,
            package_size_bytes=first_size,
            analysis_block=analysis_block,
        )

        checksums = generate_checksums(source_dir)
        write_checksums_file(checksums, checksums_path)

        final_size = _create_zip(source_dir, output_path)

        # ── Post-build verification ───────────────────────────────────
        post = validate_package(output_path)
        if not post.is_valid:
            output_path.unlink(missing_ok=True)
            return PackResult(
                success=False,
                errors=post.errors,
                warnings=post.warnings,
            )

        return PackResult(
            success=True,
            output_path=output_path,
            manifest_hash=manifest_hash,
            files_hash=files_hash,
            warnings=vr.warnings + post.warnings,
            file_count=file_count,
            size_bytes=final_size,
        )

    finally:
        # ── Restore source directory ──────────────────────────────────
        manifest_path.write_text(original_manifest, encoding="utf-8")
        if not had_checksums:
            checksums_path.unlink(missing_ok=True)


def unpack(package_path: Path, output_dir: Path) -> None:
    """Validate and extract a ``.agent`` file to *output_dir*.

    Raises :class:`PackageCorruptError` if validation fails.
    """
    vr = validate_package(package_path)
    if not vr.is_valid:
        msgs = "; ".join(e.message for e in vr.errors)
        raise PackageCorruptError(f"Package validation failed: {msgs}")

    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(output_dir)


def inspect(package_path: Path) -> dict[str, Any]:
    """Extract metadata from a ``.agent`` file without writing to disk.

    Returns a dict with keys:
      manifest, files, size_bytes, is_valid, errors, warnings, analysis
    """
    result: dict[str, Any] = {
        "manifest": None,
        "files": [],
        "size_bytes": 0,
        "is_valid": False,
        "errors": [],
        "warnings": [],
        "analysis": None,
    }

    result["size_bytes"] = package_path.stat().st_size

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                result["files"] = sorted(zf.namelist())
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile as exc:
            result["errors"] = [str(exc)]
            return result

        manifest_path = tmp_dir / MANIFEST_FILENAME
        if manifest_path.exists():
            try:
                result["manifest"] = load_manifest(manifest_path)
            except Exception as exc:
                result["errors"] = [str(exc)]
                return result

            # Extract analysis block from raw _package data
            try:
                raw = yaml.safe_load(
                    manifest_path.read_text(encoding="utf-8")
                )
                pkg = raw.get("_package", {})
                if isinstance(pkg, dict):
                    result["analysis"] = pkg.get("analysis")
            except Exception:
                pass

        vr = validate_package(package_path)
        result["is_valid"] = vr.is_valid
        result["errors"] = [e.message for e in vr.errors]
        result["warnings"] = [w.message for w in vr.warnings]

    return result
