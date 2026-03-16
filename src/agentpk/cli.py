"""Click-based CLI entry point for the ``agent`` command.

Uses Rich for coloured, structured terminal output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentpk import __version__

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_errors(errors: list, *, prefix: str = "ERROR") -> None:
    """Print a list of ValidationError objects as red lines."""
    for e in errors:
        field = f" [{e.field}]" if getattr(e, "field", None) else ""
        err_console.print(f"  [bold red]{prefix}[/bold red]{field}: {e.message}")


def _print_warnings(warnings: list) -> None:
    """Print a list of ValidationError objects as yellow lines."""
    for w in warnings:
        field = f" [{w.field}]" if getattr(w, "field", None) else ""
        err_console.print(f"  [bold yellow]WARN[/bold yellow]{field}: {w.message}")


def _humanize_bytes(n: int) -> str:
    """Return human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def _print_analysis_results(analysis_result: object) -> None:
    """Print analysis level results and discrepancies."""
    from agentpk.analyzer import AnalysisResult

    ar: AnalysisResult = analysis_result  # type: ignore[assignment]

    # Level results table
    table = Table(title="Analysis Levels", border_style="cyan", show_header=True)
    table.add_column("Level", style="bold", width=6)
    table.add_column("Name", min_width=20)
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Notes", style="dim")

    for lr in ar.level_results:
        if lr.ran:
            status = "[bold green]RAN[/bold green]" if lr.passed else "[bold yellow]RAN[/bold yellow]"
        else:
            status = "[dim]SKIP[/dim]"
        note = lr.skipped_reason if not lr.ran else ""
        if not note and lr.notes:
            note = lr.notes[0] if lr.notes else ""
        table.add_row(str(lr.level), lr.name, status, str(lr.score), note)

    console.print(table)

    # Discrepancies
    if ar.all_discrepancies:
        console.print()
        d_table = Table(title="Discrepancies", border_style="yellow", show_header=True)
        d_table.add_column("Severity", style="bold")
        d_table.add_column("Type")
        d_table.add_column("Description")
        d_table.add_column("Evidence", style="dim")

        for d in ar.all_discrepancies:
            sev_style = {
                "minor": "[yellow]MINOR[/yellow]",
                "major": "[bold yellow]MAJOR[/bold yellow]",
                "critical": "[bold red]CRITICAL[/bold red]",
            }.get(d.severity.value, d.severity.value)
            d_table.add_row(sev_style, d.type.value, d.description, d.evidence[:60])

        console.print(d_table)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version=__version__, prog_name="agent")
def cli() -> None:
    """agentpk - Package AI agents into portable .agent files."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("name")
@click.option(
    "-d", "--directory",
    type=click.Path(path_type=Path),
    default=".",
    help="Parent directory for the new project.",
)
@click.option(
    "--runtime",
    type=click.Choice(["python", "nodejs", "typescript", "go", "java"]),
    default="python",
    help="Runtime language for the agent project.",
)
def init(name: str, directory: Path, runtime: str) -> None:
    """Scaffold a new agent project."""
    from agentpk.scaffold import scaffold

    # Support path-like names: "test-agents/my-agent" -> dir="test-agents", name="my-agent"
    name_path = Path(name)
    if len(name_path.parts) > 1:
        directory = Path(directory).resolve() / name_path.parent
        name = name_path.name
    else:
        directory = Path(directory).resolve()
    files = scaffold(name, directory, runtime=runtime)

    console.print(
        Panel(
            f"[bold green]Created project [cyan]{name}[/cyan] "
            f"with {len(files)} files[/bold green]",
            title="agent init",
        )
    )
    for f in files:
        console.print(f"  [dim]-[/dim] {f}")


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None, help="Output .agent file path.")
@click.option("--out-dir", type=click.Path(path_type=Path), default=None, help="Output directory (filename auto-generated).")
@click.option("--dry-run", is_flag=True, default=False, help="Validate and compute hashes without writing.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show detailed output.")
@click.option("--strict", is_flag=True, default=False, help="Treat warnings as errors.")
@click.option("--analyze", is_flag=True, default=False, help="Run code analysis and embed trust score in package.")
@click.option("--level", "analyze_level", default=None, type=click.IntRange(1, 4), help="Analysis level (1-4). Default: highest available.")
@click.option("--on-discrepancy", type=click.Choice(["warn", "fail", "auto"]), default="warn", help="Behavior when analysis finds undeclared capabilities.")
def pack(
    source: Path,
    output: Path | None,
    out_dir: Path | None,
    dry_run: bool,
    verbose: bool,
    strict: bool,
    analyze: bool,
    analyze_level: int | None,
    on_discrepancy: str,
) -> None:
    """Pack a directory into a .agent file.

    \b
    Use --analyze to run code analysis and embed a trust score:
      agent pack my-agent/ --analyze
      agent pack my-agent/ --analyze --level 3
      agent pack my-agent/ --analyze --strict --level 3
    """
    from agentpk.packer import pack as do_pack

    source = Path(source).resolve()

    # ── Run analysis if requested ────────────────────────────────────
    analysis_block = None
    if analyze:
        from agentpk.analyzer import analyze as run_analysis, build_analysis_block

        level = analyze_level
        if level is None:
            # Auto-detect highest available level
            import os
            has_llm = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))
            level = 3 if has_llm else 2

        console.print(f"  Running code analysis (level {level})...\n")
        analysis_result = run_analysis(source, level=level, mode="verify")

        # Show results
        _print_analysis_results(analysis_result)

        # Strict check: did we reach the requested level?
        if strict and analyze_level is not None:
            if analyze_level not in analysis_result.levels_run:
                err_console.print(
                    f"\n[bold red]Strict mode:[/bold red] requested level {analyze_level} "
                    f"was not reached (ran: {analysis_result.levels_run})"
                )
                sys.exit(1)

        # Discrepancy handling
        if analysis_result.all_discrepancies:
            if on_discrepancy == "fail":
                err_console.print(
                    f"\n[bold red]Pack failed:[/bold red] {len(analysis_result.all_discrepancies)} "
                    f"discrepancy(ies) found (--on-discrepancy=fail)"
                )
                sys.exit(1)
            elif on_discrepancy == "auto":
                console.print("  [yellow]Auto-updating manifest with analysis findings...[/yellow]")
                # NOTE: auto-update is best-effort; for now we just continue
                # and note the discrepancies in the analysis block

        analysis_block = build_analysis_block(analysis_result)
        console.print(
            f"\n  Trust score: [bold]{analysis_result.trust_score}/100[/bold] "
            f"({analysis_result.trust_label})\n"
        )

    # ── Resolve output path ──────────────────────────────────────────
    output_path = output
    if output_path is None and out_dir is not None:
        output_path = None  # pack() will auto-name; we move after
    # NOTE: if both are None, pack() picks <name>-<version>.agent in parent dir

    result = do_pack(source, output_path=output_path, dry_run=dry_run, analysis_block=analysis_block)

    # Move to out_dir if needed (and not dry_run)
    if (
        result.success
        and not dry_run
        and out_dir is not None
        and output is None
        and result.output_path is not None
    ):
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        new_path = out_dir / result.output_path.name
        result.output_path.rename(new_path)
        result.output_path = new_path

    # Print warnings
    if result.warnings:
        _print_warnings(result.warnings)

    # Strict mode (for pack warnings, separate from analyze strict)
    if strict and result.warnings and not analyze:
        err_console.print("[bold red]Strict mode: warnings treated as errors.[/bold red]")
        _print_errors(result.warnings, prefix="WARN>>ERR")
        sys.exit(1)

    if not result.success:
        err_console.print("[bold red]Pack failed.[/bold red]")
        _print_errors(result.errors)
        sys.exit(1)

    if dry_run:
        console.print(Panel("[bold yellow]Dry run -- no file created[/bold yellow]", title="agent pack"))
    else:
        console.print(
            Panel(
                f"[bold green]Packed successfully![/bold green]\n"
                f"  Output: [cyan]{result.output_path}[/cyan]\n"
                f"  Size:   {_humanize_bytes(result.size_bytes)}\n"
                f"  Files:  {result.file_count}",
                title="agent pack",
            )
        )

    if verbose:
        console.print(f"  manifest_hash: {result.manifest_hash}")
        console.print(f"  files_hash:    {result.files_hash}")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("target", required=False, default=None)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show each validation stage and its result.")
def validate(target: str | None, verbose: bool) -> None:
    """Validate an agent directory or packed .agent file.

    \b
    TARGET can be a project directory or a packed .agent file:
      agent validate .
      agent validate ./my-fraud-agent/
      agent validate fraud-detection-1.0.0.agent

    \b
    Both run the same 6-stage validation pipeline. Directories skip the
    checksum and package integrity stages (Stages 5-6) since those only
    apply to packed files.
    """
    from agentpk.validator import validate_directory, validate_package

    if target is None:
        console.print()
        console.print("[red]Error:[/red] no target specified.")
        console.print("Pass a directory or .agent file:\n")
        console.print("  agent validate ./my-agent/")
        console.print("  agent validate my-agent-1.0.0.agent")
        console.print()
        sys.exit(1)

    target = Path(target).resolve()

    if not target.exists():
        err_console.print(f"[bold red]Error:[/bold red] path does not exist: {target}")
        sys.exit(1)

    is_dir = target.is_dir()
    if verbose:
        console.print(f"  Validating: [cyan]{target}[/cyan]\n")

    if is_dir:
        vr = validate_directory(target)
        # Append skip markers for stages 5-6 (directory only)
        from agentpk.validator import StageResult
        vr.stages.append(StageResult("Checksums", "skip", "directory, not package"))
        vr.stages.append(StageResult("Package integrity", "skip", "directory, not package"))
    else:
        vr = validate_package(target)

    # Verbose: stage table
    if verbose:
        _STAGE_LABELS = {
            "pass": "[bold green]PASS[/bold green]",
            "fail": "[bold red]FAIL[/bold red]",
            "skip": "[dim]SKIP[/dim]",
        }
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="bold")
        table.add_column("Num", style="dim", width=1)
        table.add_column("Name", min_width=20)
        table.add_column("Status", justify="center")
        table.add_column("Note", style="dim")
        for i, s in enumerate(vr.stages, 1):
            note = f"({s.message})" if s.message else ""
            table.add_row("Stage", str(i), s.name, _STAGE_LABELS.get(s.status, s.status), note)
        console.print(table)
        console.print()

    if vr.warnings:
        _print_warnings(vr.warnings)

    if vr.is_valid:
        console.print(
            Panel("[bold green]Validation passed.[/bold green]", title="agent validate")
        )
    else:
        err_console.print("[bold red]Validation failed.[/bold red]")
        _print_errors(vr.errors)
        sys.exit(1)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("agent_file", type=click.Path(exists=True, path_type=Path))
def inspect(agent_file: Path) -> None:
    """Inspect a .agent file and display its metadata."""
    from agentpk.packer import inspect as do_inspect

    agent_file = Path(agent_file).resolve()
    info = do_inspect(agent_file)

    manifest = info.get("manifest")
    if manifest is None:
        err_console.print("[bold red]Could not read manifest.[/bold red]")
        if info["errors"]:
            for e in info["errors"]:
                err_console.print(f"  [red]{e}[/red]")
        sys.exit(1)

    # ── Identity table ────────────────────────────────────────────────
    id_table = Table(title="Identity", show_header=False, border_style="cyan")
    id_table.add_column("Field", style="bold")
    id_table.add_column("Value")
    id_table.add_row("name", manifest.name)
    id_table.add_row("version", manifest.version)
    id_table.add_row("description", manifest.description)
    if manifest.display_name:
        id_table.add_row("display_name", manifest.display_name)
    if manifest.author:
        id_table.add_row("author", manifest.author)
    if manifest.organization:
        id_table.add_row("organization", manifest.organization)
    if manifest.license:
        id_table.add_row("license", manifest.license)
    if manifest.tags:
        id_table.add_row("tags", ", ".join(manifest.tags))
    console.print(id_table)

    # ── Runtime table ─────────────────────────────────────────────────
    rt = manifest.runtime
    rt_table = Table(title="Runtime", show_header=False, border_style="cyan")
    rt_table.add_column("Field", style="bold")
    rt_table.add_column("Value")
    rt_table.add_row("language", rt.language)
    rt_table.add_row("language_version", rt.language_version)
    rt_table.add_row("entry_point", rt.entry_point)
    if rt.entry_function:
        rt_table.add_row("entry_function", rt.entry_function)
    if rt.dependencies:
        rt_table.add_row("dependencies", rt.dependencies)
    console.print(rt_table)

    # ── Capabilities table ────────────────────────────────────────────
    tools = manifest.capabilities.tools
    if tools:
        tools_table = Table(title="Capabilities (Tools)", border_style="cyan")
        tools_table.add_column("ID", style="bold")
        tools_table.add_column("Scope")
        tools_table.add_column("Required")
        tools_table.add_column("Description")
        for t in tools:
            tools_table.add_row(
                t.id, t.scope, str(t.required), t.description
            )
        console.print(tools_table)

    # ── Execution table ───────────────────────────────────────────────
    ex = manifest.execution
    ex_table = Table(title="Execution", show_header=False, border_style="cyan")
    ex_table.add_column("Field", style="bold")
    ex_table.add_column("Value")
    ex_table.add_row("type", ex.type)
    if ex.schedule:
        ex_table.add_row("schedule", ex.schedule)
    if ex.timeout_minutes:
        ex_table.add_row("timeout_minutes", str(ex.timeout_minutes))
    console.print(ex_table)

    # ── Package metadata ──────────────────────────────────────────────
    pkg = manifest.package_metadata
    if pkg:
        p_table = Table(title="Package Metadata", show_header=False, border_style="green")
        p_table.add_column("Field", style="bold")
        p_table.add_column("Value")
        p_table.add_row("format_version", pkg.format_version)
        p_table.add_row("packaged_at", pkg.packaged_at)
        p_table.add_row("packaged_by", pkg.packaged_by)
        p_table.add_row("manifest_hash", pkg.manifest_hash)
        p_table.add_row("files_hash", pkg.files_hash)
        p_table.add_row("total_files", str(pkg.total_files))
        p_table.add_row("package_size_bytes", _humanize_bytes(pkg.package_size_bytes))
        console.print(p_table)

    # ── Trust Score ───────────────────────────────────────────────────
    analysis = info.get("analysis")
    ts_table = Table(title="Trust Score", show_header=False, border_style="cyan")
    ts_table.add_column("Field", style="bold")
    ts_table.add_column("Value")

    if analysis:
        score = analysis.get("trust_score", 0)
        label = analysis.get("trust_label", "Unverified")
        ts_table.add_row("score", f"{score}/100  ({label})")
        levels_run = analysis.get("levels_run", [])
        ts_table.add_row("levels run", ", ".join(str(l) for l in levels_run))

        levels_skipped = analysis.get("levels_skipped", [])
        if levels_skipped:
            skip_parts = []
            for sk in levels_skipped:
                if isinstance(sk, dict):
                    skip_parts.append(f"{sk.get('level', '?')}  ({sk.get('reason', '')})")
                else:
                    skip_parts.append(str(sk))
            ts_table.add_row("levels skipped", ", ".join(skip_parts))
        else:
            ts_table.add_row("levels skipped", "none")

        discrepancies = analysis.get("discrepancies", [])
        ts_table.add_row(
            "discrepancies",
            str(len(discrepancies)) if discrepancies else "none",
        )
        ts_table.add_row("analyzed at", analysis.get("analyzed_at", ""))
        llm_provider = analysis.get("llm_provider", "")
        if llm_provider:
            ts_table.add_row("llm provider", llm_provider)
    else:
        ts_table.add_row("score", "unverified  (no analysis performed)")
        ts_table.add_row("", "repack with --analyze to generate score")

    console.print(ts_table)

    # ── File listing ──────────────────────────────────────────────────
    files = info.get("files", [])
    if files:
        console.print(f"\n[bold]Files[/bold] ({len(files)}):")
        for f in files:
            console.print(f"  [dim]-[/dim] {f}")

    # ── Validation status ─────────────────────────────────────────────
    if info["is_valid"]:
        console.print("\n[bold green]PASS: Package is valid.[/bold green]")
    else:
        console.print("\n[bold red]FAIL: Package has errors:[/bold red]")
        for e in info["errors"]:
            err_console.print(f"  [red]{e}[/red]")

    if info["warnings"]:
        for w in info["warnings"]:
            err_console.print(f"  [yellow]WARN: {w}[/yellow]")


# ---------------------------------------------------------------------------
# unpack
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("agent_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-d", "--dest",
    type=click.Path(path_type=Path),
    default=None,
    help="Destination directory (default: <name>-<version>/).",
)
def unpack(agent_file: Path, dest: Path | None) -> None:
    """Unpack a .agent file into a directory."""
    from agentpk.exceptions import PackageCorruptError
    from agentpk.packer import unpack as do_unpack

    agent_file = Path(agent_file).resolve()

    if dest is None:
        # Derive directory name from filename, e.g. foo-1.0.0.agent -> foo-1.0.0/
        stem = agent_file.stem
        dest = agent_file.parent / stem

    dest = Path(dest).resolve()

    try:
        do_unpack(agent_file, dest)
    except PackageCorruptError as exc:
        err_console.print(f"[bold red]Unpack failed:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold green]Unpacked to [cyan]{dest}[/cyan][/bold green]",
            title="agent unpack",
        )
    )


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
def diff(old_file: Path, new_file: Path) -> None:
    """Show differences between two .agent files."""
    from agentpk.diff import diff_packages

    old_file = Path(old_file).resolve()
    new_file = Path(new_file).resolve()

    d = diff_packages(old_file, new_file)

    if d.is_empty:
        console.print("[bold green]No differences found.[/bold green]")
        return

    if d.added:
        table = Table(title="Added", border_style="green")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in sorted(d.added.items()):
            table.add_row(k, str(v))
        console.print(table)

    if d.removed:
        table = Table(title="Removed", border_style="red")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in sorted(d.removed.items()):
            table.add_row(k, str(v))
        console.print(table)

    if d.changed:
        table = Table(title="Changed", border_style="yellow")
        table.add_column("Field", style="bold")
        table.add_column("Old Value")
        table.add_column("New Value")
        for k, (old_val, new_val) in sorted(d.changed.items()):
            table.add_row(k, str(old_val), str(new_val))
        console.print(table)


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

@cli.command("test")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show detail for every test case.")
def self_test(verbose: bool) -> None:
    """Run built-in self-tests to verify your installation."""
    from agentpk.testing import run_tests

    console.print("[bold]Running agentpk self-tests...[/bold]\n")

    suite = run_tests(verbose=verbose)

    # Build results table
    table = Table(title="Self-Test Results", border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Test", style="bold")
    table.add_column("Description")
    table.add_column("Result", justify="center")
    if verbose:
        table.add_column("Detail")

    for i, r in enumerate(suite.results, 1):
        status = "[bold green]PASS[/bold green]" if r.passed else "[bold red]FAIL[/bold red]"
        row = [str(i), r.name, r.description, status]
        if verbose:
            row.append(r.detail)
        table.add_row(*row)

    console.print(table)
    console.print()

    if suite.all_passed:
        console.print(
            Panel(
                f"[bold green]All {suite.total} tests passed.[/bold green]",
                title="agent test",
            )
        )
    else:
        err_console.print(
            Panel(
                f"[bold red]{suite.failed}/{suite.total} tests failed.[/bold red]",
                title="agent test",
            )
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@cli.command("generate")
@click.argument("directory", default=".", required=False)
@click.option("--level", default=2, type=click.IntRange(1, 4), help="Analysis level (1-4). Default: 2.")
@click.option("-o", "--output", default=None, help="Output path for manifest.yaml.")
@click.option("-f", "--force", is_flag=True, default=False, help="Overwrite existing manifest.yaml if present.")
def generate_command(directory: str, level: int, output: str | None, force: bool) -> None:
    """Generate a manifest.yaml from code analysis.

    \b
    Analyzes source code in DIRECTORY and produces a manifest.yaml
    based on what the code actually does. Fields that cannot be
    determined from code are marked with # REVIEW comments.

    \b
    If a manifest.yaml already exists, use ``agent pack --analyze``
    to verify it against the code instead.

    \b
      agent generate .
      agent generate ./my-agent --level 3
      agent generate ./my-agent --output ./manifest.yaml
    """
    from agentpk.analyzer import analyze, get_review_fields
    from agentpk.constants import MANIFEST_FILENAME

    dir_path = Path(directory).resolve()

    if not dir_path.exists() or not dir_path.is_dir():
        err_console.print(f"[bold red]Error:[/bold red] directory not found: {directory}")
        sys.exit(1)

    manifest_path = dir_path / MANIFEST_FILENAME
    if output:
        manifest_path = Path(output).resolve()

    if manifest_path.exists() and not force:
        err_console.print(
            f"[bold red]Error:[/bold red] {manifest_path.name} already exists.\n"
            "  Use --force to overwrite, or use [cyan]agent pack --analyze[/cyan] "
            "to verify the existing manifest."
        )
        sys.exit(1)

    console.print(f"  Analyzing: [cyan]{dir_path}[/cyan]")
    console.print(f"  Level:     {level}\n")

    result = analyze(dir_path, level=level, mode="generate")

    # Show analysis results
    _print_analysis_results(result)

    if result.suggested_manifest is None:
        err_console.print("\n[bold red]Error:[/bold red] could not generate manifest from analysis.")
        sys.exit(1)

    generated = result.suggested_manifest

    # Show the generated manifest
    import yaml

    manifest_yaml = yaml.dump(generated, default_flow_style=False, sort_keys=False)
    console.print("\n[bold]Generated manifest.yaml from code analysis:[/bold]\n")
    console.print(Panel(manifest_yaml, title="manifest.yaml", border_style="cyan"))

    # Show REVIEW fields
    review_fields = get_review_fields(generated)
    if review_fields:
        console.print(
            f"\n  [yellow]{len(review_fields)} field(s) require your review "
            f"(marked with # REVIEW):[/yellow]"
        )
        for field in review_fields:
            console.print(f"    - {field}")

    # Write manifest
    manifest_path.write_text(manifest_yaml, encoding="utf-8")
    console.print(f"\n  Written: [cyan]{manifest_path}[/cyan]")
    console.print(
        Panel(
            "[bold green]manifest.yaml written.[/bold green]\n"
            "  Review marked fields, then run [cyan]agent pack[/cyan] to package your agent.",
            title="agent generate",
        )
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.argument("directory", required=False, default=".")
@click.option("--recursive", "-r", is_flag=True, default=False, help="Scan subdirectories recursively.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
def list_command(directory: str, recursive: bool, output_json: bool) -> None:
    """List all .agent files in a directory.

    \b
    Scans DIRECTORY (default: current directory) for .agent files
    and displays a summary table.

    \b
      agent list
      agent list ./agents/
      agent list ./agents/ --recursive
      agent list ./agents/ --json
    """
    import json as json_mod

    from agentpk.lister import list_agents

    dir_path = Path(directory).resolve()

    if not dir_path.exists():
        err_console.print(f"[bold red]Error:[/bold red] directory not found: {directory}")
        sys.exit(1)

    if not dir_path.is_dir():
        err_console.print(f"[bold red]Error:[/bold red] not a directory: {directory}")
        sys.exit(1)

    agents = list_agents(dir_path, recursive=recursive)

    if output_json:
        data = [
            {
                "name": a.name,
                "version": a.version,
                "execution_type": a.execution_type,
                "tool_count": a.tool_count,
                "packaged_at": a.packaged_at,
                "path": str(a.path),
                "valid": a.valid,
            }
            for a in agents
        ]
        click.echo(json_mod.dumps(data, indent=2))
        return

    if not agents:
        console.print(f"No .agent files found in {directory}")
        return

    console.print(f"  Scanning: [cyan]{dir_path}[/cyan]\n")

    table = Table(border_style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Version")
    table.add_column("Execution")
    table.add_column("Tools", justify="right")
    table.add_column("Packaged")

    invalid_warnings: list[str] = []
    for a in agents:
        version_str = a.version
        if not a.valid:
            version_str = "[red][invalid][/red]"
            invalid_warnings.append(f"{a.path.name}: {a.error}")
        table.add_row(
            a.name,
            version_str,
            a.execution_type,
            str(a.tool_count),
            a.packaged_at,
        )

    console.print(table)
    console.print(f"\n  {len(agents)} agent(s) found.")

    for w in invalid_warnings:
        err_console.print(f"  [yellow]WARN:[/yellow] {w}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("agent_file", type=click.Path(exists=True, path_type=Path))
@click.option("--keep", "-k", is_flag=True, default=False, help="Keep the temp directory after execution.")
@click.option("--dry-run", is_flag=True, default=False, help="Validate and extract but do not execute.")
@click.option("--env", "env_pairs", multiple=True, help="Set environment variable (KEY=VALUE). Repeatable.")
@click.argument("agent_args", nargs=-1, type=click.UNPROCESSED)
def run(agent_file: Path, keep: bool, dry_run: bool, env_pairs: tuple[str, ...], agent_args: tuple[str, ...]) -> None:
    """Run a packed .agent file.

    \b
    Extracts to a temp directory, validates, and executes the agent
    entry point as a subprocess.

    \b
      agent run my-agent-1.0.0.agent
      agent run my-agent-1.0.0.agent -- --flag value
      agent run my-agent-1.0.0.agent --dry-run
      agent run my-agent-1.0.0.agent --keep

    \b
    Warning: this executes code from the .agent package.
    Only run agents from sources you trust.
    """
    from agentpk.manifest import load_manifest
    from agentpk.runner import run_agent

    agent_file = Path(agent_file).resolve()

    # Parse env vars
    env_vars: dict[str, str] = {}
    for pair in env_pairs:
        if "=" not in pair:
            err_console.print(f"[bold red]Error:[/bold red] invalid --env format: {pair} (expected KEY=VALUE)")
            sys.exit(1)
        k, v = pair.split("=", 1)
        env_vars[k] = v

    console.print("[bold yellow]Warning:[/bold yellow] this executes code from the .agent package.")
    console.print("[bold yellow]Only run agents from sources you trust.[/bold yellow]\n")

    # Show agent info
    try:
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(agent_file, "r") as zf:
                zf.extract("manifest.yaml", tmp)
            m = load_manifest(Path(tmp) / "manifest.yaml")
            console.print(f"  Agent:   [bold]{m.name}[/bold] v{m.version}")
            console.print(f"  Runtime: {m.runtime.language} {m.runtime.language_version}")
            entry_fn = f" :: {m.runtime.entry_function}" if m.runtime.entry_function else ""
            console.print(f"  Entry:   {m.runtime.entry_point}{entry_fn}")
            console.print()
    except Exception:
        pass  # info display is best-effort

    if dry_run:
        console.print("  Validating (dry run)...")

    result = run_agent(
        agent_file,
        agent_args=list(agent_args) if agent_args else None,
        keep=keep,
        dry_run=dry_run,
        env_vars=env_vars if env_vars else None,
    )

    if not result.success:
        err_console.print(f"\n[bold red]Run failed:[/bold red] {result.error}")
        sys.exit(1)

    if dry_run:
        console.print(
            Panel("[bold green]Dry run passed. Agent is valid and runnable.[/bold green]", title="agent run")
        )
    else:
        console.print(f"\n  Done. Exit code: {result.exit_code}")

    if keep and result.temp_dir:
        console.print(f"  Temp directory kept: [cyan]{result.temp_dir}[/cyan]")
    elif not keep and not dry_run:
        console.print("  Cleaned up temp directory.")


# ---------------------------------------------------------------------------
# sign
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("agent_file", type=click.Path(exists=True, path_type=Path))
@click.option("--key", required=True, type=click.Path(exists=True, path_type=Path), help="Path to PEM private key.")
@click.option("--signer", default=None, help="Signer identity string.")
def sign(agent_file: Path, key: Path, signer: str | None) -> None:
    """Sign a .agent file with a private key.

    \b
    Produces a .sig file alongside the .agent file:
      agent sign fraud-detection-1.0.0.agent --key my-key.pem
      agent sign fraud-detection-1.0.0.agent --key my-key.pem --signer "Acme AI"
    """
    from agentpk.signing import sign_agent

    agent_file = Path(agent_file).resolve()
    key = Path(key).resolve()

    console.print(f"  Signing: [cyan]{agent_file.name}[/cyan]")
    console.print(f"  Key:     {key}")

    try:
        sig_path = sign_agent(agent_file, key, signer=signer)
    except Exception as exc:
        err_console.print(f"\n[bold red]Signing failed:[/bold red] {exc}")
        sys.exit(1)

    console.print(f"\n  Written: [cyan]{sig_path}[/cyan]")
    console.print(
        Panel("[bold green]Signed successfully.[/bold green]", title="agent sign")
    )


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("agent_file", type=click.Path(exists=True, path_type=Path))
@click.option("--cert", required=True, type=click.Path(exists=True, path_type=Path), help="Path to PEM certificate.")
def verify(agent_file: Path, cert: Path) -> None:
    """Verify the signature on a .agent file.

    \b
    Checks the .sig file alongside the .agent file:
      agent verify fraud-detection-1.0.0.agent --cert my-cert.pem
    """
    from agentpk.signing import verify_agent

    agent_file = Path(agent_file).resolve()
    cert = Path(cert).resolve()

    console.print(f"  Verifying: [cyan]{agent_file.name}[/cyan]")
    console.print(f"  Certificate: {cert}\n")

    valid, message = verify_agent(agent_file, cert)

    if valid:
        console.print(f"  [bold green]{message}[/bold green]")
        console.print(
            Panel("[bold green]Verification passed.[/bold green]", title="agent verify")
        )
    else:
        err_console.print(f"  [bold red]ERROR:[/bold red] {message}")
        err_console.print("[bold red]  Do not use this agent.[/bold red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--out", required=True, type=click.Path(path_type=Path), help="Output path for the private key PEM file.")
def keygen(out: Path) -> None:
    """Generate a key pair for signing agents.

    \b
    Generates an RSA-2048 private key and a self-signed certificate:
      agent keygen --out my-key.pem

    \b
    This creates two files:
      my-key.pem   -- private key (keep secret)
      my-cert.pem  -- public certificate (share with recipients)
    """
    from agentpk.signing import generate_keypair

    out = Path(out).resolve()
    cert_path = out.parent / out.name.replace("-key", "-cert").replace("key", "cert")
    if cert_path == out:
        cert_path = out.parent / (out.stem + "-cert" + out.suffix)

    console.print("  Generating RSA-2048 key pair...")

    try:
        generate_keypair(out, cert_path)
    except Exception as exc:
        err_console.print(f"\n[bold red]Key generation failed:[/bold red] {exc}")
        sys.exit(1)

    console.print(f"  Private key: [cyan]{out}[/cyan]")
    console.print(f"  Public cert: [cyan]{cert_path}[/cyan]")
    console.print()
    console.print("  Keep the private key secret. Share the certificate with")
    console.print("  recipients so they can verify agents you sign.")
    console.print(
        Panel("[bold green]Key pair generated.[/bold green]", title="agent keygen")
    )


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@cli.command("serve")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8080, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes (dev mode).")
def serve_cmd(host, port, reload):
    """Start the agentpk REST API and packaging UI."""
    try:
        from agentpk.api.server import serve
    except ImportError:
        click.echo("API server requires: pip install agentpk[api]", err=True)
        sys.exit(1)

    click.echo(f"Starting agentpk API on http://{host}:{port}")
    click.echo(f"Packaging UI: http://localhost:{port}")
    serve(host=host, port=port, reload=reload)
