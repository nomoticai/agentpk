"""Execute a packed .agent file as a subprocess."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agentpk.constants import MANIFEST_FILENAME
from agentpk.manifest import load_manifest
from agentpk.models import AgentManifest
from agentpk.packer import unpack
from agentpk.validator import validate_package


@dataclass
class RunResult:
    """Outcome of executing an agent."""

    success: bool
    exit_code: int = 0
    error: str = ""
    temp_dir: Optional[Path] = None


# Languages we can directly execute
_RUNTIME_COMMANDS = {
    "python": "python",
    "nodejs": "node",
    "typescript": "npx",
}

_TYPESCRIPT_ARGS = ["ts-node"]


def _build_command(
    manifest: AgentManifest,
    extract_dir: Path,
) -> tuple[list[str], Optional[Path]]:
    """Build the subprocess command and optional wrapper script path.

    Returns (command_parts, wrapper_path_or_None).
    """
    lang = manifest.runtime.language
    entry_point = manifest.runtime.entry_point
    entry_function = manifest.runtime.entry_function

    if lang not in _RUNTIME_COMMANDS:
        raise ValueError(
            f"Runtime '{lang}' is not directly executable by agentpk. "
            f"Extract and run manually."
        )

    interpreter = _RUNTIME_COMMANDS[lang]
    wrapper_path: Optional[Path] = None

    if lang == "python" and entry_function and entry_function != "__main__":
        # Generate a thin wrapper script that imports and calls the function
        wrapper_path = extract_dir / "_agentpk_runner.py"
        # Compute the module name from entry_point (e.g. src/agent.py -> src.agent)
        module_path = entry_point.replace("/", ".").replace("\\", ".")
        if module_path.endswith(".py"):
            module_path = module_path[:-3]

        wrapper_code = textwrap.dedent(f"""\
            import sys
            sys.path.insert(0, {str(extract_dir)!r})
            from {module_path} import {entry_function}
            {entry_function}()
        """)
        wrapper_path.write_text(wrapper_code, encoding="utf-8")
        return [interpreter, str(wrapper_path)], wrapper_path

    if lang == "typescript":
        return [interpreter] + _TYPESCRIPT_ARGS + [str(extract_dir / entry_point)], None

    return [interpreter, str(extract_dir / entry_point)], None


def run_agent(
    package_path: Path,
    *,
    agent_args: list[str] | None = None,
    keep: bool = False,
    dry_run: bool = False,
    env_vars: dict[str, str] | None = None,
) -> RunResult:
    """Validate, extract, and execute a packed .agent file.

    Args:
        package_path: Path to the .agent file.
        agent_args: Arguments to pass to the agent subprocess.
        keep: If True, do not delete the temp directory after execution.
        dry_run: If True, validate and extract but do not execute.
        env_vars: Extra environment variables for the subprocess.

    Returns:
        A :class:`RunResult` with the outcome.
    """
    package_path = package_path.resolve()

    # Validate
    vr = validate_package(package_path)
    if not vr.is_valid:
        msgs = "; ".join(e.message for e in vr.errors)
        return RunResult(success=False, error=f"Validation failed: {msgs}")

    # Extract to temp directory
    tmp = tempfile.mkdtemp(prefix="agentpk-run-")
    tmp_path = Path(tmp)

    try:
        unpack(package_path, tmp_path)

        # Load manifest
        manifest = load_manifest(tmp_path / MANIFEST_FILENAME)

        if dry_run:
            if not keep:
                shutil.rmtree(tmp_path, ignore_errors=True)
                return RunResult(success=True, exit_code=0)
            return RunResult(success=True, exit_code=0, temp_dir=tmp_path)

        # Build command
        try:
            cmd, wrapper = _build_command(manifest, tmp_path)
        except ValueError as exc:
            if not keep:
                shutil.rmtree(tmp_path, ignore_errors=True)
            return RunResult(success=False, error=str(exc))

        if agent_args:
            cmd.extend(agent_args)

        # Build environment
        run_env = os.environ.copy()
        if env_vars:
            run_env.update(env_vars)

        # Execute
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(tmp_path),
                env=run_env,
            )
            return RunResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode,
                temp_dir=tmp_path if keep else None,
            )
        except FileNotFoundError:
            return RunResult(
                success=False,
                error=f"Interpreter not found: {cmd[0]}",
                temp_dir=tmp_path if keep else None,
            )
        except KeyboardInterrupt:
            return RunResult(
                success=False,
                exit_code=130,
                error="Interrupted by user",
                temp_dir=tmp_path if keep else None,
            )
        finally:
            # Clean up wrapper
            if wrapper and wrapper.exists():
                wrapper.unlink(missing_ok=True)

    finally:
        if not keep:
            shutil.rmtree(tmp_path, ignore_errors=True)
