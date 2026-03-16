"""Go signal extractor using pattern-based analysis."""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    EnvVarAccess,
    ExtractorBase,
    FileOperation,
    ImportRecord,
    NetworkCall,
    StaticAnalysisFindings,
    SubprocessCall,
)


class GoExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> list[str]:
        return [".go"]

    # Patterns
    _IMPORT_BLOCK = re.compile(r'import\s*\(([^)]+)\)', re.DOTALL)
    _IMPORT_SINGLE = re.compile(r'import\s+"([^"]+)"')
    _HTTP_GET = re.compile(r'http\.Get\s*\(')
    _HTTP_POST = re.compile(r'http\.Post\s*\(')
    _HTTP_DO = re.compile(r'\.Do\s*\(')
    _NEW_REQUEST = re.compile(r'http\.NewRequest\s*\(\s*"(\w+)"')
    _FILE_WRITE = re.compile(r'os\.(Create|OpenFile|WriteFile)\s*\(|ioutil\.WriteFile\s*\(')
    _FILE_READ = re.compile(r'os\.Open\s*\(|ioutil\.ReadFile\s*\(|os\.ReadFile\s*\(')
    _EXEC = re.compile(r'exec\.Command\s*\(')
    _ENV = re.compile(r'os\.Getenv\s*\(\s*"([^"]+)"\s*\)|os\.LookupEnv\s*\(\s*"([^"]+)"\s*\)')
    _ENTRY = re.compile(r'^func (main|run|execute|invoke|handler)\s*\(', re.MULTILINE)

    def extract(self, source_files: list[Path]) -> StaticAnalysisFindings:
        findings = StaticAnalysisFindings(language="go")
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
        fname = path.name
        lines = source.split("\n")

        # Import extraction
        for block in self._IMPORT_BLOCK.finditer(source):
            for line_match in re.finditer(r'"([^"]+)"', block.group(1)):
                line_num = source[:block.start() + block.group(0).find(line_match.group(0))].count("\n") + 1
                findings.imports.append(ImportRecord(module=line_match.group(1), file=fname, line=line_num))
        for m in self._IMPORT_SINGLE.finditer(source):
            line_num = source[:m.start()].count("\n") + 1
            findings.imports.append(ImportRecord(module=m.group(1), file=fname, line=line_num))

        # Line-by-line signal extraction
        for i, line in enumerate(lines, 1):
            if self._HTTP_GET.search(line):
                findings.network_calls.append(NetworkCall(method="GET", library="net/http", file=fname, line=i))
            if self._HTTP_POST.search(line):
                findings.network_calls.append(NetworkCall(method="POST", library="net/http", file=fname, line=i))
            m = self._NEW_REQUEST.search(line)
            if m:
                findings.network_calls.append(NetworkCall(method=m.group(1).upper(), library="net/http", file=fname, line=i))
            if self._FILE_WRITE.search(line):
                findings.file_writes.append(FileOperation(operation="write", file=fname, line=i))
            if self._FILE_READ.search(line):
                findings.file_reads.append(FileOperation(operation="read", file=fname, line=i))
            if self._EXEC.search(line):
                findings.subprocess_calls.append(SubprocessCall(command="UNKNOWN", file=fname, line=i))
            for m in self._ENV.finditer(line):
                var = m.group(1) or m.group(2) or "UNKNOWN"
                findings.env_var_accesses.append(EnvVarAccess(var_name=var, file=fname, line=i))

        # Entry functions
        for m in self._ENTRY.finditer(source):
            if m.group(1) not in findings.entry_functions:
                findings.entry_functions.append(m.group(1))
