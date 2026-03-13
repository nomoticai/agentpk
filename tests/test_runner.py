"""Tests for the agent runner module (agentpk.runner)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from agentpk.cli import cli
from agentpk.packer import pack
from agentpk.runner import run_agent

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"


@pytest.fixture()
def packed_agent(tmp_path: Path) -> Path:
    """Pack fraud-detection example and return path to .agent file."""
    src = EXAMPLES_DIR / "fraud-detection"
    out = tmp_path / "fraud-detection-0.1.0.agent"
    result = pack(src, output_path=out)
    assert result.success
    return out


class TestRunAgent:
    """Unit tests for the run_agent function."""

    def test_dry_run_valid(self, packed_agent: Path) -> None:
        result = run_agent(packed_agent, dry_run=True)
        assert result.success is True

    def test_dry_run_invalid(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.agent"
        bad.write_text("not a zip")
        result = run_agent(bad, dry_run=True)
        assert result.success is False
        assert "Validation failed" in result.error

    def test_keep_flag(self, packed_agent: Path) -> None:
        result = run_agent(packed_agent, dry_run=True, keep=True)
        assert result.success is True
        assert result.temp_dir is not None
        assert result.temp_dir.exists()
        # Manual cleanup
        import shutil
        shutil.rmtree(result.temp_dir, ignore_errors=True)

    def test_actual_run(self, packed_agent: Path) -> None:
        """Actually execute the Python agent (it just prints)."""
        result = run_agent(packed_agent, keep=False)
        assert result.success is True
        assert result.exit_code == 0


class TestRunCommand:
    """CLI tests for agent run."""

    def test_dry_run_cli(self, packed_agent: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["run", str(packed_agent), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run passed" in result.output

    def test_nonexistent_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "/nonexistent/file.agent", "--dry-run"])
        assert result.exit_code != 0
