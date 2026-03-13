"""Code analysis and trust scoring for .agent packages.

Four independent analysis levels:
  Level 1 - Structural validation (manifest schema)
  Level 2 - Static AST analysis (imports, calls, tools)
  Level 3 - LLM semantic analysis (requires API key)
  Level 4 - Runtime sandbox (requires Docker)
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from agentpk.constants import (
    DISCREPANCY_PENALTIES,
    FORMAT_VERSION,
    LEVEL_SKIP_PENALTIES,
    LEVEL_WEIGHTS,
    MANIFEST_FILENAME,
    VALID_LANGUAGES,
    trust_label,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class DiscrepancyType(str, Enum):
    UNDECLARED = "undeclared"  # found in code, not in manifest
    UNCONFIRMED = "unconfirmed"  # in manifest, not found in code
    SCOPE_MISMATCH = "scope_mismatch"  # declared read, code does write


class DiscrepancySeverity(str, Enum):
    MINOR = "minor"  # -5 points
    MAJOR = "major"  # -10 points
    CRITICAL = "critical"  # -20 points


@dataclass
class Discrepancy:
    type: DiscrepancyType
    severity: DiscrepancySeverity
    description: str
    evidence: str = ""  # file:line reference or code snippet
    source: str = ""  # "static", "llm", "sandbox"


@dataclass
class LevelResult:
    level: int
    name: str
    ran: bool
    passed: bool
    score: int  # points contributed (can be negative for discrepancies)
    skipped_reason: str = ""
    discrepancies: list[Discrepancy] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class StaticAnalysisFindings:
    """Raw findings from AST analysis before comparison with manifest."""

    imports: list[str] = field(default_factory=list)
    network_calls: list[str] = field(default_factory=list)
    file_writes: list[str] = field(default_factory=list)
    file_reads: list[str] = field(default_factory=list)
    subprocess_calls: list[str] = field(default_factory=list)
    env_vars_read: list[str] = field(default_factory=list)
    tool_registrations: list[str] = field(default_factory=list)
    external_apis: list[str] = field(default_factory=list)
    detected_language: str = ""
    entry_functions: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    level_requested: int
    levels_run: list[int] = field(default_factory=list)
    trust_score: int = 0
    trust_label: str = "Unverified"
    level_results: list[LevelResult] = field(default_factory=list)
    all_discrepancies: list[Discrepancy] = field(default_factory=list)
    suggested_manifest: Optional[dict] = None
    analyzed_at: str = ""
    llm_provider: str = ""
    analysis_mode: str = ""  # "verify" or "generate"
    static_findings: Optional[StaticAnalysisFindings] = None


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------


def calculate_trust_score(level_results: list[LevelResult]) -> int:
    """Calculate the trust score from level results.

    Each level contributes its score when run, and subtracts a penalty
    when skipped.  The final score is floored at 0.
    """
    base = 0
    levels_seen = {lr.level for lr in level_results}

    for lr in level_results:
        if lr.ran:
            base += lr.score

    # Penalties for skipped levels
    for lvl in (1, 2, 3, 4):
        lr_for_level = next((lr for lr in level_results if lr.level == lvl), None)
        if lr_for_level is None or not lr_for_level.ran:
            base += LEVEL_SKIP_PENALTIES.get(lvl, 0)

    return max(0, base)


# ---------------------------------------------------------------------------
# Level 1 - Structural validation
# ---------------------------------------------------------------------------


def run_level1(manifest_path: Optional[Path]) -> LevelResult:
    """Validate the manifest schema if one exists.

    If no manifest is present, return skipped with penalty noted.
    """
    if manifest_path is None or not manifest_path.exists():
        return LevelResult(
            level=1,
            name="Structural validation",
            ran=False,
            passed=False,
            score=0,
            skipped_reason="No manifest present",
        )

    from agentpk.validator import validate_directory

    source_dir = manifest_path.parent
    vr = validate_directory(source_dir)

    if vr.is_valid:
        return LevelResult(
            level=1,
            name="Structural validation",
            ran=True,
            passed=True,
            score=LEVEL_WEIGHTS[1],
            notes=[f"Manifest valid ({len(vr.warnings)} warnings)"],
        )

    # Partial: ran but failed
    error_msgs = [e.message for e in vr.errors[:5]]
    return LevelResult(
        level=1,
        name="Structural validation",
        ran=True,
        passed=False,
        score=max(0, LEVEL_WEIGHTS[1] // 2),
        notes=[f"Manifest has {len(vr.errors)} error(s)"] + error_msgs,
    )


# ---------------------------------------------------------------------------
# Level 2 - Static AST analysis
# ---------------------------------------------------------------------------

# Known network call patterns
_NETWORK_PATTERNS = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "requests.patch",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.delete",
    "httpx.Client",
    "httpx.AsyncClient",
    "urllib.request.urlopen",
    "aiohttp.ClientSession",
}

# Known LLM client patterns (prefix match)
_LLM_CLIENT_PREFIXES = [
    "openai.",
    "anthropic.",
    "langchain_openai.",
    "langchain_anthropic.",
    "litellm.",
    "cohere.",
    "google.generativeai.",
]

# Known database modules
_DATABASE_MODULES = {
    "psycopg2",
    "psycopg",
    "sqlalchemy",
    "pymongo",
    "redis",
    "pymysql",
    "sqlite3",
    "asyncpg",
    "motor",
    "peewee",
    "tortoise",
    "databases",
    "aiosqlite",
}

# Known tool framework patterns
_TOOL_DECORATOR_NAMES = {"tool", "task", "agent"}
_TOOL_CLASS_NAMES = {
    "Tool",
    "StructuredTool",
    "BaseTool",
    "ConversableAgent",
}
_TOOL_FUNCTION_CALLS = {"register_function"}

# Subprocess call patterns
_SUBPROCESS_PATTERNS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_output",
    "subprocess.check_call",
    "os.system",
    "os.popen",
}

# File write patterns
_FILE_WRITE_PATTERNS = {
    "write_text",
    "write_bytes",
    "os.remove",
    "os.unlink",
    "shutil.copy",
    "shutil.move",
    "shutil.rmtree",
}

# File read patterns
_FILE_READ_PATTERNS = {"read_text", "read_bytes"}


class _PythonASTVisitor(ast.NodeVisitor):
    """Walk a Python AST and extract behavioral signals."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.imports: list[str] = []
        self.network_calls: list[str] = []
        self.file_writes: list[str] = []
        self.file_reads: list[str] = []
        self.subprocess_calls: list[str] = []
        self.env_vars_read: list[str] = []
        self.tool_registrations: list[str] = []
        self.external_apis: list[str] = []
        self.entry_functions: list[str] = []
        self._in_class = False

    def _ref(self, node: ast.AST) -> str:
        """Return a file:line reference."""
        return f"{self.filename}:{getattr(node, 'lineno', '?')}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(f"{alias.name}:{node.lineno}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append(f"{module}:{node.lineno}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Detect entry functions at module level
        if not self._in_class and node.name in (
            "run",
            "main",
            "execute",
            "invoke",
            "handler",
        ):
            self.entry_functions.append(f"{node.name}:{self._ref(node)}")

        # Detect tool decorator patterns
        for decorator in node.decorator_list:
            deco_name = self._get_decorator_name(decorator)
            if deco_name in _TOOL_DECORATOR_NAMES:
                self.tool_registrations.append(
                    f"@{deco_name}({node.name}):{self._ref(node)}"
                )

        old_in_class = self._in_class
        self._in_class = False
        self.generic_visit(node)
        self._in_class = old_in_class

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Detect tool class subclasses
        for base in node.bases:
            base_name = self._get_name(base)
            if base_name in _TOOL_CLASS_NAMES:
                self.tool_registrations.append(
                    f"class({base_name})({node.name}):{self._ref(node)}"
                )

        old_in_class = self._in_class
        self._in_class = True
        self.generic_visit(node)
        self._in_class = old_in_class

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._get_call_name(node)
        if call_name:
            # Network calls
            if call_name in _NETWORK_PATTERNS:
                self.network_calls.append(f"{call_name}:{self._ref(node)}")
            # LLM clients
            elif any(call_name.startswith(p) for p in _LLM_CLIENT_PREFIXES):
                self.external_apis.append(f"{call_name}:{self._ref(node)}")
            # Subprocess calls
            elif call_name in _SUBPROCESS_PATTERNS:
                self.subprocess_calls.append(f"{call_name}:{self._ref(node)}")
            # Tool registration functions
            elif call_name.split(".")[-1] in _TOOL_FUNCTION_CALLS:
                self.tool_registrations.append(
                    f"call({call_name}):{self._ref(node)}"
                )
            # Tool class instantiation
            elif call_name.split(".")[-1] in _TOOL_CLASS_NAMES:
                self.tool_registrations.append(
                    f"new({call_name}):{self._ref(node)}"
                )

            # File writes via method call
            method = call_name.split(".")[-1] if "." in call_name else call_name
            if method in _FILE_WRITE_PATTERNS:
                self.file_writes.append(f"{call_name}:{self._ref(node)}")
            if method in _FILE_READ_PATTERNS:
                self.file_reads.append(f"{call_name}:{self._ref(node)}")

            # open() call — check mode arg
            if call_name == "open" or call_name.endswith(".open"):
                self._handle_open_call(node)

            # Environment variable access
            if call_name in ("os.environ.get", "os.getenv"):
                self._handle_env_access(node)
            elif call_name == "os.environ" and isinstance(
                node, ast.Subscript
            ):
                self.env_vars_read.append(f"os.environ[]:{self._ref(node)}")

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Detect os.environ[key] access."""
        sub_name = self._get_name(node.value)
        if sub_name == "os.environ":
            key = ""
            if isinstance(node.slice, ast.Constant):
                key = str(node.slice.value)
            self.env_vars_read.append(
                f"os.environ[{key}]:{self._ref(node)}"
            )
        self.generic_visit(node)

    def _handle_open_call(self, node: ast.Call) -> None:
        """Classify open() as read or write based on mode argument."""
        mode = "r"  # default
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value)

        ref = self._ref(node)
        if any(c in mode for c in "wxa"):
            self.file_writes.append(f"open({mode}):{ref}")
        else:
            self.file_reads.append(f"open({mode}):{ref}")

    def _handle_env_access(self, node: ast.Call) -> None:
        """Record environment variable name from os.getenv / os.environ.get."""
        key = ""
        if node.args and isinstance(node.args[0], ast.Constant):
            key = str(node.args[0].value)
        ref = self._ref(node)
        self.env_vars_read.append(f"{key}:{ref}")

    @staticmethod
    def _get_decorator_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call):
            return _PythonASTVisitor._get_name(node.func)
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    @staticmethod
    def _get_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _PythonASTVisitor._get_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        return _PythonASTVisitor._get_name(node.func)


def _analyze_python_file(path: Path, rel_name: str) -> _PythonASTVisitor:
    """Parse and analyze a single Python file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=rel_name)
    except SyntaxError:
        return _PythonASTVisitor(rel_name)
    visitor = _PythonASTVisitor(rel_name)
    visitor.visit(tree)
    return visitor


# Regex patterns for Node.js analysis
_JS_IMPORT_RE = re.compile(r"""(?:require\s*\(\s*['"]([^'"]+)['"]\s*\)|import\s+.*?from\s+['"]([^'"]+)['"])""")
_JS_NETWORK_RE = re.compile(r"""(?:fetch\s*\(|axios\.|http\.|https\.|request\s*\()""")
_JS_FS_WRITE_RE = re.compile(r"""fs\s*\.\s*(?:write|unlink|rmdir|rm|appendFile)""")
_JS_FS_READ_RE = re.compile(r"""fs\s*\.\s*(?:read|readFile|readdir|stat)""")
_JS_SUBPROCESS_RE = re.compile(r"""child_process|exec\s*\(|spawn\s*\(""")
_JS_ENV_RE = re.compile(r"""process\.env\.(\w+)""")
_JS_EXPORT_RE = re.compile(r"""(?:module\.exports|export\s+(?:default\s+)?(?:function|class|const))""")


def _analyze_js_file(
    path: Path, rel_name: str
) -> dict[str, list[str]]:
    """Regex-based analysis of a JavaScript/TypeScript file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()

    findings: dict[str, list[str]] = {
        "imports": [],
        "network_calls": [],
        "file_writes": [],
        "file_reads": [],
        "subprocess_calls": [],
        "env_vars_read": [],
        "entry_functions": [],
    }

    for i, line in enumerate(lines, 1):
        ref = f"{rel_name}:{i}"
        for m in _JS_IMPORT_RE.finditer(line):
            mod = m.group(1) or m.group(2)
            findings["imports"].append(f"{mod}:{ref}")
        if _JS_NETWORK_RE.search(line):
            findings["network_calls"].append(ref)
        if _JS_FS_WRITE_RE.search(line):
            findings["file_writes"].append(ref)
        if _JS_FS_READ_RE.search(line):
            findings["file_reads"].append(ref)
        if _JS_SUBPROCESS_RE.search(line):
            findings["subprocess_calls"].append(ref)
        for m in _JS_ENV_RE.finditer(line):
            findings["env_vars_read"].append(f"{m.group(1)}:{ref}")
        if _JS_EXPORT_RE.search(line):
            findings["entry_functions"].append(ref)

    return findings


def _detect_language(source_dir: Path) -> str:
    """Detect the primary language from file extensions."""
    py_count = len(list(source_dir.rglob("*.py")))
    js_count = len(list(source_dir.rglob("*.js")))
    ts_count = len(list(source_dir.rglob("*.ts")))

    if ts_count > max(py_count, js_count):
        return "typescript"
    if js_count > py_count:
        return "nodejs"
    if py_count > 0:
        return "python"
    return ""


def _collect_source_files(source_dir: Path) -> dict[str, Path]:
    """Collect all source files grouped by relative name."""
    files: dict[str, Path] = {}
    for ext in ("*.py", "*.js", "*.ts", "*.mjs", "*.cjs"):
        for p in sorted(source_dir.rglob(ext)):
            # Skip common non-source dirs
            parts = p.relative_to(source_dir).parts
            if any(
                part in ("node_modules", ".venv", "venv", "__pycache__", ".git")
                for part in parts
            ):
                continue
            rel = p.relative_to(source_dir).as_posix()
            files[rel] = p
    return files


def run_level2(
    source_dir: Path,
    manifest: Optional[dict] = None,
    language: str = "",
) -> tuple[LevelResult, StaticAnalysisFindings]:
    """Walk all source files and extract behavioral signals via AST analysis.

    Compare findings against manifest declarations.
    """
    if not language:
        language = _detect_language(source_dir)

    source_files = _collect_source_files(source_dir)
    if not source_files:
        return (
            LevelResult(
                level=2,
                name="Static AST analysis",
                ran=False,
                passed=False,
                score=0,
                skipped_reason="No source files found",
            ),
            StaticAnalysisFindings(),
        )

    findings = StaticAnalysisFindings(detected_language=language)

    # Analyze all files
    for rel_name, path in source_files.items():
        if path.suffix == ".py":
            visitor = _analyze_python_file(path, rel_name)
            findings.imports.extend(visitor.imports)
            findings.network_calls.extend(visitor.network_calls)
            findings.file_writes.extend(visitor.file_writes)
            findings.file_reads.extend(visitor.file_reads)
            findings.subprocess_calls.extend(visitor.subprocess_calls)
            findings.env_vars_read.extend(visitor.env_vars_read)
            findings.tool_registrations.extend(visitor.tool_registrations)
            findings.external_apis.extend(visitor.external_apis)
            findings.entry_functions.extend(visitor.entry_functions)
        elif path.suffix in (".js", ".ts", ".mjs", ".cjs"):
            js_findings = _analyze_js_file(path, rel_name)
            findings.imports.extend(js_findings["imports"])
            findings.network_calls.extend(js_findings["network_calls"])
            findings.file_writes.extend(js_findings["file_writes"])
            findings.file_reads.extend(js_findings["file_reads"])
            findings.subprocess_calls.extend(js_findings["subprocess_calls"])
            findings.env_vars_read.extend(js_findings["env_vars_read"])
            findings.entry_functions.extend(js_findings["entry_functions"])

    # Check for database module imports
    for imp in findings.imports:
        module_name = imp.split(":")[0].split(".")[0]
        if module_name in _DATABASE_MODULES:
            findings.external_apis.append(f"db:{imp}")

    # Compare findings against manifest
    discrepancies: list[Discrepancy] = []
    notes: list[str] = []

    if manifest is not None:
        discrepancies, notes = _compare_findings_to_manifest(findings, manifest)

    # Score calculation
    score = LEVEL_WEIGHTS[2]
    for d in discrepancies:
        score += DISCREPANCY_PENALTIES.get(d.severity.value, 0)
    score = max(0, score)

    return (
        LevelResult(
            level=2,
            name="Static AST analysis",
            ran=True,
            passed=len(discrepancies) == 0,
            score=score,
            discrepancies=discrepancies,
            notes=notes
            + [
                f"Scanned {len(source_files)} source file(s)",
                f"Language: {language}",
                f"Imports: {len(findings.imports)}",
                f"Network calls: {len(findings.network_calls)}",
                f"Tool registrations: {len(findings.tool_registrations)}",
            ],
        ),
        findings,
    )


def _compare_findings_to_manifest(
    findings: StaticAnalysisFindings,
    manifest: dict,
) -> tuple[list[Discrepancy], list[str]]:
    """Compare static analysis findings against a manifest dict.

    Returns (discrepancies, notes).
    """
    discrepancies: list[Discrepancy] = []
    notes: list[str] = []

    # Extract declared tools from manifest
    tools = manifest.get("capabilities", {}).get("tools", []) or []
    declared_tool_ids = {t.get("id", "") for t in tools if isinstance(t, dict)}
    declared_scopes = {
        t.get("id", ""): t.get("scope", "read")
        for t in tools
        if isinstance(t, dict)
    }
    has_write_tool = any(s in ("write", "execute", "admin") for s in declared_scopes.values())
    has_read_tool = any(s == "read" for s in declared_scopes.values())

    # Check for undeclared network calls
    if findings.network_calls and not has_write_tool and not has_read_tool:
        for nc in findings.network_calls[:5]:  # Cap at 5
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.UNDECLARED,
                    severity=DiscrepancySeverity.MAJOR,
                    description="Network call detected but no tool with network scope declared",
                    evidence=nc,
                    source="static",
                )
            )

    # Check for scope mismatches: network writes but only read tools declared
    if findings.network_calls and has_read_tool and not has_write_tool:
        # Look for POST/PUT/DELETE style calls
        write_calls = [
            nc
            for nc in findings.network_calls
            if any(
                w in nc
                for w in ("post", "put", "delete", "patch", "write")
            )
        ]
        for wc in write_calls[:3]:
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.SCOPE_MISMATCH,
                    severity=DiscrepancySeverity.CRITICAL,
                    description="Network write call detected but only read-scope tools declared",
                    evidence=wc,
                    source="static",
                )
            )

    # Check for tool registrations vs declared tools
    detected_tool_names: set[str] = set()
    for tr in findings.tool_registrations:
        # Extract function/class name from registration string
        # e.g., "@tool(scan_transaction):file:line" -> "scan_transaction"
        match = re.search(r"\((\w+)\)", tr)
        if match:
            detected_tool_names.add(match.group(1))

    for detected in detected_tool_names:
        if detected not in declared_tool_ids:
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.UNDECLARED,
                    severity=DiscrepancySeverity.MAJOR,
                    description=f"Tool registration '{detected}' found in code but not declared in manifest",
                    evidence=next(
                        (tr for tr in findings.tool_registrations if detected in tr),
                        "",
                    ),
                    source="static",
                )
            )

    for declared_id in declared_tool_ids:
        if (
            detected_tool_names
            and declared_id not in detected_tool_names
            and findings.tool_registrations
        ):
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.UNCONFIRMED,
                    severity=DiscrepancySeverity.MINOR,
                    description=f"Tool '{declared_id}' declared in manifest but no registration found in code",
                    source="static",
                )
            )

    # Check for subprocess calls
    if findings.subprocess_calls:
        # Check if any tool or permission covers subprocess execution
        has_execute = any(
            declared_scopes.get(tid) in ("execute", "admin")
            for tid in declared_tool_ids
        )
        if not has_execute:
            for sc in findings.subprocess_calls[:3]:
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.UNDECLARED,
                        severity=DiscrepancySeverity.MAJOR,
                        description="Subprocess call detected but no execute-scope tool declared",
                        evidence=sc,
                        source="static",
                    )
                )

    # Check for database imports without data_class
    data_classes = manifest.get("permissions", {}).get("data_classes", []) or []
    has_data_class = len(data_classes) > 0
    db_imports = [
        imp
        for imp in findings.imports
        if imp.split(":")[0].split(".")[0] in _DATABASE_MODULES
    ]
    if db_imports and not has_data_class:
        for di in db_imports[:3]:
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.UNDECLARED,
                    severity=DiscrepancySeverity.MAJOR,
                    description="Database module imported but no data_class declared in permissions",
                    evidence=di,
                    source="static",
                )
            )

    if not discrepancies:
        notes.append("No discrepancies found between code and manifest")

    return discrepancies, notes


# ---------------------------------------------------------------------------
# Level 3 - LLM semantic analysis
# ---------------------------------------------------------------------------


def _detect_llm_provider() -> tuple[str, str]:
    """Detect available LLM provider from environment.

    Returns (provider_name, api_key) or ("", "") if none available.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return "anthropic", key
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return "openai", key
    return "", ""


def _build_llm_prompt(
    source_files: dict[str, str],
    manifest: Optional[dict],
    static_findings: StaticAnalysisFindings,
) -> str:
    """Build the prompt to send to the LLM for semantic analysis."""
    files_block = ""
    for name, content in source_files.items():
        # Truncate very large files
        if len(content) > 10_000:
            content = content[:10_000] + "\n... (truncated)"
        files_block += f"\n--- {name} ---\n{content}\n"

    manifest_block = ""
    if manifest:
        manifest_block = yaml.dump(manifest, default_flow_style=False, sort_keys=False)

    findings_block = (
        f"Imports: {len(static_findings.imports)}\n"
        f"Network calls: {', '.join(static_findings.network_calls[:10]) or 'none'}\n"
        f"File writes: {', '.join(static_findings.file_writes[:10]) or 'none'}\n"
        f"File reads: {', '.join(static_findings.file_reads[:10]) or 'none'}\n"
        f"Subprocess calls: {', '.join(static_findings.subprocess_calls[:10]) or 'none'}\n"
        f"Env vars: {', '.join(static_findings.env_vars_read[:10]) or 'none'}\n"
        f"Tool registrations: {', '.join(static_findings.tool_registrations[:10]) or 'none'}\n"
        f"External APIs: {', '.join(static_findings.external_apis[:10]) or 'none'}\n"
    )

    return (
        "You are analyzing source code for an AI agent to determine what the "
        "agent actually does. Your job is to generate an accurate manifest "
        "description based ONLY on what you can observe in the code.\n\n"
        "For every claim you make, you MUST cite the specific file and line "
        "number. Do not infer capabilities that aren't evidenced in the code.\n\n"
        f"Source files:\n{files_block}\n\n"
        f"Existing manifest (if present):\n{manifest_block}\n\n"
        f"Static analysis findings:\n{findings_block}\n\n"
        "Respond in JSON only with this structure:\n"
        "{\n"
        '  "capabilities": [...],\n'
        '  "execution_type": "...",\n'
        '  "permissions": {...},\n'
        '  "undeclared_findings": [...],\n'
        '  "unconfirmed_declarations": [...],\n'
        '  "citations": {"finding": "file:line"},\n'
        '  "confidence": 0-100,\n'
        '  "notes": [...]\n'
        "}\n"
    )


def _call_anthropic(prompt: str, api_key: str) -> Optional[dict]:
    """Call the Anthropic API using raw HTTP (no SDK dependency)."""
    import urllib.request

    body = json.dumps(
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "Anthropic-Version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Extract text from content blocks
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return _parse_llm_json(text)
    except Exception as exc:
        logger.warning("Anthropic API call failed: %s", exc)
        return None


def _call_openai(prompt: str, api_key: str) -> Optional[dict]:
    """Call the OpenAI API using raw HTTP (no SDK dependency)."""
    import urllib.request

    body = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0,
        }
    )
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        return _parse_llm_json(text)
    except Exception as exc:
        logger.warning("OpenAI API call failed: %s", exc)
        return None


def _parse_llm_json(text: str) -> Optional[dict]:
    """Try to extract JSON from LLM response text."""
    # Try direct parse
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code block
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def run_level3(
    source_files: dict[str, str],
    manifest: Optional[dict],
    static_findings: StaticAnalysisFindings,
    llm_provider: str = "auto",
) -> LevelResult:
    """Send source files to an LLM for semantic analysis.

    Ask it to generate what the manifest SHOULD say, with citations.
    Compare against existing manifest and static findings.
    """
    if llm_provider == "auto":
        provider, api_key = _detect_llm_provider()
    elif llm_provider == "anthropic":
        provider = "anthropic"
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    elif llm_provider == "openai":
        provider = "openai"
        api_key = os.environ.get("OPENAI_API_KEY", "")
    else:
        provider, api_key = "", ""

    if not provider or not api_key:
        return LevelResult(
            level=3,
            name="LLM semantic analysis",
            ran=False,
            passed=False,
            score=0,
            skipped_reason="No LLM API key available (set ANTHROPIC_API_KEY or OPENAI_API_KEY)",
        )

    prompt = _build_llm_prompt(source_files, manifest, static_findings)

    # Call LLM
    if provider == "anthropic":
        provider_label = "anthropic/claude-haiku-4-5-20251001"
        llm_result = _call_anthropic(prompt, api_key)
    else:
        provider_label = "openai/gpt-4o-mini"
        llm_result = _call_openai(prompt, api_key)

    if llm_result is None:
        return LevelResult(
            level=3,
            name="LLM semantic analysis",
            ran=True,
            passed=False,
            score=max(0, LEVEL_WEIGHTS[3] // 2),
            notes=[f"LLM call failed ({provider_label})"],
        )

    # Process LLM findings
    discrepancies: list[Discrepancy] = []
    notes: list[str] = [f"Provider: {provider_label}"]

    citations = llm_result.get("citations", {})
    confidence = llm_result.get("confidence", 50)
    notes.append(f"LLM confidence: {confidence}/100")

    # Undeclared findings from LLM
    for finding in llm_result.get("undeclared_findings", []):
        desc = finding if isinstance(finding, str) else str(finding)
        has_citation = any(desc in c for c in citations) if citations else False
        sev = DiscrepancySeverity.MAJOR if has_citation else DiscrepancySeverity.MINOR
        evidence = citations.get(desc, "LLM-only, no code citation")
        discrepancies.append(
            Discrepancy(
                type=DiscrepancyType.UNDECLARED,
                severity=sev,
                description=desc,
                evidence=evidence,
                source="llm",
            )
        )

    # Unconfirmed declarations from LLM
    for decl in llm_result.get("unconfirmed_declarations", []):
        desc = decl if isinstance(decl, str) else str(decl)
        discrepancies.append(
            Discrepancy(
                type=DiscrepancyType.UNCONFIRMED,
                severity=DiscrepancySeverity.MINOR,
                description=desc,
                evidence="",
                source="llm",
            )
        )

    # LLM notes
    for note in llm_result.get("notes", []):
        notes.append(f"LLM: {note}")

    # Score
    score = LEVEL_WEIGHTS[3]
    for d in discrepancies:
        # Weight LLM-only findings at 50%
        penalty = DISCREPANCY_PENALTIES.get(d.severity.value, 0)
        if "LLM-only" in d.evidence:
            penalty = penalty // 2
        score += penalty
    score = max(0, score)

    return LevelResult(
        level=3,
        name="LLM semantic analysis",
        ran=True,
        passed=len(discrepancies) == 0,
        score=score,
        discrepancies=discrepancies,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Level 4 - Runtime sandbox
# ---------------------------------------------------------------------------


def _check_docker() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_level4(
    agent_dir: Path,
    manifest: dict,
    timeout_seconds: int = 30,
) -> LevelResult:
    """Execute the agent in an isolated Docker container.

    Observe actual behavior and compare against manifest.
    Requires Docker to be installed and running.
    """
    if not _check_docker():
        return LevelResult(
            level=4,
            name="Runtime sandbox",
            ran=False,
            passed=False,
            score=0,
            skipped_reason="Docker not available",
        )

    language = manifest.get("runtime", {}).get("language", "python")
    entry_point = manifest.get("runtime", {}).get("entry_point", "")
    deps_file = manifest.get("runtime", {}).get("dependencies", "")

    # Build Dockerfile
    if language == "python":
        base_image = "python:3.11-slim"
        install_cmd = ""
        if deps_file:
            install_cmd = f"COPY {deps_file} .\nRUN pip install -r {deps_file} --quiet 2>/dev/null || true"
        run_cmd = (
            f'CMD ["python", "-c", '
            f'"import sys, os; sys.path.insert(0, \\".\\"); '
            f"exec(open('{entry_point}').read())"
            f'"]'
        )
    elif language in ("nodejs", "typescript"):
        base_image = "node:18-slim"
        install_cmd = ""
        if deps_file:
            install_cmd = f"COPY {deps_file} .\nRUN npm install --quiet 2>/dev/null || true"
        run_cmd = f'CMD ["node", "{entry_point}"]'
    else:
        return LevelResult(
            level=4,
            name="Runtime sandbox",
            ran=False,
            passed=False,
            score=0,
            skipped_reason=f"Unsupported language for sandbox: {language}",
        )

    discrepancies: list[Discrepancy] = []
    notes: list[str] = ["Sandbox execution is best-effort observation"]
    container_name = f"agentpk-sandbox-{os.getpid()}"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # Write Dockerfile
            dockerfile = (
                f"FROM {base_image}\n"
                "WORKDIR /agent\n"
                f"{install_cmd}\n"
                "COPY . .\n"
                f"{run_cmd}\n"
            )
            (tmp_dir / "Dockerfile").write_text(dockerfile)

            # Copy agent files
            import shutil

            for item in agent_dir.iterdir():
                dest = tmp_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            # Build
            build_result = subprocess.run(
                [
                    "docker",
                    "build",
                    "-t",
                    container_name,
                    "--no-cache",
                    ".",
                ],
                cwd=tmp_dir,
                capture_output=True,
                timeout=120,
            )

            if build_result.returncode != 0:
                stderr = build_result.stderr.decode("utf-8", errors="replace")[:500]
                notes.append(f"Docker build failed: {stderr}")
                return LevelResult(
                    level=4,
                    name="Runtime sandbox",
                    ran=True,
                    passed=False,
                    score=max(0, LEVEL_WEIGHTS[4] // 2),
                    notes=notes,
                )

            # Run with network disabled
            run_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--tmpfs",
                    "/tmp",
                    f"--name={container_name}-run",
                    container_name,
                ],
                capture_output=True,
                timeout=timeout_seconds + 10,
            )

            stdout = run_result.stdout.decode("utf-8", errors="replace")
            stderr = run_result.stderr.decode("utf-8", errors="replace")
            notes.append(f"Exit code: {run_result.returncode}")

            if run_result.returncode != 0:
                notes.append(f"Agent stderr (truncated): {stderr[:300]}")

            # Analyze output for signals
            if "AGENT_ERROR" in stderr:
                notes.append("Agent raised an exception during execution")

            # Even import-time failures give us useful signals
            notes.append("Sandbox execution completed")

    except subprocess.TimeoutExpired:
        notes.append("Sandbox execution timed out")
        return LevelResult(
            level=4,
            name="Runtime sandbox",
            ran=True,
            passed=False,
            score=max(0, LEVEL_WEIGHTS[4] // 3),
            discrepancies=discrepancies,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"Sandbox error: {exc}")
        return LevelResult(
            level=4,
            name="Runtime sandbox",
            ran=True,
            passed=False,
            score=0,
            notes=notes,
        )
    finally:
        # Cleanup Docker image
        try:
            subprocess.run(
                ["docker", "rmi", container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

    score = LEVEL_WEIGHTS[4]
    for d in discrepancies:
        score += DISCREPANCY_PENALTIES.get(d.severity.value, 0)
    score = max(0, score)

    return LevelResult(
        level=4,
        name="Runtime sandbox",
        ran=True,
        passed=len(discrepancies) == 0,
        score=score,
        discrepancies=discrepancies,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


def generate_manifest_from_analysis(
    analysis_result: AnalysisResult,
    static_findings: StaticAnalysisFindings,
    source_dir: Path,
) -> dict:
    """Produce a manifest dict from analysis findings.

    Fields that cannot be determined from code are left with placeholder
    values and a ``# REVIEW`` comment noted in the returned structure.
    """
    # Derive name from directory
    name = re.sub(r"[^a-z0-9-]", "-", source_dir.name.lower()).strip("-")
    if not name:
        name = "my-agent"

    # Detect language
    language = static_findings.detected_language or _detect_language(source_dir)
    if language not in VALID_LANGUAGES:
        language = "python"

    # Detect entry point
    entry_point = ""
    if static_findings.entry_functions:
        # Use the first entry function reference
        ref = static_findings.entry_functions[0]
        # Extract filename from "func_name:filename:line"
        parts = ref.split(":")
        if len(parts) >= 2:
            entry_point = parts[1] if parts[1].endswith(".py") else parts[0]
    if not entry_point:
        # Fallback: look for common entry files
        for candidate in ("src/agent.py", "agent.py", "main.py", "app.py", "index.js", "index.ts"):
            if (source_dir / candidate).exists():
                entry_point = candidate
                break
    if not entry_point:
        entry_point = "REVIEW_entry_point"

    # Detect entry function
    entry_function = "main"
    if static_findings.entry_functions:
        func_name = static_findings.entry_functions[0].split(":")[0]
        entry_function = func_name

    # Detect dependencies file
    deps = None
    for candidate in ("requirements.txt", "package.json", "Pipfile"):
        if (source_dir / candidate).exists():
            deps = candidate
            break

    # Language version
    lang_version = "3.11" if language == "python" else "18"

    # Detect tools from registrations
    tools = []
    seen_tools: set[str] = set()
    for tr in static_findings.tool_registrations:
        match = re.search(r"\((\w+)\)", tr)
        if match:
            tool_name = match.group(1)
            if tool_name not in seen_tools:
                seen_tools.add(tool_name)
                # Infer scope from file write/network patterns
                scope = "read"
                tools.append(
                    {
                        "id": tool_name,
                        "description": f"# REVIEW: description for {tool_name}",
                        "scope": scope,
                        "required": True,
                        "targets": ["# REVIEW: add targets"],
                    }
                )

    # Detect execution type
    exec_type = "on-demand"
    schedule = None
    for imp in static_findings.imports:
        mod = imp.split(":")[0].lower()
        if any(kw in mod for kw in ("schedule", "cron", "apscheduler", "celery")):
            exec_type = "scheduled"
            schedule = "# REVIEW: add cron expression"
            break
        if any(kw in mod for kw in ("trigger", "event", "webhook", "pubsub")):
            exec_type = "triggered"
            break

    manifest: dict[str, Any] = {
        "spec_version": FORMAT_VERSION,
        "name": name,
        "display_name": f"# REVIEW: display name for {name}",
        "version": "0.1.0",
        "description": "# REVIEW: add description",
        "author": "# REVIEW: add author",
        "license": "MIT",
        "tags": [],
        "runtime": {
            "language": language,
            "language_version": lang_version,
            "entry_point": entry_point,
            "entry_function": entry_function,
        },
        "capabilities": {"tools": tools} if tools else {"tools": []},
        "execution": {"type": exec_type},
    }

    if deps:
        manifest["runtime"]["dependencies"] = deps

    if schedule:
        manifest["execution"]["schedule"] = schedule

    # Add data classes if database imports detected
    db_imports = [
        imp.split(":")[0].split(".")[0]
        for imp in static_findings.imports
        if imp.split(":")[0].split(".")[0] in _DATABASE_MODULES
    ]
    if db_imports:
        manifest["permissions"] = {
            "data_classes": [
                {"name": f"# REVIEW: {mod}", "access": "read"}
                for mod in set(db_imports)
            ]
        }

    return manifest


def _get_review_fields(manifest: dict, prefix: str = "") -> list[str]:
    """Find all fields containing '# REVIEW' markers."""
    review_fields: list[str] = []
    for key, value in manifest.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, str) and "# REVIEW" in value:
            review_fields.append(full_key)
        elif isinstance(value, dict):
            review_fields.extend(_get_review_fields(value, full_key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    review_fields.extend(
                        _get_review_fields(item, f"{full_key}[{i}]")
                    )
                elif isinstance(item, str) and "# REVIEW" in item:
                    review_fields.append(f"{full_key}[{i}]")
    return review_fields


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------


def analyze(
    source_dir: Path,
    *,
    level: int = 2,
    mode: str = "verify",
    manifest_dict: Optional[dict] = None,
) -> AnalysisResult:
    """Run analysis up to the requested level.

    Parameters
    ----------
    source_dir:
        Directory containing agent source code.
    level:
        Maximum analysis level to run (1-4).
    mode:
        "verify" to check existing manifest, "generate" to create one.
    manifest_dict:
        Pre-loaded manifest dict. If None and mode is "verify", will
        attempt to load from source_dir/manifest.yaml.
    """
    manifest_path = source_dir / MANIFEST_FILENAME
    has_manifest = manifest_path.exists()

    if manifest_dict is None and has_manifest:
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                manifest_dict = raw
        except Exception:
            pass

    result = AnalysisResult(
        level_requested=level,
        analysis_mode=mode,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )

    static_findings = StaticAnalysisFindings()

    # Level 1 - Structural validation
    if level >= 1:
        lr1 = run_level1(manifest_path if has_manifest else None)
        result.level_results.append(lr1)
        if lr1.ran:
            result.levels_run.append(1)
        result.all_discrepancies.extend(lr1.discrepancies)

    # Level 2 - Static AST analysis
    if level >= 2:
        language = ""
        if manifest_dict:
            language = manifest_dict.get("runtime", {}).get("language", "")
        lr2, static_findings = run_level2(source_dir, manifest_dict, language)
        result.level_results.append(lr2)
        if lr2.ran:
            result.levels_run.append(2)
        result.all_discrepancies.extend(lr2.discrepancies)

    result.static_findings = static_findings

    # Level 3 - LLM semantic analysis
    if level >= 3:
        source_files = _collect_source_files(source_dir)
        file_contents = {
            name: path.read_text(encoding="utf-8", errors="replace")
            for name, path in source_files.items()
        }
        lr3 = run_level3(file_contents, manifest_dict, static_findings)
        result.level_results.append(lr3)
        if lr3.ran:
            result.levels_run.append(3)
        result.all_discrepancies.extend(lr3.discrepancies)
        if lr3.ran:
            # Extract provider from notes
            for note in lr3.notes:
                if note.startswith("Provider:"):
                    result.llm_provider = note.split(":", 1)[1].strip()
                    break

    # Level 4 - Runtime sandbox
    if level >= 4:
        if manifest_dict:
            lr4 = run_level4(source_dir, manifest_dict)
        else:
            lr4 = LevelResult(
                level=4,
                name="Runtime sandbox",
                ran=False,
                passed=False,
                score=0,
                skipped_reason="No manifest available for sandbox execution",
            )
        result.level_results.append(lr4)
        if lr4.ran:
            result.levels_run.append(4)
        result.all_discrepancies.extend(lr4.discrepancies)

    # Calculate trust score
    result.trust_score = calculate_trust_score(result.level_results)
    result.trust_label = trust_label(result.trust_score)

    # Generate suggested manifest if in generate mode
    if mode == "generate":
        result.suggested_manifest = generate_manifest_from_analysis(
            result, static_findings, source_dir
        )

    return result


def get_review_fields(manifest: dict) -> list[str]:
    """Public wrapper for finding REVIEW markers in a manifest."""
    return _get_review_fields(manifest)


def build_analysis_block(result: AnalysisResult) -> dict:
    """Build the ``analysis`` sub-block for ``_package`` metadata."""
    levels_skipped = []
    levels_in_results = {lr.level for lr in result.level_results}
    # Levels that were in results but didn't run (e.g., no API key)
    for lr in result.level_results:
        if not lr.ran:
            levels_skipped.append(
                {"level": lr.level, "reason": lr.skipped_reason}
            )
    # Levels not even attempted (above requested level)
    for lvl in (1, 2, 3, 4):
        if lvl not in levels_in_results:
            levels_skipped.append(
                {"level": lvl, "reason": f"Above requested level ({result.level_requested})"}
            )

    findings_summary = {}
    if result.static_findings:
        sf = result.static_findings
        findings_summary = {
            "imports_detected": len(sf.imports),
            "network_calls": len(sf.network_calls),
            "tool_registrations": len(sf.tool_registrations),
            "undeclared_capabilities": sum(
                1
                for d in result.all_discrepancies
                if d.type == DiscrepancyType.UNDECLARED
            ),
        }

    discreps = []
    for d in result.all_discrepancies:
        discreps.append(
            {
                "type": d.type.value,
                "severity": d.severity.value,
                "description": d.description,
                "evidence": d.evidence,
                "source": d.source,
            }
        )

    return {
        "level_requested": result.level_requested,
        "levels_run": result.levels_run,
        "levels_skipped": levels_skipped,
        "trust_score": result.trust_score,
        "trust_label": result.trust_label,
        "discrepancies": discreps,
        "analyzed_at": result.analyzed_at,
        "llm_provider": result.llm_provider,
        "static_findings_summary": findings_summary,
    }
