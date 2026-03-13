"""Scan a directory for .agent files and summarize them."""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from agentpk.constants import AGENT_EXTENSION, MANIFEST_FILENAME


@dataclass
class AgentSummary:
    """Summary of a single .agent file."""

    name: str
    version: str
    execution_type: str
    tool_count: int
    packaged_at: str
    path: Path
    valid: bool
    error: Optional[str] = None


def _read_summary(agent_path: Path) -> AgentSummary:
    """Read an .agent file and extract its summary metadata."""
    try:
        with zipfile.ZipFile(agent_path, "r") as zf:
            if MANIFEST_FILENAME not in zf.namelist():
                return AgentSummary(
                    name=agent_path.stem,
                    version="[invalid]",
                    execution_type="",
                    tool_count=0,
                    packaged_at="",
                    path=agent_path,
                    valid=False,
                    error="manifest.yaml not found in archive",
                )
            raw = zf.read(MANIFEST_FILENAME).decode("utf-8")

        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return AgentSummary(
                name=agent_path.stem,
                version="[invalid]",
                execution_type="",
                tool_count=0,
                packaged_at="",
                path=agent_path,
                valid=False,
                error="manifest.yaml is not a YAML mapping",
            )

        name = data.get("name", agent_path.stem)
        version = data.get("version", "unknown")
        execution = data.get("execution") or {}
        exec_type = execution.get("type", "unknown") if isinstance(execution, dict) else "unknown"
        capabilities = data.get("capabilities") or {}
        tools = capabilities.get("tools") or [] if isinstance(capabilities, dict) else []
        tool_count = len(tools) if isinstance(tools, list) else 0
        pkg = data.get("_package") or {}
        packaged_at = pkg.get("packaged_at", "") if isinstance(pkg, dict) else ""

        return AgentSummary(
            name=name,
            version=version,
            execution_type=exec_type,
            tool_count=tool_count,
            packaged_at=packaged_at,
            path=agent_path,
            valid=True,
        )

    except zipfile.BadZipFile:
        return AgentSummary(
            name=agent_path.stem,
            version="[invalid]",
            execution_type="",
            tool_count=0,
            packaged_at="",
            path=agent_path,
            valid=False,
            error="not a valid ZIP archive",
        )
    except Exception as exc:
        return AgentSummary(
            name=agent_path.stem,
            version="[invalid]",
            execution_type="",
            tool_count=0,
            packaged_at="",
            path=agent_path,
            valid=False,
            error=str(exc),
        )


def list_agents(directory: Path, *, recursive: bool = False) -> list[AgentSummary]:
    """Scan *directory* for .agent files and return a summary of each.

    Args:
        directory: Directory to scan.
        recursive: If True, scan subdirectories as well.

    Returns:
        List of :class:`AgentSummary` objects sorted by name.
    """
    pattern = f"**/*{AGENT_EXTENSION}" if recursive else f"*{AGENT_EXTENSION}"
    agent_files = sorted(directory.glob(pattern))

    return sorted(
        (_read_summary(f) for f in agent_files),
        key=lambda s: s.name,
    )
