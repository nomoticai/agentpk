from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class PackOptions(BaseModel):
    analyze: bool = False
    levels: list[int] | None = None
    strict: bool = False
    sandbox_timeout: int = 30


class JobStatus(BaseModel):
    job_id: str
    status: str          # queued | running | complete | failed
    created_at: str
    completed_at: str | None = None
    error: str | None = None


class DiscrepancyResponse(BaseModel):
    type: str
    severity: str
    source: str
    capability: str
    file: str
    line: int
    evidence: str
    penalty: float
    requires_review: bool


class AnalysisResponse(BaseModel):
    trust_score: int
    trust_label: str
    levels_run: list[int]
    levels_skipped: list[dict[str, str]]
    discrepancy_count: int
    discrepancy_records: list[DiscrepancyResponse]
    analysis_timestamp: str
    extractor_warnings: list[str]


class PackResponse(BaseModel):
    job_id: str
    status: str
    package_filename: str | None = None
    manifest_hash: str | None = None
    packaged_at: str | None = None
    source_file_count: int | None = None
    analysis: AnalysisResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
