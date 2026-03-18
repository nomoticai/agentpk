"""API endpoint tests using FastAPI TestClient."""

import io
import time
import zipfile

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed (install with: pip install agentpk[api])")
from fastapi.testclient import TestClient

from agentpk.api.app import create_app


@pytest.fixture
def client():
    app = create_app(ui=False)
    return TestClient(app)


@pytest.fixture
def agent_zip(tmp_path, python_agent_fixture):
    """Create an archive of a valid agent directory for upload."""
    zip_path = tmp_path / "agent.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in python_agent_fixture.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(python_agent_fixture.parent))
    return zip_path


class TestHealth:
    def test_health(self, client):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_version(self, client):
        r = client.get("/v1/version")
        assert r.status_code == 200
        assert "version" in r.json()


class TestPackEndpoint:
    def test_submit_returns_202_with_job_id(self, client, agent_zip):
        with open(agent_zip, "rb") as f:
            r = client.post(
                "/v1/packages",
                files={"source": ("agent.zip", f, "application/zip")},
                data={"analyze": "false"},
            )
        assert r.status_code == 202
        data = r.json()
        assert "job_id" in data
        assert data["status"] in ["queued", "running", "complete"]

    def test_poll_job_status(self, client, agent_zip):
        with open(agent_zip, "rb") as f:
            r = client.post(
                "/v1/packages",
                files={"source": ("agent.zip", f, "application/zip")},
                data={"analyze": "false"},
            )
        job_id = r.json()["job_id"]

        # Poll until complete or failed (timeout after 10s in test)
        for _ in range(20):
            poll = client.get(f"/v1/packages/{job_id}")
            assert poll.status_code == 200
            if poll.json()["status"] in ("complete", "failed"):
                break
            time.sleep(0.5)

        final = client.get(f"/v1/packages/{job_id}").json()
        assert final["status"] == "complete"

    def test_nonexistent_job_returns_404(self, client):
        r = client.get("/v1/packages/nonexistent-job-id")
        assert r.status_code == 404

    def test_download_complete_job(self, client, agent_zip):
        with open(agent_zip, "rb") as f:
            r = client.post(
                "/v1/packages",
                files={"source": ("agent.zip", f, "application/zip")},
                data={"analyze": "false"},
            )
        job_id = r.json()["job_id"]

        for _ in range(20):
            if client.get(f"/v1/packages/{job_id}").json()["status"] == "complete":
                break
            time.sleep(0.5)

        dl = client.get(f"/v1/packages/{job_id}/download")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/octet-stream"

    def test_invalid_archive_returns_400(self, client):
        fake_zip = io.BytesIO(b"not a valid archive")
        r = client.post(
            "/v1/packages",
            files={"source": ("agent.zip", fake_zip, "application/zip")},
            data={"analyze": "false"},
        )
        assert r.status_code == 400
