import shutil
"""Tests for the agent lister module (agentpk.lister)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentpk.cli import cli
from agentpk.lister import list_agents
from agentpk.packer import pack

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"


@pytest.fixture()
def packed_dir(tmp_path: Path) -> Path:
    """Create a directory with packed .agent files for testing."""
    out = tmp_path / "agents"
    out.mkdir()
    # Pack fraud-detection and data-pipeline
    for name in ("fraud-detection", "data-pipeline"):
        src = EXAMPLES_DIR / name
        result = pack(src)
        if result.output_path:
            shutil.copy2(result.output_path, out / result.output_path.name)
    return out


class TestListAgents:
    """Unit tests for the list_agents function."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        agents = list_agents(tmp_path)
        assert agents == []

    def test_finds_agent_files(self, packed_dir: Path) -> None:
        agents = list_agents(packed_dir)
        assert len(agents) >= 2
        names = {a.name for a in agents}
        assert "fraud-detection" in names
        assert "data-pipeline" in names

    def test_all_valid(self, packed_dir: Path) -> None:
        agents = list_agents(packed_dir)
        for a in agents:
            assert a.valid is True

    def test_invalid_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.agent"
        bad.write_text("not a valid archive")
        agents = list_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].valid is False
        assert agents[0].version == "[invalid]"

    def test_recursive_scan(self, packed_dir: Path) -> None:
        sub = packed_dir / "subdir"
        sub.mkdir()
        # Move one agent into subdir
        for f in packed_dir.glob("*.agent"):
            shutil.copy2(f, sub / f.name)
            break
        # Flat scan should find fewer
        flat = list_agents(packed_dir, recursive=False)
        rec = list_agents(packed_dir, recursive=True)
        assert len(rec) > len(flat)

    def test_sorted_by_name(self, packed_dir: Path) -> None:
        agents = list_agents(packed_dir)
        names = [a.name for a in agents]
        assert names == sorted(names)


class TestListCommand:
    """CLI tests for agent list."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["list", str(tmp_path)])
        assert result.exit_code == 0
        assert "No .agent files found" in result.output

    def test_json_output(self, packed_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["list", str(packed_dir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 2
        assert all("name" in d for d in data)

    def test_nonexistent_dir(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "/nonexistent/path/12345"])
        assert result.exit_code == 1
        assert "not found" in result.output or "does not exist" in result.output or "directory not found" in result.output
