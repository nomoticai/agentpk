from __future__ import annotations

import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agentpk import pack as sdk_pack, AgentpkError, ManifestError
from agentpk.api.jobs import get_store
from agentpk.api.models import PackOptions, PackResponse, AnalysisResponse, DiscrepancyResponse

router = APIRouter()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_analysis_response(analysis) -> AnalysisResponse | None:
    if analysis is None:
        return None
    return AnalysisResponse(
        trust_score=analysis.trust_score,
        trust_label=analysis.trust_label,
        levels_run=analysis.levels_run,
        levels_skipped=analysis.levels_skipped,
        discrepancy_count=analysis.discrepancy_count,
        discrepancy_records=[
            DiscrepancyResponse(
                type=d.type,
                severity=d.severity,
                source=d.source,
                capability=d.capability,
                file=d.file,
                line=d.line,
                evidence=d.evidence,
                penalty=d.penalty,
                requires_review=d.requires_review,
            )
            for d in analysis.discrepancy_records
        ],
        analysis_timestamp=analysis.analysis_timestamp,
        extractor_warnings=analysis.extractor_warnings,
    )


def _run_pack_job(job_id: str, source_dir: Path, out_dir: Path, options: PackOptions) -> None:
    """Runs in a background thread."""
    store = get_store()
    store.update(job_id, status="running")

    try:
        result = sdk_pack(
            source_dir,
            out_dir=out_dir,
            analyze=options.analyze,
            levels=options.levels,
            strict=options.strict,
            sandbox_timeout=options.sandbox_timeout,
        )
        store.update(
            job_id,
            status="complete",
            completed_at=time.time(),
            result=result,
            artifact_path=result.package_path,
        )
    except (AgentpkError, ManifestError) as e:
        store.update(job_id, status="failed", completed_at=time.time(), error=str(e))
    except Exception as e:
        store.update(job_id, status="failed", completed_at=time.time(),
                     error=f"Unexpected error: {e}")
    finally:
        # Clean up temp source dir (artifact_path is in out_dir, separate)
        shutil.rmtree(source_dir, ignore_errors=True)


@router.post("/v1/packages", response_model=PackResponse, status_code=202)
async def create_package(
    source: UploadFile = File(..., description="ZIP archive of the agent directory"),
    analyze: bool = Form(False),
    levels: str = Form("", description="Comma-separated level numbers, e.g. '1,2,3'"),
    strict: bool = Form(False),
    sandbox_timeout: int = Form(30),
):
    """
    Submit an agent directory (as a ZIP) for packaging.

    Returns a job_id immediately. Poll GET /v1/packages/{job_id} for status.
    When status is 'complete', download from GET /v1/packages/{job_id}/download.
    """
    # Parse levels
    level_list = None
    if levels.strip():
        try:
            level_list = [int(x.strip()) for x in levels.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(400, "levels must be comma-separated integers")

    options = PackOptions(
        analyze=analyze,
        levels=level_list,
        strict=strict,
        sandbox_timeout=sandbox_timeout,
    )

    # Save uploaded ZIP to temp location
    tmp_upload = tempfile.mktemp(suffix=".zip")
    try:
        content = await source.read()
        with open(tmp_upload, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    # Extract ZIP to temp source dir
    source_dir = Path(tempfile.mkdtemp(prefix="agentpk_src_"))
    out_dir = Path(tempfile.mkdtemp(prefix="agentpk_out_"))

    try:
        shutil.unpack_archive(tmp_upload, source_dir, "zip")
    except Exception as e:
        shutil.rmtree(source_dir, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(400, f"Invalid ZIP archive: {e}")
    finally:
        Path(tmp_upload).unlink(missing_ok=True)

    # If the ZIP contains a single top-level directory, use that as source
    contents = list(source_dir.iterdir())
    if len(contents) == 1 and contents[0].is_dir():
        source_dir = contents[0]

    # Create job and start background thread
    store = get_store()
    job = store.create()
    thread = threading.Thread(
        target=_run_pack_job,
        args=(job.job_id, source_dir, out_dir, options),
        daemon=True,
    )
    thread.start()

    return PackResponse(job_id=job.job_id, status="queued")


@router.get("/v1/packages/{job_id}", response_model=PackResponse)
def get_package(job_id: str):
    """Poll job status. When status='complete', result fields are populated."""
    store = get_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    if job.status == "failed":
        return PackResponse(job_id=job_id, status="failed", error=job.error)

    if job.status != "complete" or job.result is None:
        return PackResponse(job_id=job_id, status=job.status)

    result = job.result
    return PackResponse(
        job_id=job_id,
        status="complete",
        package_filename=result.package_path.name if result.package_path else None,
        manifest_hash=result.manifest_hash,
        packaged_at=result.packaged_at,
        source_file_count=result.source_file_count,
        analysis=_build_analysis_response(result.analysis),
        warnings=result.warnings,
    )


@router.get("/v1/packages/{job_id}/download")
def download_package(job_id: str):
    """Download the completed .agent archive."""
    store = get_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job.status != "complete":
        raise HTTPException(409, f"Job not complete (status: {job.status})")
    if job.artifact_path is None or not job.artifact_path.exists():
        raise HTTPException(410, "Artifact has expired or was deleted")

    return FileResponse(
        path=job.artifact_path,
        filename=job.artifact_path.name,
        media_type="application/octet-stream",
    )


@router.get("/v1/capabilities")
def get_capabilities():
    """
    Returns what analysis levels are available in the current environment.
    Used by the UI to show/disable options intelligently.
    """
    import os

    anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    has_llm = anthropic_key or openai_key

    # Determine which provider is configured
    if anthropic_key:
        llm_provider = "Anthropic (Claude)"
    elif openai_key:
        llm_provider = "OpenAI"
    else:
        llm_provider = None

    return {
        "level3_available": has_llm,
        "llm_provider": llm_provider,
        "level4_available": True,  # sandbox availability checked at pack time
    }


@router.get("/v1/health")
def health():
    return {"status": "ok"}


@router.get("/v1/version")
def version():
    from agentpk import __version__
    return {"version": __version__, "api_version": "1"}
