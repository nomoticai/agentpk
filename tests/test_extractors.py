"""Tests for the pluggable extractor architecture."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from agentpk.extractors import (
    GoExtractor,
    JavaExtractor,
    NodeJSExtractor,
    PythonExtractor,
    TypeScriptExtractor,
    get_extractor,
    supported_languages,
)
from agentpk.extractors.base import StaticAnalysisFindings


# ---------------------------------------------------------------------------
# Python Extractor
# ---------------------------------------------------------------------------


class TestPythonExtractor:
    def test_detects_http_post(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            import requests
            def main():
                resp = requests.post("https://api.example.com/data", json={})
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.network_calls) >= 1
        assert any(nc.method == "POST" for nc in findings.network_calls)

    def test_detects_http_get(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            import requests
            def main():
                resp = requests.get("https://api.example.com/data")
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.network_calls) >= 1
        assert any(nc.method == "GET" for nc in findings.network_calls)

    def test_detects_dynamic_import(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            import importlib
            mod = importlib.import_module("something")
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert findings.dynamic_import_detected is True

    def test_detects_tool_registration(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            from langchain.tools import tool

            @tool
            def search_docs(query: str) -> str:
                return "results"
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.tool_registrations) >= 1
        assert any(tr.tool_name == "search_docs" for tr in findings.tool_registrations)

    def test_detects_env_vars(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            import os
            key = os.environ.get("API_KEY")
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.env_var_accesses) >= 1
        assert any(ev.var_name == "API_KEY" for ev in findings.env_var_accesses)

    def test_detects_file_write(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            with open("output.txt", "w") as f:
                f.write("data")
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.file_writes) >= 1

    def test_detects_subprocess(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            import subprocess
            subprocess.run(["ls", "-la"])
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.subprocess_calls) >= 1

    def test_detects_entry_functions(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.py"
        src.write_text(textwrap.dedent("""\
            def main():
                pass
            def run():
                pass
        """), encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert "main" in findings.entry_functions
        assert "run" in findings.entry_functions

    def test_handles_syntax_error(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n", encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.extractor_warnings) >= 1

    def test_skips_non_py_files(self, tmp_path: Path) -> None:
        src = tmp_path / "readme.md"
        src.write_text("# Hello", encoding="utf-8")
        extractor = PythonExtractor()
        findings = extractor.extract([src])
        assert len(findings.imports) == 0

    def test_language_property(self) -> None:
        assert PythonExtractor().language == "python"

    def test_file_extensions(self) -> None:
        assert PythonExtractor().file_extensions == [".py"]


# ---------------------------------------------------------------------------
# Node.js Extractor
# ---------------------------------------------------------------------------


class TestNodeJSExtractor:
    def test_language_property(self) -> None:
        assert NodeJSExtractor().language == "nodejs"

    def test_file_extensions(self) -> None:
        exts = NodeJSExtractor().file_extensions
        assert ".js" in exts
        assert ".mjs" in exts
        assert ".cjs" in exts

    def test_falls_back_gracefully_if_node_unavailable(self, tmp_path: Path) -> None:
        src = tmp_path / "agent.js"
        src.write_text('const x = require("axios");\n', encoding="utf-8")
        extractor = NodeJSExtractor()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = extractor.extract([src])
        assert any("Node.js not found" in w for w in findings.extractor_warnings)

    def test_handles_timeout(self, tmp_path: Path) -> None:
        import subprocess
        src = tmp_path / "agent.js"
        src.write_text('console.log("hello");\n', encoding="utf-8")
        extractor = NodeJSExtractor()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("node", 10)):
            findings = extractor.extract([src])
        assert any("timed out" in w for w in findings.extractor_warnings)


# ---------------------------------------------------------------------------
# TypeScript Extractor
# ---------------------------------------------------------------------------


class TestTypeScriptExtractor:
    def test_language_property(self) -> None:
        assert TypeScriptExtractor().language == "typescript"

    def test_file_extensions(self) -> None:
        exts = TypeScriptExtractor().file_extensions
        assert ".ts" in exts
        assert ".tsx" in exts


# ---------------------------------------------------------------------------
# Go Extractor
# ---------------------------------------------------------------------------


class TestGoExtractor:
    def test_detects_http_get(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main

            import (
                "fmt"
                "net/http"
            )

            func main() {
                resp, _ := http.Get("https://api.example.com")
                fmt.Println(resp.StatusCode)
            }
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        assert len(findings.network_calls) >= 1
        assert any(nc.method == "GET" for nc in findings.network_calls)

    def test_detects_exec_command(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main

            import "os/exec"

            func main() {
                cmd := exec.Command("ls", "-la")
                cmd.Run()
            }
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        assert len(findings.subprocess_calls) >= 1

    def test_detects_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main

            import (
                "fmt"
                "net/http"
                "os"
            )

            func main() {}
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        modules = [i.module for i in findings.imports]
        assert "fmt" in modules
        assert "net/http" in modules
        assert "os" in modules

    def test_detects_env_vars(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main
            import "os"
            func main() {
                key := os.Getenv("API_KEY")
                _ = key
            }
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        assert len(findings.env_var_accesses) >= 1
        assert any(ev.var_name == "API_KEY" for ev in findings.env_var_accesses)

    def test_detects_entry_functions(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main
            func main() {}
            func run() {}
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        assert "main" in findings.entry_functions
        assert "run" in findings.entry_functions

    def test_detects_file_operations(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(textwrap.dedent("""\
            package main
            import "os"
            func main() {
                f, _ := os.Create("output.txt")
                f.Close()
                data, _ := os.ReadFile("input.txt")
                _ = data
            }
        """), encoding="utf-8")
        extractor = GoExtractor()
        findings = extractor.extract([src])
        assert len(findings.file_writes) >= 1
        assert len(findings.file_reads) >= 1

    def test_language_property(self) -> None:
        assert GoExtractor().language == "go"

    def test_file_extensions(self) -> None:
        assert GoExtractor().file_extensions == [".go"]


# ---------------------------------------------------------------------------
# Java Extractor
# ---------------------------------------------------------------------------


class TestJavaExtractor:
    def test_detects_http_client(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            import java.net.http.HttpClient;
            import java.net.http.HttpRequest;
            public class Agent {
                public void run() {
                    HttpClient client = HttpClient.newHttpClient();
                    HttpRequest request = HttpRequest.newBuilder()
                        .GET()
                        .build();
                }
            }
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        assert len(findings.network_calls) >= 1
        assert any(nc.method == "GET" for nc in findings.network_calls)

    def test_detects_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            import java.net.http.HttpClient;
            import java.io.FileWriter;
            public class Agent {}
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        modules = [i.module for i in findings.imports]
        assert "java.net.http.HttpClient" in modules
        assert "java.io.FileWriter" in modules

    def test_detects_env_vars(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            public class Agent {
                public void run() {
                    String key = System.getenv("API_KEY");
                }
            }
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        assert len(findings.env_var_accesses) >= 1
        assert any(ev.var_name == "API_KEY" for ev in findings.env_var_accesses)

    def test_detects_spring_tool(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            public class Agent {
                @Tool
                public String fetchData(String query) {
                    return "result";
                }
            }
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        assert len(findings.tool_registrations) >= 1
        assert any(tr.framework == "spring-ai" for tr in findings.tool_registrations)

    def test_detects_file_operations(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            import java.io.FileWriter;
            import java.io.FileReader;
            public class Agent {
                public void run() {
                    FileWriter writer = new FileWriter("out.txt");
                    FileReader reader = new FileReader("in.txt");
                }
            }
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        assert len(findings.file_writes) >= 1
        assert len(findings.file_reads) >= 1

    def test_detects_entry_functions(self, tmp_path: Path) -> None:
        src = tmp_path / "Agent.java"
        src.write_text(textwrap.dedent("""\
            public class Agent {
                public static void main(String[] args) {}
                public void run() {}
            }
        """), encoding="utf-8")
        extractor = JavaExtractor()
        findings = extractor.extract([src])
        assert "main" in findings.entry_functions
        assert "run" in findings.entry_functions

    def test_language_property(self) -> None:
        assert JavaExtractor().language == "java"

    def test_file_extensions(self) -> None:
        assert JavaExtractor().file_extensions == [".java"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestExtractorRegistry:
    def test_all_languages_registered(self) -> None:
        for lang in ["python", "nodejs", "typescript", "go", "java"]:
            assert lang in supported_languages()

    def test_unsupported_language_returns_none(self) -> None:
        assert get_extractor("cobol") is None

    def test_findings_schema_consistent_across_extractors(self, tmp_path: Path) -> None:
        """Each extractor on an empty file should return a valid StaticAnalysisFindings."""
        for lang in ["python", "go", "java"]:
            extractor = get_extractor(lang)
            assert extractor is not None
            findings = extractor.extract([])
            assert isinstance(findings, StaticAnalysisFindings)
            assert findings.language == lang
            assert isinstance(findings.imports, list)
            assert isinstance(findings.network_calls, list)
            assert isinstance(findings.entry_functions, list)
