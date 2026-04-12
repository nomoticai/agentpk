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
from rich.prompt import Confirm, Prompt

from agentpk import __version__
from agentpk.constants import MANIFEST_FILENAME


console = Console()
err_console = Console(stderr=True)

# Use ASCII-safe characters that work on all Windows terminals
_PASS = "[bold green]OK[/bold green]"
_FAIL = "[red]X[/red]"
_WARN = "[yellow]![/yellow]"
_SEP = "-" * 60


def _mark(status: str) -> str:
    """Return a Rich-markup status string."""
    if status == "pass":
        return _PASS
    elif status == "fail":
        return _FAIL
    return _WARN


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


def _display_scanning(project: dict) -> None:
    """Display the project scanning section."""
    console.print()
    console.print(f"  [bold]agentpk[/bold]  |  {project['name']}")
    console.print()
    console.print(f"  [bold]-- Scanning project {_SEP}[/bold]")
    console.print(
        f"  {_mark('pass')}  [cyan]{project['name']}[/cyan] v{project['version']}"
    )
    parts = []
    if project["language"]:
        parts.append(project["language"].capitalize())
    if project["execution_type"]:
        parts.append(project["execution_type"])
    if project["tool_count"]:
        parts.append(f"{project['tool_count']} tools")
    if parts:
        console.print(f"     {' | '.join(parts)}")
    if project["tool_names"]:
        console.print(f"     {'  '.join(project['tool_names'][:6])}")


def _display_environment(env: dict) -> None:
    """Display the environment detection section."""
    llm = env.get("llm", {})
    docker = env.get("docker", {})

    console.print()
    console.print(f"  [bold]-- Environment {_SEP}[/bold]")

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
        mark = _mark("pass") if available else _mark("fail")
        if available:
            console.print(f"  {mark}  Level {level}  {name:<28}{status}")
        else:
            console.print(f"  {mark}  [dim]Level {level}  {name:<28}{status}[/dim]")


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

    console.print()
    console.print(f"  [bold]-- Code analysis {_SEP}[/bold]")
    console.print("  Run code analysis?  [dim][recommended][/dim]")
    console.print()

    # Build menu with sequential numbering
    _level_names = {1: "structural", 2: "static AST", 3: "LLM semantic", 4: "sandbox"}
    options: list[tuple[str, int | None]] = []

    # Highest available
    options.append((f"Yes -- Level {max_avail} (highest available)", max_avail))
    if max_avail > 2:
        options.append(("Yes -- Level 2 only (no API key used)", 2))
    if max_avail > 1:
        options.append(("Yes -- Level 1 only (structural only)", 1))
    options.append(("No -- skip analysis", None))

    valid_choices = []
    for i, (label, _level) in enumerate(options, 1):
        console.print(f"  {i}) {label}")
        valid_choices.append(str(i))

    console.print()
    choice = Prompt.ask("  Choose", choices=valid_choices, default="1")

    idx = int(choice) - 1
    return options[idx][1] if 0 <= idx < len(options) else None


def prompt_memory_bundle(env: dict) -> tuple[bool, list[str]]:
    """Ask whether to bundle an AIR memory snapshot.

    Returns (include_memory, components).
    """
    _ALL_COMPONENTS = ["audit", "fingerprint", "trust", "org_context", "knowledge_state"]

    console.print()
    console.print(f"  [bold]-- Memory snapshot {_SEP}[/bold]")
    console.print("  Bundle an AIR memory snapshot with this package?")
    console.print()
    console.print("  1) Yes -- all components")
    console.print("  2) Yes -- choose components")
    console.print("  3) No -- skip")
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
    _level_names = {1: "structural", 2: "static AST", 3: "LLM semantic", 4: "sandbox"}

    console.print()
    console.print(f"  [bold]-- Confirm {_SEP}[/bold]")
    console.print(
        f"  Ready to pack [cyan]{project['name']}[/cyan] "
        f"v{project['version']}"
    )

    if analysis_level:
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
    mark = _mark(status)
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

    if not project["valid"]:
        console.print()
        console.print(f"  {_mark('fail')}  {project['error']}")
        return 1

    _display_scanning(project)

    # 2. Detect environment
    env = detect_environment()
    _display_environment(env)

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
    console.print(f"  [bold]-- Packaging {_SEP}[/bold]")

    # Run analysis if requested
    analysis_block = None
    analysis_result = None
    if analysis_level:
        console.print(f"  >  Running analysis (level {analysis_level})...")
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
        console.print("  >  Building AIR bundle...")
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
                "_status": "stub -- install agentpk[memory] for full intelligence export",
            }
        _print_stage("AIR bundle", "pass", f"{len(memory_components)} components")

    # Pack
    console.print("  >  Packaging...")

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

    # 7. Summary
    console.print()
    console.print(f"  [bold]-- Summary {_SEP}[/bold]")

    if analysis_result:
        _print_stage(
            "Trust score",
            "pass",
            f"{analysis_result.trust_score}/100  {analysis_result.trust_label}",
        )
        disc_count = len(analysis_result.all_discrepancies)
        _print_stage(
            "Discrepancies",
            "pass" if disc_count == 0 else "warn",
            str(disc_count) if disc_count else "none",
        )

    if include_memory:
        _print_stage("AIR bundle", "pass", " | ".join(memory_components))

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
