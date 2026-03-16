"""Internal packer implementation for SDK."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentpk.sdk import PackResult, AnalysisResult, PackagingError, ManifestError


def run_pack(
    source: Path,
    *,
    out_dir: Path | None = None,
    analyze: bool = False,
    levels: list[int] | None = None,
    strict: bool = False,
    sandbox_timeout: int = 30,
    sandbox_harness: Path | None = None,
    validate_llm: bool = False,
    dry_run: bool = False,
) -> PackResult:
    """Core pack implementation."""
    from agentpk.packer import pack as do_pack
    from agentpk.constants import MANIFEST_FILENAME
    from datetime import datetime, timezone

    source = source.resolve()
    manifest_path = source / MANIFEST_FILENAME

    if not manifest_path.exists():
        raise ManifestError(f"manifest.yaml not found in {source}")

    # Run analysis if requested
    analysis_result: AnalysisResult | None = None
    analysis_block = None
    if analyze:
        from agentpk._internal.analyzer_runner import run_analysis
        analysis_result = run_analysis(
            source=source,
            levels=levels,
            strict=strict,
            sandbox_timeout=sandbox_timeout,
            sandbox_harness=sandbox_harness,
            validate_llm=validate_llm,
        )
        from agentpk.analyzer import build_analysis_block, analyze as _analyze
        # Run the original analyzer to get the block
        level = max(levels) if levels else 2
        ar = _analyze(source, level=level, mode="verify")
        analysis_block = build_analysis_block(ar)

    # Determine output path
    output_path: Path | None = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = do_pack(
            source,
            output_path=output_path,
            dry_run=dry_run,
            analysis_block=analysis_block,
        )
    except Exception as e:
        raise PackagingError(str(e)) from e

    if not result.success:
        errors = "; ".join(e.message for e in result.errors)
        raise PackagingError(f"Pack failed: {errors}")

    # Move to out_dir if needed
    actual_path = result.output_path or Path(".")
    if result.output_path and out_dir and not dry_run:
        new_path = out_dir / result.output_path.name
        if result.output_path != new_path:
            result.output_path.rename(new_path)
            actual_path = new_path

    from agentpk.manifest import compute_manifest_hash
    manifest_hash = compute_manifest_hash(manifest_path)

    return PackResult(
        package_path=actual_path,
        manifest_hash=manifest_hash,
        packaged_at=datetime.now(timezone.utc).isoformat(),
        source_file_count=result.file_count,
        analysis=analysis_result,
        warnings=[w.message for w in result.warnings],
    )
