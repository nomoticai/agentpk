"""Tests for the interactive CLI module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from agentpk.interactive import detect_environment, is_interactive, scan_project


# ── detect_environment ───────────────────────────────────────────────────────


class TestDetectEnvironment:
    """Test environment detection with mocked environment."""

    def test_no_api_keys_no_docker(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            env = detect_environment()
        assert env["llm"]["available"] is False
        assert env["llm"]["provider"] is None

    def test_anthropic_key_detected(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=True):
            env = detect_environment()
        assert env["llm"]["available"] is True
        assert env["llm"]["provider"] == "anthropic"
        assert env["llm"]["key_name"] == "ANTHROPIC_API_KEY"

    def test_openai_key_detected(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            env = detect_environment()
        assert env["llm"]["available"] is True
        assert env["llm"]["provider"] == "openai"

    def test_anthropic_preferred_over_openai(self) -> None:
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-a", "OPENAI_API_KEY": "sk-o"},
            clear=True,
        ):
            env = detect_environment()
        assert env["llm"]["provider"] == "anthropic"


# ── is_interactive ───────────────────────────────────────────────────────────


class TestIsInteractive:
    """Test TTY detection."""

    def test_returns_false_in_test_runner(self) -> None:
        # pytest typically redirects stdout, so this should be False
        assert is_interactive() is False


# ── scan_project ─────────────────────────────────────────────────────────────


class TestScanProject:
    """Test project scanning."""

    def test_valid_project(self, tmp_path: Path) -> None:
        manifest = {
            "spec_version": "1.0",
            "name": "test-agent",
            "version": "1.0.0",
            "description": "A test.",
            "runtime": {
                "language": "python",
                "language_version": "3.11",
                "entry_point": "agent.py",
            },
            "capabilities": {
                "tools": [
                    {"id": "read_data", "description": "Read", "scope": "read", "required": True},
                ]
            },
            "execution": {"type": "on-demand"},
        }
        (tmp_path / "manifest.yaml").write_text(
            yaml.dump(manifest), encoding="utf-8"
        )
        result = scan_project(tmp_path)
        assert result["valid"] is True
        assert result["name"] == "test-agent"
        assert result["version"] == "1.0.0"
        assert result["language"] == "python"
        assert result["tool_count"] == 1
        assert result["tool_names"] == ["read_data"]

    def test_missing_manifest(self, tmp_path: Path) -> None:
        result = scan_project(tmp_path)
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.yaml").write_text(
            "bad: yaml: [broken", encoding="utf-8"
        )
        result = scan_project(tmp_path)
        assert result["valid"] is False
        assert result["error"] is not None


# ── no-interactive flag ──────────────────────────────────────────────────────


class TestNoInteractiveFlag:
    """Test that --no-interactive skips interactive mode."""

    def test_pack_with_no_interactive_skips_prompts(self, tmp_path: Path) -> None:
        from click.testing import CliRunner
        from agentpk.cli import cli

        # Create a minimal valid project
        manifest = {
            "spec_version": "1.0",
            "name": "test-agent",
            "version": "1.0.0",
            "description": "A test.",
            "runtime": {
                "language": "python",
                "language_version": "3.11",
                "entry_point": "agent.py",
                "dependencies": "requirements.txt",
            },
            "execution": {"type": "on-demand"},
        }
        (tmp_path / "manifest.yaml").write_text(
            yaml.dump(manifest), encoding="utf-8"
        )
        (tmp_path / "agent.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "pack", str(tmp_path),
            "--no-interactive",
            "--out-dir", str(tmp_path / "out"),
        ])
        assert result.exit_code == 0, result.output
        # Should produce a packed file without any prompts
        out_files = list((tmp_path / "out").glob("*.agent"))
        assert len(out_files) == 1
