"""Internal analysis runner for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import AnalysisResult, DiscrepancyRecord, AnalysisError


def run_analysis(
    source: Path,
    *,
    levels: list[int] | None = None,
    strict: bool = False,
    sandbox_timeout: int = 30,
    sandbox_harness: Path | None = None,
    validate_llm: bool = False,
) -> AnalysisResult:
    """Core analysis implementation."""
    from agentpk.analyzer import analyze as _analyze

    level = max(levels) if levels else 2

    try:
        ar = _analyze(source, level=level, mode="verify")
    except Exception as e:
        raise AnalysisError(str(e)) from e

    # Check strict mode
    if strict and levels:
        for requested_level in levels:
            if requested_level not in ar.levels_run:
                raise AnalysisError(
                    f"Strict mode: requested level {requested_level} "
                    f"was not reached (ran: {ar.levels_run})"
                )

    # Convert to SDK types
    discrepancy_records = []
    for d in ar.all_discrepancies:
        discrepancy_records.append(DiscrepancyRecord(
            type=d.type.value,
            severity=d.severity.value,
            source=d.source or "static",
            capability=d.description,
            file=d.evidence.split(":")[0] if ":" in d.evidence else "",
            line=int(d.evidence.split(":")[-1]) if d.evidence and d.evidence.split(":")[-1].isdigit() else 0,
            evidence=d.evidence,
            penalty={"minor": -5, "major": -10, "critical": -20}.get(d.severity.value, 0),
        ))

    levels_skipped = []
    levels_in_results = {lr.level for lr in ar.level_results}
    for lr in ar.level_results:
        if not lr.ran:
            levels_skipped.append({"level": str(lr.level), "reason": lr.skipped_reason})
    for lvl in (1, 2, 3, 4):
        if lvl not in levels_in_results:
            levels_skipped.append({"level": str(lvl), "reason": f"Above requested level ({ar.level_requested})"})

    extractor_warnings = []
    for lr in ar.level_results:
        for note in lr.notes:
            if "warning" in note.lower() or "not found" in note.lower():
                extractor_warnings.append(note)

    return AnalysisResult(
        trust_score=ar.trust_score,
        trust_label=ar.trust_label,
        levels_run=ar.levels_run,
        levels_skipped=levels_skipped,
        discrepancy_count=len(discrepancy_records),
        discrepancy_records=discrepancy_records,
        analysis_timestamp=ar.analyzed_at,
        extractor_warnings=extractor_warnings,
    )
