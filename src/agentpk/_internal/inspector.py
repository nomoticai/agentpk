"""Internal inspect implementation for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import InspectResult, PackagingError, AnalysisResult, DiscrepancyRecord


def run_inspect(path: Path) -> InspectResult:
    """Core inspect implementation."""
    from agentpk.packer import inspect as do_inspect

    try:
        info = do_inspect(path)
    except Exception as e:
        raise PackagingError(f"Cannot inspect {path}: {e}") from e

    manifest = info.get("manifest")
    if manifest is None:
        errors = info.get("errors", [])
        raise PackagingError(f"Cannot read manifest: {'; '.join(str(e) for e in errors)}")

    # Convert analysis if present
    analysis = None
    analysis_data = info.get("analysis")
    if analysis_data:
        discrepancy_records = []
        for d in analysis_data.get("discrepancies", []):
            if isinstance(d, dict):
                discrepancy_records.append(DiscrepancyRecord(
                    type=d.get("type", "undeclared"),
                    severity=d.get("severity", "minor"),
                    source=d.get("source", "static"),
                    capability=d.get("description", ""),
                    file="",
                    line=0,
                    evidence=d.get("evidence", ""),
                    penalty=0,
                ))

        analysis = AnalysisResult(
            trust_score=analysis_data.get("trust_score", 0),
            trust_label=analysis_data.get("trust_label", "Unverified"),
            levels_run=analysis_data.get("levels_run", []),
            levels_skipped=analysis_data.get("levels_skipped", []),
            discrepancy_count=len(discrepancy_records),
            discrepancy_records=discrepancy_records,
            analysis_timestamp=analysis_data.get("analyzed_at", ""),
            extractor_warnings=[],
        )

    return InspectResult(
        name=manifest.name,
        version=manifest.version,
        language=manifest.runtime.language,
        entry_point=manifest.runtime.entry_point,
        capabilities=manifest.capabilities.model_dump() if manifest.capabilities else {},
        packaged_at=manifest.package_metadata.packaged_at if manifest.package_metadata else "",
        manifest_hash=manifest.package_metadata.manifest_hash if manifest.package_metadata else "",
        analysis=analysis,
        source_files=info.get("files", []),
        package_size_bytes=path.stat().st_size,
    )
