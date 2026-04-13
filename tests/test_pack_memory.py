"""Tests for --memory / --memory-components (AIR bundle) feature."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

from agentpk.constants import MANIFEST_FILENAME
from agentpk.packer import pack


# ── helpers ────────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal valid agent project tree and return its root."""
    project = tmp_path / "my-agent"
    project.mkdir()
    (project / "src").mkdir()

    manifest = {
        "spec_version": "1.0",
        "name": "my-agent",
        "version": "0.1.0",
        "description": "A test agent.",
        "runtime": {
            "language": "python",
            "language_version": "3.11",
            "entry_point": "src/agent.py",
            "entry_function": "main",
            "dependencies": "requirements.txt",
        },
        "capabilities": {"tools": []},
        "execution": {"type": "on-demand"},
    }
    (project / MANIFEST_FILENAME).write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    (project / "src" / "agent.py").write_text(
        'def main():\n    print("hello")\n', encoding="utf-8"
    )
    (project / "requirements.txt").write_text("# none\n", encoding="utf-8")
    return project


def _read_packed_manifest(agent_path: Path) -> dict:
    """Extract and parse manifest.yaml from a packed .agent file."""
    with zipfile.ZipFile(agent_path, "r") as zf:
        return yaml.safe_load(zf.read(MANIFEST_FILENAME))


# ── tests ──────────────────────────────────────────────────────────────────


class TestAirBundleViaPacker:
    """Test air_bundle embedding through packer.pack() directly."""

    def test_pack_without_memory_has_no_air_key(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project)
        assert result.success and result.output_path is not None

        manifest = _read_packed_manifest(result.output_path)
        assert "air" not in manifest["_package"]

    def test_pack_with_air_bundle_embeds_it(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        air = {"air_version": "1.0", "test": True}
        result = pack(project, air_bundle=air)
        assert result.success and result.output_path is not None

        manifest = _read_packed_manifest(result.output_path)
        assert manifest["_package"]["air"]["air_version"] == "1.0"
        assert manifest["_package"]["air"]["test"] is True

    def test_air_bundle_preserves_all_fields(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        air = {
            "air_version": "1.0",
            "spec": "https://agentpk.io/specs/air/v1.0",
            "components": ["fingerprint", "trust"],
            "issuing_platform": "agentpk",
        }
        result = pack(project, air_bundle=air)
        assert result.success and result.output_path is not None

        manifest = _read_packed_manifest(result.output_path)
        embedded = manifest["_package"]["air"]
        assert embedded["components"] == ["fingerprint", "trust"]
        assert embedded["spec"] == "https://agentpk.io/specs/air/v1.0"
        assert embedded["issuing_platform"] == "agentpk"


class TestAirBundleViaCLI:
    """Test --memory and --memory-components via the CLI."""

    def test_memory_flag_embeds_stub(self, tmp_path: Path) -> None:
        """--memory without agentpk[memory] installed produces a stub."""
        from click.testing import CliRunner
        from agentpk.cli import cli

        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", str(project), "--memory",
            "--out-dir", str(tmp_path / "out"),
        ])
        assert result.exit_code == 0, result.output

        # Find the output .agent file
        out_dir = tmp_path / "out"
        agent_files = list(out_dir.glob("*.agent"))
        assert len(agent_files) == 1

        manifest = _read_packed_manifest(agent_files[0])
        air = manifest["_package"]["air"]
        assert air["air_version"] == "1.1"
        assert "stub" in air.get("_status", "")
        assert sorted(air["components"]) == [
            "audit", "compliance_state", "domain_model", "fingerprint",
            "interaction_patterns", "knowledge_state", "org_context", "trust"
        ]

    def test_memory_components_subset(self, tmp_path: Path) -> None:
        """--memory-components fingerprint,trust limits components."""
        from click.testing import CliRunner
        from agentpk.cli import cli

        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", str(project),
            "--memory", "--memory-components", "fingerprint,trust",
            "--out-dir", str(tmp_path / "out"),
        ])
        assert result.exit_code == 0, result.output

        out_dir = tmp_path / "out"
        agent_files = list(out_dir.glob("*.agent"))
        assert len(agent_files) == 1

        manifest = _read_packed_manifest(agent_files[0])
        air = manifest["_package"]["air"]
        assert air["components"] == ["fingerprint", "trust"]

    def test_unknown_component_exits_with_error(self, tmp_path: Path) -> None:
        """--memory-components with an unknown name exits 1."""
        from click.testing import CliRunner
        from agentpk.cli import cli

        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", str(project),
            "--memory", "--memory-components", "unknown_component",
        ])
        assert result.exit_code != 0
        assert "unknown" in result.output.lower() or "unknown" in (result.stderr or "").lower()

    def test_no_memory_flag_no_air_key(self, tmp_path: Path) -> None:
        """Without --memory, _package should not contain an air key."""
        from click.testing import CliRunner
        from agentpk.cli import cli

        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", str(project),
            "--out-dir", str(tmp_path / "out"),
        ])
        assert result.exit_code == 0, result.output

        out_dir = tmp_path / "out"
        agent_files = list(out_dir.glob("*.agent"))
        assert len(agent_files) == 1

        manifest = _read_packed_manifest(agent_files[0])
        assert "air" not in manifest["_package"]
