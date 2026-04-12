"""Interactive CLI mode for agentpk pack.

Provides environment detection, guided option selection, live progress,
and a clear summary. Interactive when invoked from a terminal, silent
when piped or when all flags are explicitly provided.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from agentpk import __version__
from agentpk.constants import MANIFEST_FILENAME


console = Console()
err_console = Console(stderr=True)

_CHECK = Text("\u2713", style="bold green")
_CROSS = Text("\u2717", style="red dim")
_WARN = Text("\u26a0", style="yellow")


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------


def detect_environment() -> dict:
    """Probe the environment and return detected capabilities.

    Returns a dict with keys: llm, docker, nomotic.
    """
    env: dict[str, Any] = {
        "llm": {"available": False, "provider": None, "key_name": None},
        "docker": {"available": False, "reason": None},
        "nomotic": {"available": False, "version": None},
    }

    # LLM detection (prefer Anthropic)
    if os.environ.get("ANTHROPIC_API_KEY"):
        env["llm"] = {
            "available": True,
            "provider": "anthropic",
            "key_name": "ANTHROPIC_API_KEY",
        }
    elif os.environ.get("OPENAI_API_KEY"):
        env["llm"] = {
            "available": True,
            "provider": "openai",
            "key_name": "OPENAI_API_KEY",
        }

    # Docker detection
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=2,
        )
        if proc.returncode == 0:
            env["docker"]["available"] = True
        else:
            stderr = proc.stderr.decode(errors="replace").strip()
            if "permission denied" in stderr.lower():
                env["docker"]["reason"] = "permission denied"
            elif "daemon" in stderr.lower() or "running" in stderr.lower():
                env["docker"]["reason"] = "daemon not running"
            else:
                env["docker"]["reason"] = "unavailable"
    except FileNotFoundError:
        env["docker"]["reason"] = "not installed"
    except subprocess.TimeoutExpired:
        env["docker"]["reason"] = "timed out"

    # Nomotic detection
    try:
        import nomotic  # type: ignore[import-untyped]
        env["nomotic"]["available"] = True
        env["nomotic"]["version"] = getattr(nomotic, "__version__", "unknown")
    except ImportError:
        pass

    return env


# ---------------------------------------------------------------------------
# Project scanning
# ---------------------------------------------------------------------------


def scan_project(source: Path) -> dict:
    """Read the manifest and return display-ready project metadata."""
    result: dict[str, Any] = {
        "name": "",
        "version": "",
        "language": "",
        "execution_type": "",
        "tool_count": 0,
        "tool_names": [],
        "valid": False,
        "error": None,
    }

    manifest_path = source / MANIFEST_FILENAME
    if not manifest_path.exists():
        result["error"] = f"{MANIFEST_FILENAME} not found"
        return result

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["error"] = f"Cannot parse manifest: {exc}"
        return result

    if not isinstance(data, dict):
        result["error"] = "Manifest is not a YAML mapping"
        return result

    result["name"] = data.get("name", "")
    result["version"] = data.get("version", "")
    runtime = data.get("runtime") or {}
    result["language"] = runtime.get("language", "")
    execution = data.get("execution") or {}
    result["execution_type"] = execution.get("type", "")
    tools = (data.get("capabilities") or {}).get("tools") or []
    result["tool_count"] = len(tools)
    result["tool_names"] = [t.get("id", "") for t in tools if isinstance(t, dict)]
    result["valid"] = True
    return result


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def is_interactive() -> bool:
    """True if stdin and stdout are both connected to a real terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def prompt_analysis_level(env: dict, max_level: int | None = None) -> int | None:
    """Ask the user which analysis level to run.

    Returns the chosen level (1-4) or None if the user declines.
    """
    llm = env.get("llm", {})
    docker = env.get("docker", {})

    # Determine max available level
    max_avail = 2
    if llm.get("available"):
        max_avail = 3
    if docker.get("available"):
        max_avail = 4
    if max_level is not None:
        max_avail = min(max_avail, max_level)

    # Display environment table
    console.print()
    console.print("  [bold]\u2500\u2500 Environment[/bold]")
    console.print()

    _levels = [
        (1, "Structural validation", "always available", True),
        (2, "Static AST analysis", "always available", True),
        (
            3,
            "LLM semantic analysis",
            f"{llm.get('key_name', '')} detected" if llm.get("available") else "no API key",
            llm.get("available", False),
        ),
        (
            4,
            "Sandbox execution",
            "available" if docker.get("available") else (docker.get("reason") or "unavailable"),
            docker.get("available", False),
        ),
    ]

    for level, name, status, available in _levels:
        mark = _CHECK if available else _CROSS
        style = "" if available else "[dim]"
        end_style = "[/dim]" if not available else ""
        console.print(f"  {mark}  Level {level}  {style}{name:<28}{status}{end_style}")

    console.print()
    console.print("  [bold]Run code analysis?[/bold]  [dim][recommended][/dim]")
    console.print()

    # Build choices
    choices = []
    if max_avail >= 3:
        choices.append(f"  1) Yes \u2014 Level {max_avail} (highest available)")
    if max_avail >= 2:
        choices.append("  2) Yes \u2014 Level 2 only (no API key used)")
    choices.append("  3) Yes \u2014 Level 1 only (structural only)")
    choices.append("  4) No \u2014 skip analysis")

    for c in choices:
        console.print(c)

    console.print()
    choice = Prompt.ask("  Choose", choices=["1", "2", "3", "4"], default="1")

    _level_map: dict[str, int | None] = {
        "1": max_avail if max_avail >= 3 else 2,
        "2": 2,
        "3": 1,
        "4": None,
    }
    return _level_map.get(choice)


def prompt_memory_bundle(env: dict) -> tuple[bool, list[str]]:
    """Ask whether to bundle an AIR memory snapshot.

    Returns (include_memory, components).
    """
    _ALL_COMPONENTS = ["audit", "fingerprint", "trust", "org_context", "knowledge_state"]

    console.print()
    console.print("  [bold]\u2500\u2500 Memory snapshot[/bold]")
    console.print()
    console.print("  Bundle an AIR memory snapshot with this package?")
    console.print()
    console.print("  1) Yes \u2014 all components")
    console.print("  2) Yes \u2014 choose components")
    console.print("  3) No \u2014 skip")
    console.print()

    choice = Prompt.ask("  Choose", choices=["1", "2", "3"], default="3")

    if choice == "3":
        return False, []

    if choice == "1":
        return True, _ALL_COMPONENTS

    # Let user pick components
    console.print()
    console.print("  Available components:")
    for i, comp in enumerate(_ALL_COMPONENTS, 1):
        console.print(f"    {i}) {comp}")
    console.print()

    selected = Prompt.ask(
        "  Enter component numbers (comma-separated)",
        default="1,2,3,4,5",
    )
    indices = [int(s.strip()) for s in selected.split(",") if s.strip().isdigit()]
    components = [_ALL_COMPONENTS[i - 1] for i in indices if 1 <= i <= len(_ALL_COMPONENTS)]
    return True, components


def prompt_confirm_pack(
    project: dict,
    analysis_level: int | None,
    memory: bool,
    memory_components: list[str] | None = None,
) -> bool:
    """Show a summary and ask for confirmation."""
    console.print()
    console.print("  [bold]\u2500\u2500 Confirm[/bold]")
    console.print()
    console.print(
        f"  Ready to pack [cyan]{project['name']}[/cyan] "
        f"v{project['version']}"
    )

    if analysis_level:
        _level_names = {1: "structural", 2: "static AST", 3: "LLM semantic", 4: "sandbox"}
        console.print(f"  Analysis:  Level {analysis_level} ({_level_names.get(analysis_level, '')})")
    else:
        console.print("  Analysis:  none")

    if memory and memory_components:
        console.print(f"  Memory:    {', '.join(memory_components)}")
    else:
        console.print("  Memory:    none")

    console.print()
    return Confirm.ask("  Proceed?", default=True)


# ---------------------------------------------------------------------------
# Progress display and pack orchestration
# ---------------------------------------------------------------------------


def _print_stage(label: str, status: str, detail: str = "") -> None:
    """Print a completed stage line."""
    if status == "pass":
        mark = _CHECK
    elif status == "fail":
        mark = _CROSS
    else:
        mark = _WARN
    suffix = f"  {detail}" if detail else ""
    console.print(f"  {mark}  {label}{suffix}")


def run_interactive_pack(
    source: Path,
    *,
    strict: bool = False,
    out_dir: Path | None = None,
    output: Path | None = None,
) -> int:
    """Orchestrate the full interactive pack flow.

    Returns exit code (0 for success, 1 for failure).
    """
    from agentpk.packer import pack as do_pack

    source = source.resolve()

    # 1. Scan project
    project = scan_project(source)
    console.print()
    console.print(f"  [bold]agentpk[/bold]  \u00b7  {project['name']}")
    console.print()
    console.print("  [bold]\u2500\u2500 Scanning project[/bold]")
    console.print()

    if not project["valid"]:
        console.print(f"  {_CROSS}  {project['error']}")
        return 1

    console.print(
        f"  {_CHECK}  [cyan]{project['name']}[/cyan] v{project['version']}"
    )
    parts = []
    if project["language"]:
        parts.append(project["language"].capitalize())
    if project["execution_type"]:
        parts.append(project["execution_type"])
    if project["tool_count"]:
        parts.append(f"{project['tool_count']} tools")
    if parts:
        console.print(f"     {' \u00b7 '.join(parts)}")
    if project["tool_names"]:
        console.print(f"     {' '.join(project['tool_names'][:6])}")

    # 2. Detect environment
    env = detect_environment()

    # 3. Prompt for analysis level
    analysis_level = prompt_analysis_level(env)

    # 4. Prompt for memory bundle
    include_memory, memory_components = prompt_memory_bundle(env)

    # 5. Confirm
    if not prompt_confirm_pack(project, analysis_level, include_memory, memory_components):
        console.print("\n  Cancelled.")
        return 1

    # 6. Execute the pipeline
    console.print()
    console.print("  [bold]\u2500\u2500 Packaging[/bold]")
    console.print()

    # Run analysis if requested
    analysis_block = None
    analysis_result = None
    if analysis_level:
        console.print(f"  \u2981  Running analysis (level {analysis_level})...")
        try:
            from agentpk.analyzer import analyze as run_analysis, build_analysis_block

            analysis_result = run_analysis(source, level=analysis_level, mode="verify")
            analysis_block = build_analysis_block(analysis_result)
            _print_stage(
                "Code analysis",
                "pass",
                f"score {analysis_result.trust_score}/100 ({analysis_result.trust_label})",
            )
        except Exception as exc:
            _print_stage("Code analysis", "fail", str(exc))
            if strict:
                return 1

    # Build AIR bundle if requested
    air_bundle = None
    if include_memory:
        console.print("  \u2981  Building AIR bundle...")
        import datetime as _dt

        requested = set(memory_components)
        try:
            from agentpk.air import build_air_bundle  # type: ignore[import-untyped]
            air_bundle = build_air_bundle(source, components=requested)
        except ImportError:
            air_bundle = {
                "air_version": "1.0",
                "spec": "https://agentpk.io/specs/air/v1.0",
                "components": sorted(requested),
                "export_timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "issuing_platform": "agentpk",
                "issuing_platform_version": __version__,
                "_status": "stub \u2014 install agentpk[memory] for full intelligence export",
            }
        _print_stage("AIR bundle", "pass", f"{len(memory_components)} components")

    # Pack
    console.print("  \u2981  Packaging...")

    output_path = output
    if output_path is None and out_dir is not None:
        output_path = None

    result = do_pack(
        source,
        output_path=output_path,
        analysis_block=analysis_block,
        air_bundle=air_bundle,
    )

    # Move to out_dir if needed
    if (
        result.success
        and out_dir is not None
        and output is None
        and result.output_path is not None
    ):
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        new_path = out_dir / result.output_path.name
        result.output_path.rename(new_path)
        result.output_path = new_path

    if not result.success:
        _print_stage("Packaging", "fail", "")
        for e in result.errors:
            err_console.print(f"  [red]{e.message}[/red]")
        return 1

    _print_stage(
        "Packaging",
        "pass",
        f"[cyan]{result.output_path.name}[/cyan]" if result.output_path else "",
    )

    # 7. Summary panel
    console.print()
    console.print("  [bold]\u2500\u2500 Summary[/bold]")
    console.print()

    if analysis_result:
        _print_stage(
            "Trust score",
            "pass",
            f"{analysis_result.trust_score}/100  {analysis_result.trust_label}",
        )
        disc_count = len(analysis_result.all_discrepancies)
        _print_stage("Discrepancies", "pass" if disc_count == 0 else "warn", str(disc_count) if disc_count else "none")

    if include_memory:
        _print_stage("AIR bundle", "pass", " \u00b7 ".join(memory_components))

    from agentpk.cli import _humanize_bytes

    size_str = _humanize_bytes(result.size_bytes)
    _print_stage(
        "Package",
        "pass",
        f"{result.output_path.name}  ({size_str})" if result.output_path else "",
    )

    console.print()
    console.print("  [dim]Next steps:[/dim]")
    if result.output_path:
        console.print(f"    agentpk inspect {result.output_path.name}")
        console.print(f"    agentpk validate {result.output_path.name}")
        console.print(f"    agentpk sign {result.output_path.name} --key my-key.pem")
    console.print()

    return 0
