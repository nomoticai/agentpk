"""Java signal extractor using pattern-based analysis."""

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
    ToolRegistration,
)


class JavaExtractor(ExtractorBase):
    @property
    def language(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> list[str]:
        return [".java"]

    _IMPORT = re.compile(r'^import\s+([\w.]+)\s*;', re.MULTILINE)
    _HTTP_CLIENT = re.compile(r'HttpClient|OkHttpClient|RestTemplate|WebClient|HttpURLConnection|CloseableHttpClient')
    _HTTP_POST = re.compile(r'\.post\(|\.PUT\(|\.DELETE\(|\.PATCH\(|POST\b|newBuilder.*POST', re.IGNORECASE)
    _HTTP_GET = re.compile(r'\.get\(|\.GET\b|\.newCall\(', re.IGNORECASE)
    _FILE_WRITE = re.compile(r'FileWriter|BufferedWriter|Files\.write|PrintWriter|FileOutputStream')
    _FILE_READ = re.compile(r'FileReader|BufferedReader|Files\.read|FileInputStream|Scanner\s*\(\s*new\s+File')
    _EXEC = re.compile(r'Runtime\.getRuntime\(\)\.exec|new\s+ProcessBuilder')
    _ENV = re.compile(r'System\.getenv\s*\(\s*"([^"]+)"\s*\)')
    _SPRING_TOOL = re.compile(r'@Tool\b')
    _ENTRY = re.compile(r'public\s+(?:static\s+)?void\s+(main|run|execute|invoke|handle)\s*\(', re.MULTILINE)

    def extract(self, source_files: list[Path]) -> StaticAnalysisFindings:
        findings = StaticAnalysisFindings(language="java")
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

        for m in self._IMPORT.finditer(source):
            line_num = source[:m.start()].count("\n") + 1
            findings.imports.append(ImportRecord(module=m.group(1), file=fname, line=line_num))

        has_http_client = bool(self._HTTP_CLIENT.search(source))

        for i, line in enumerate(lines, 1):
            if self._HTTP_POST.search(line) and has_http_client:
                findings.network_calls.append(NetworkCall(method="POST", library="java-http", file=fname, line=i))
            if self._HTTP_GET.search(line) and has_http_client:
                findings.network_calls.append(NetworkCall(method="GET", library="java-http", file=fname, line=i))
            if self._FILE_WRITE.search(line):
                findings.file_writes.append(FileOperation(operation="write", file=fname, line=i))
            if self._FILE_READ.search(line):
                findings.file_reads.append(FileOperation(operation="read", file=fname, line=i))
            if self._EXEC.search(line):
                findings.subprocess_calls.append(SubprocessCall(command="UNKNOWN", file=fname, line=i))
            for m in self._ENV.finditer(line):
                findings.env_var_accesses.append(EnvVarAccess(var_name=m.group(1), file=fname, line=i))
            if self._SPRING_TOOL.search(line):
                findings.tool_registrations.append(ToolRegistration(framework="spring-ai", tool_name="UNKNOWN", file=fname, line=i))

        for m in self._ENTRY.finditer(source):
            if m.group(1) not in findings.entry_functions:
                findings.entry_functions.append(m.group(1))
