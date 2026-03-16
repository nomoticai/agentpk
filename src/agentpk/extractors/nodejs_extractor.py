"""Node.js signal extractor using bundled JS AST helper."""

from __future__ import annotations

import json
import subprocess
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


class NodeJSExtractor(ExtractorBase):
    # Bundle path to js_ast_helper.js
    HELPER = Path(__file__).parent / "js_ast_helper.js"

    @property
    def language(self) -> str:
        return "nodejs"

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".mjs", ".cjs"]

    def extract(self, source_files: list[Path]) -> StaticAnalysisFindings:
        findings = StaticAnalysisFindings(language="nodejs")
        for path in source_files:
            if not self.supports_file(path):
                continue
            self._analyze_file(path, findings)
        return findings

    def _analyze_file(self, path: Path, findings: StaticAnalysisFindings) -> None:
        try:
            result = subprocess.run(
                ["node", str(self.HELPER), str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                findings.extractor_warnings.append(
                    f"{path.name}: node helper exited {result.returncode}: {result.stderr[:200]}"
                )
                return
            data = json.loads(result.stdout)
            self._merge(data, path, findings)
        except FileNotFoundError:
            findings.extractor_warnings.append(
                "Node.js not found on PATH; Level 2 analysis unavailable for .js files"
            )
        except subprocess.TimeoutExpired:
            findings.extractor_warnings.append(f"{path.name}: analysis timed out")
        except Exception as e:
            findings.extractor_warnings.append(f"{path.name}: {e}")

    def _merge(self, data: dict, path: Path, findings: StaticAnalysisFindings) -> None:
        fname = path.name
        for r in data.get("imports", []):
            findings.imports.append(ImportRecord(module=r["module"], file=fname, line=r["line"]))
        for r in data.get("network_calls", []):
            findings.network_calls.append(NetworkCall(method=r["method"], library=r["library"], file=fname, line=r["line"]))
        for r in data.get("file_writes", []):
            findings.file_writes.append(FileOperation(operation="write", file=fname, line=r["line"]))
        for r in data.get("file_reads", []):
            findings.file_reads.append(FileOperation(operation="read", file=fname, line=r["line"]))
        for r in data.get("subprocess_calls", []):
            findings.subprocess_calls.append(SubprocessCall(command=r.get("command", "UNKNOWN"), file=fname, line=r["line"]))
        for r in data.get("env_var_accesses", []):
            findings.env_var_accesses.append(EnvVarAccess(var_name=r.get("var_name", "UNKNOWN"), file=fname, line=r["line"]))
        for r in data.get("tool_registrations", []):
            findings.tool_registrations.append(ToolRegistration(framework=r["framework"], tool_name=r["tool_name"], file=fname, line=r["line"]))
        for fn in data.get("entry_functions", []):
            if fn not in findings.entry_functions:
                findings.entry_functions.append(fn)
        if data.get("dynamic_import_detected"):
            findings.dynamic_import_detected = True
        if data.get("obfuscated_call_detected"):
            findings.obfuscated_call_detected = True
        for w in data.get("warnings", []):
            findings.extractor_warnings.append(w)
