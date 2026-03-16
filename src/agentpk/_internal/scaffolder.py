"""Internal scaffold implementation for SDK."""

from __future__ import annotations

from pathlib import Path

from agentpk.sdk import InitResult, AgentpkError


def run_init(
    name: str,
    dest: Path,
    runtime: str = "python",
    force: bool = False,
) -> InitResult:
    """Core init implementation."""
    from agentpk.scaffold import scaffold

    project_dir = dest / name
    if project_dir.exists() and not force:
        raise AgentpkError(f"Directory already exists: {project_dir}")

    files = scaffold(name, dest, runtime=runtime)

    return InitResult(
        project_dir=project_dir,
        runtime=runtime,
        files_created=[project_dir / f for f in files],
    )
