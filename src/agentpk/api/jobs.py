from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Job:
    job_id: str
    status: str                  # queued | running | complete | failed
    created_at: float            # time.time()
    completed_at: float | None = None
    result: Any = None           # PackResult when complete
    error: str | None = None
    artifact_path: Path | None = None   # path to produced .agent file


class JobStore:
    """Thread-safe in-memory job store with TTL cleanup."""

    def __init__(self, ttl_seconds: int = 3600):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._start_cleanup_thread()

    def create(self) -> Job:
        job = Job(job_id=str(uuid.uuid4()), status="queued", created_at=time.time())
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)

    def _start_cleanup_thread(self) -> None:
        def cleanup():
            while True:
                time.sleep(300)  # check every 5 minutes
                cutoff = time.time() - self._ttl
                with self._lock:
                    expired = [jid for jid, j in self._jobs.items()
                               if j.created_at < cutoff]
                    for jid in expired:
                        job = self._jobs.pop(jid)
                        if job.artifact_path and job.artifact_path.exists():
                            job.artifact_path.unlink(missing_ok=True)
        t = threading.Thread(target=cleanup, daemon=True)
        t.start()


# Module-level singleton
_store = JobStore()

def get_store() -> JobStore:
    return _store
