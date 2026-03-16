"""Python signal extractor using AST analysis."""

from __future__ import annotations

import ast
from pathlib import Path

from .base import (
    EnvVarAccess,
    ExtractorBase,
    FileOperation,
    ImportRecord,
    NetworkCall,
    StaticAnalysisFindings,
    SubprocessCall,
    ToolRegistration,
)

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

_NETWORK_WRITE_METHODS = {"post", "put", "delete", "patch"}

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

# Dynamic import patterns
_DYNAMIC_IMPORT_CALLS = {"importlib.import_module", "__import__"}


class _PythonASTVisitor(ast.NodeVisitor):
    """Walk a Python AST and extract behavioral signals."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.imports: list[ImportRecord] = []
        self.network_calls: list[NetworkCall] = []
        self.file_writes: list[FileOperation] = []
        self.file_reads: list[FileOperation] = []
        self.subprocess_calls: list[SubprocessCall] = []
        self.env_var_accesses: list[EnvVarAccess] = []
        self.tool_registrations: list[ToolRegistration] = []
        self.entry_functions: list[str] = []
        self.dynamic_import_detected: bool = False
        self._in_class = False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportRecord(
                module=alias.name, file=self.filename, line=node.lineno
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append(ImportRecord(
            module=module, file=self.filename, line=node.lineno
        ))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Detect entry functions at module level
        if not self._in_class and node.name in (
            "run", "main", "execute", "invoke", "handler",
        ):
            self.entry_functions.append(node.name)

        # Detect tool decorator patterns
        for decorator in node.decorator_list:
            deco_name = self._get_decorator_name(decorator)
            if deco_name in _TOOL_DECORATOR_NAMES:
                # Infer framework from imports
                framework = "unknown"
                for imp in self.imports:
                    if "langchain" in imp.module:
                        framework = "langchain"
                        break
                    elif "crewai" in imp.module:
                        framework = "crewai"
                        break
                    elif "autogen" in imp.module:
                        framework = "autogen"
                        break
                self.tool_registrations.append(ToolRegistration(
                    framework=framework,
                    tool_name=node.name,
                    file=self.filename,
                    line=node.lineno,
                ))

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
                self.tool_registrations.append(ToolRegistration(
                    framework="unknown",
                    tool_name=node.name,
                    file=self.filename,
                    line=node.lineno,
                ))

        old_in_class = self._in_class
        self._in_class = True
        self.generic_visit(node)
        self._in_class = old_in_class

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._get_call_name(node)
        if call_name:
            # Network calls
            if call_name in _NETWORK_PATTERNS:
                method_part = call_name.split(".")[-1].upper()
                if method_part in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    method = method_part
                else:
                    method = "UNKNOWN"
                library = call_name.split(".")[0]
                self.network_calls.append(NetworkCall(
                    method=method, library=library,
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))
            # LLM clients
            elif any(call_name.startswith(p) for p in _LLM_CLIENT_PREFIXES):
                self.network_calls.append(NetworkCall(
                    method="UNKNOWN", library=call_name.split(".")[0],
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))
            # Subprocess calls
            elif call_name in _SUBPROCESS_PATTERNS:
                self.subprocess_calls.append(SubprocessCall(
                    command="UNKNOWN",
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))
            # Tool registration functions
            elif call_name.split(".")[-1] in _TOOL_FUNCTION_CALLS:
                self.tool_registrations.append(ToolRegistration(
                    framework="unknown",
                    tool_name=call_name,
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))
            # Tool class instantiation
            elif call_name.split(".")[-1] in _TOOL_CLASS_NAMES:
                self.tool_registrations.append(ToolRegistration(
                    framework="unknown",
                    tool_name=call_name,
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))

            # Dynamic imports
            if call_name in _DYNAMIC_IMPORT_CALLS:
                self.dynamic_import_detected = True

            # File writes via method call
            method = call_name.split(".")[-1] if "." in call_name else call_name
            if method in _FILE_WRITE_PATTERNS:
                self.file_writes.append(FileOperation(
                    operation="write",
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))
            if method in _FILE_READ_PATTERNS:
                self.file_reads.append(FileOperation(
                    operation="read",
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))

            # open() call -- check mode arg
            if call_name == "open" or call_name.endswith(".open"):
                self._handle_open_call(node)

            # Environment variable access
            if call_name in ("os.environ.get", "os.getenv"):
                self._handle_env_access(node)
            elif call_name == "os.environ" and isinstance(node, ast.Subscript):
                self.env_var_accesses.append(EnvVarAccess(
                    var_name="UNKNOWN",
                    file=self.filename, line=getattr(node, "lineno", 0),
                ))

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Detect os.environ[key] access."""
        sub_name = self._get_name(node.value)
        if sub_name == "os.environ":
            key = "UNKNOWN"
            if isinstance(node.slice, ast.Constant):
                key = str(node.slice.value)
            self.env_var_accesses.append(EnvVarAccess(
                var_name=key,
                file=self.filename, line=getattr(node, "lineno", 0),
            ))
        self.generic_visit(node)

    def _handle_open_call(self, node: ast.Call) -> None:
        """Classify open() as read or write based on mode argument."""
        mode = "r"  # default
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value)

        lineno = getattr(node, "lineno", 0)
        if any(c in mode for c in "wxa"):
            self.file_writes.append(FileOperation(
                operation="write", file=self.filename, line=lineno,
            ))
        else:
            self.file_reads.append(FileOperation(
                operation="read", file=self.filename, line=lineno,
            ))

    def _handle_env_access(self, node: ast.Call) -> None:
        """Record environment variable name from os.getenv / os.environ.get."""
        key = "UNKNOWN"
        if node.args and isinstance(node.args[0], ast.Constant):
            key = str(node.args[0].value)
        self.env_var_accesses.append(EnvVarAccess(
            var_name=key,
            file=self.filename, line=getattr(node, "lineno", 0),
        ))

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


class PythonExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> list[str]:
        return [".py"]

    def extract(self, source_files: list[Path]) -> StaticAnalysisFindings:
        findings = StaticAnalysisFindings(language="python")
        for path in source_files:
            if not self.supports_file(path):
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                self._analyze_file(path, source, findings)
            except Exception as e:
                findings.extractor_warnings.append(f"{path.name}: {e}")
        return findings

    def _analyze_file(self, path: Path, source: str, findings: StaticAnalysisFindings) -> None:
        rel_name = path.name
        try:
            tree = ast.parse(source, filename=rel_name)
        except SyntaxError:
            findings.extractor_warnings.append(f"{rel_name}: SyntaxError")
            return

        visitor = _PythonASTVisitor(rel_name)
        visitor.visit(tree)

        findings.imports.extend(visitor.imports)
        findings.network_calls.extend(visitor.network_calls)
        findings.file_writes.extend(visitor.file_writes)
        findings.file_reads.extend(visitor.file_reads)
        findings.subprocess_calls.extend(visitor.subprocess_calls)
        findings.env_var_accesses.extend(visitor.env_var_accesses)
        findings.tool_registrations.extend(visitor.tool_registrations)
        for ef in visitor.entry_functions:
            if ef not in findings.entry_functions:
                findings.entry_functions.append(ef)
        if visitor.dynamic_import_detected:
            findings.dynamic_import_detected = True
