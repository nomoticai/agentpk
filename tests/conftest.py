"""Shared test fixtures for agentpk tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def python_agent_fixture(tmp_path: Path) -> Path:
    """Create a minimal valid Python agent directory and return its path."""
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()

    (agent_dir / "manifest.yaml").write_text(
        'spec_version: "1.0"\n'
        "name: test-agent\n"
        'version: "1.0.0"\n'
        'description: "A minimal test agent."\n'
        "runtime:\n"
        "  language: python\n"
        '  language_version: "3.11"\n'
        "  entry_point: agent.py\n"
        "  dependencies: requirements.txt\n"
        "execution:\n"
        "  type: on-demand\n",
        encoding="utf-8",
    )

    (agent_dir / "agent.py").write_text(
        "# placeholder agent\ndef main(): pass\n",
        encoding="utf-8",
    )

    (agent_dir / "requirements.txt").write_text("", encoding="utf-8")

    return agent_dir
