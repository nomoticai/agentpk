"""Tests for the agent analyzer module (agentpk.analyzer)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from agentpk.analyzer import (
    AnalysisResult,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    LevelResult,
    StaticAnalysisFindings,
    analyze,
    build_analysis_block,
    calculate_trust_score,
    generate_manifest_from_analysis,
    get_review_fields,
    run_level1,
    run_level2,
)
from agentpk.cli import cli
from agentpk.constants import (
    LEVEL_SKIP_PENALTIES,
    LEVEL_WEIGHTS,
    trust_label,
)
from agentpk.packer import pack

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_with_network(tmp_path: Path) -> Path:
    """Create a Python agent that makes network calls (requests.post)."""
    src = tmp_path / "net-agent"
    src.mkdir()
    (src / "src").mkdir()
    (src / "src" / "agent.py").write_text(
        textwrap.dedent("""\
            import requests
            import os

            def main():
                api_key = os.environ.get("API_KEY")
                resp = requests.post("https://api.example.com/data", json={"key": api_key})
                return resp.json()

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )
    (src / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")
    return src


@pytest.fixture()
def agent_with_tools(tmp_path: Path) -> Path:
    """Create a Python agent with LangChain-style tool decorators."""
    src = tmp_path / "tool-agent"
    src.mkdir()
    (src / "src").mkdir()
    (src / "src" / "agent.py").write_text(
        textwrap.dedent("""\
            from langchain.tools import tool

            @tool
            def search_documents(query: str) -> str:
                \"\"\"Search the document database.\"\"\"
                return f"Results for: {query}"

            @tool
            def write_report(content: str) -> str:
                \"\"\"Write a report to disk.\"\"\"
                with open("report.txt", "w") as f:
                    f.write(content)
                return "Report written"

            def main():
                result = search_documents("test query")
                write_report(result)

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )
    (src / "requirements.txt").write_text("langchain>=0.1\n", encoding="utf-8")
    return src


@pytest.fixture()
def agent_with_db(tmp_path: Path) -> Path:
    """Create a Python agent with database imports."""
    src = tmp_path / "db-agent"
    src.mkdir()
    (src / "src").mkdir()
    (src / "src" / "agent.py").write_text(
        textwrap.dedent("""\
            import psycopg2

            def main():
                conn = psycopg2.connect("dbname=test")
                cur = conn.cursor()
                cur.execute("SELECT * FROM users")
                return cur.fetchall()

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )
    (src / "requirements.txt").write_text("psycopg2>=2.9\n", encoding="utf-8")
    return src


@pytest.fixture()
def agent_with_manifest(tmp_path: Path) -> Path:
    """Create a clean agent with accurate manifest (no discrepancies expected)."""
    src = tmp_path / "clean-agent"
    src.mkdir()
    (src / "src").mkdir()
    (src / "src" / "agent.py").write_text(
        textwrap.dedent("""\
            def main():
                print("Hello from clean agent")

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )
    (src / "requirements.txt").write_text("", encoding="utf-8")
    manifest = {
        "spec_version": "1.0",
        "name": "clean-agent",
        "version": "0.1.0",
        "description": "A clean test agent.",
        "runtime": {
            "language": "python",
            "language_version": "3.11",
            "entry_point": "src/agent.py",
            "entry_function": "main",
            "dependencies": "requirements.txt",
        },
        "capabilities": {"tools": []},
        "execution": {"type": "on-demand"},
    }
    (src / "manifest.yaml").write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return src


def _make_manifest(src: Path, *, tools: list | None = None, data_classes: list | None = None) -> Path:
    """Write a manifest.yaml into src and return its path."""
    manifest: dict = {
        "spec_version": "1.0",
        "name": src.name,
        "version": "0.1.0",
        "description": f"Test agent: {src.name}",
        "runtime": {
            "language": "python",
            "language_version": "3.11",
            "entry_point": "src/agent.py",
            "entry_function": "main",
            "dependencies": "requirements.txt",
        },
        "capabilities": {"tools": tools or []},
        "execution": {"type": "on-demand"},
    }
    if data_classes:
        manifest["permissions"] = {"data_classes": data_classes}
    path = src / "manifest.yaml"
    path.write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Level 2 — Static analysis
# ---------------------------------------------------------------------------


class TestLevel2StaticAnalysis:
    """Tests for static AST analysis."""

    def test_detects_network_calls(self, agent_with_network: Path) -> None:
        """Static analysis finds requests.post even when not declared."""
        lr, findings = run_level2(agent_with_network)
        assert lr.ran is True
        assert len(findings.network_calls) >= 1
        assert any("requests.post" in nc for nc in findings.network_calls)

    def test_detects_tool_registrations(self, agent_with_tools: Path) -> None:
        """LangChain @tool decorators are detected and counted."""
        lr, findings = run_level2(agent_with_tools)
        assert lr.ran is True
        assert len(findings.tool_registrations) >= 2
        # Should detect both search_documents and write_report
        all_regs = " ".join(findings.tool_registrations)
        assert "search_documents" in all_regs
        assert "write_report" in all_regs

    def test_detects_env_vars(self, agent_with_network: Path) -> None:
        """Environment variable access is detected."""
        lr, findings = run_level2(agent_with_network)
        assert lr.ran is True
        assert len(findings.env_vars_read) >= 1
        assert any("API_KEY" in ev for ev in findings.env_vars_read)

    def test_detects_file_writes(self, agent_with_tools: Path) -> None:
        """File write operations are detected."""
        lr, findings = run_level2(agent_with_tools)
        assert lr.ran is True
        assert len(findings.file_writes) >= 1

    def test_detects_entry_functions(self, agent_with_network: Path) -> None:
        """Entry functions (main, run, etc.) are detected."""
        lr, findings = run_level2(agent_with_network)
        assert lr.ran is True
        assert len(findings.entry_functions) >= 1
        assert any("main" in ef for ef in findings.entry_functions)

    def test_flags_undeclared_database(self, agent_with_db: Path) -> None:
        """psycopg2 import without data_class declaration is a MAJOR discrepancy."""
        # Create manifest without data_classes
        _make_manifest(agent_with_db)
        manifest_data = yaml.safe_load(
            (agent_with_db / "manifest.yaml").read_text(encoding="utf-8")
        )
        lr, findings = run_level2(agent_with_db, manifest=manifest_data)
        assert lr.ran is True
        # Should have discrepancy for undeclared database
        db_discreps = [
            d
            for d in lr.discrepancies
            if "database" in d.description.lower() or "data_class" in d.description.lower()
        ]
        assert len(db_discreps) >= 1
        assert db_discreps[0].severity == DiscrepancySeverity.MAJOR

    def test_no_discrepancies_on_matching_manifest(
        self, agent_with_manifest: Path
    ) -> None:
        """Clean agent with accurate manifest scores full Level 2 points."""
        manifest_data = yaml.safe_load(
            (agent_with_manifest / "manifest.yaml").read_text(encoding="utf-8")
        )
        lr, findings = run_level2(agent_with_manifest, manifest=manifest_data)
        assert lr.ran is True
        assert lr.passed is True
        assert lr.score == LEVEL_WEIGHTS[2]
        assert len(lr.discrepancies) == 0

    def test_detects_language(self, agent_with_network: Path) -> None:
        """Detected language should be 'python' for .py files."""
        lr, findings = run_level2(agent_with_network)
        assert findings.detected_language == "python"

    def test_network_without_manifest_tools(self, agent_with_network: Path) -> None:
        """Network calls without declared tools produce discrepancies."""
        # Manifest with no tools
        _make_manifest(agent_with_network, tools=[])
        manifest_data = yaml.safe_load(
            (agent_with_network / "manifest.yaml").read_text(encoding="utf-8")
        )
        lr, findings = run_level2(agent_with_network, manifest=manifest_data)
        assert lr.ran is True
        # Should flag undeclared network calls
        net_discreps = [
            d for d in lr.discrepancies if "network" in d.description.lower()
        ]
        assert len(net_discreps) >= 1


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------


class TestScoreCalculation:
    """Tests for trust score calculation."""

    def test_all_levels_skipped(self) -> None:
        """Score floors at 0, never negative."""
        results = [
            LevelResult(level=1, name="L1", ran=False, passed=False, score=0),
            LevelResult(level=2, name="L2", ran=False, passed=False, score=0),
            LevelResult(level=3, name="L3", ran=False, passed=False, score=0),
            LevelResult(level=4, name="L4", ran=False, passed=False, score=0),
        ]
        score = calculate_trust_score(results)
        assert score == 0  # -10 + -20 + -15 + -25 = -70, floored to 0

    def test_all_levels_perfect(self) -> None:
        """Perfect score with all levels passed."""
        results = [
            LevelResult(level=1, name="L1", ran=True, passed=True, score=20),
            LevelResult(level=2, name="L2", ran=True, passed=True, score=30),
            LevelResult(level=3, name="L3", ran=True, passed=True, score=25),
            LevelResult(level=4, name="L4", ran=True, passed=True, score=25),
        ]
        score = calculate_trust_score(results)
        assert score == 100

    def test_level3_skipped(self) -> None:
        """Level 3 skip subtracts 15 points from otherwise perfect score."""
        results = [
            LevelResult(level=1, name="L1", ran=True, passed=True, score=20),
            LevelResult(level=2, name="L2", ran=True, passed=True, score=30),
            LevelResult(level=3, name="L3", ran=False, passed=False, score=0),
            LevelResult(level=4, name="L4", ran=True, passed=True, score=25),
        ]
        score = calculate_trust_score(results)
        # 20 + 30 + 0 + 25 - 15 (skip penalty) = 60
        assert score == 60

    def test_level3_and_4_skipped(self) -> None:
        """Levels 3+4 skipped: 20 + 30 - 15 - 25 = 10."""
        results = [
            LevelResult(level=1, name="L1", ran=True, passed=True, score=20),
            LevelResult(level=2, name="L2", ran=True, passed=True, score=30),
            LevelResult(level=3, name="L3", ran=False, passed=False, score=0),
            LevelResult(level=4, name="L4", ran=False, passed=False, score=0),
        ]
        score = calculate_trust_score(results)
        assert score == 10  # 20 + 30 - 15 - 25 = 10

    def test_discrepancies_reduce_score(self) -> None:
        """Discrepancies in a level reduce that level's contribution."""
        results = [
            LevelResult(level=1, name="L1", ran=True, passed=True, score=20),
            LevelResult(level=2, name="L2", ran=True, passed=False, score=10),  # reduced by discrepancies
        ]
        score = calculate_trust_score(results)
        # 20 + 10 - 15 (L3 skip) - 25 (L4 skip) = -10, floored to 0
        assert score == 0


# ---------------------------------------------------------------------------
# Trust labels
# ---------------------------------------------------------------------------


class TestTrustLabels:
    """Tests for trust label boundaries."""

    def test_verified(self) -> None:
        assert trust_label(100) == "Verified"
        assert trust_label(90) == "Verified"

    def test_high(self) -> None:
        assert trust_label(89) == "High"
        assert trust_label(75) == "High"

    def test_moderate(self) -> None:
        assert trust_label(74) == "Moderate"
        assert trust_label(60) == "Moderate"

    def test_low(self) -> None:
        assert trust_label(59) == "Low"
        assert trust_label(40) == "Low"

    def test_unverified(self) -> None:
        assert trust_label(39) == "Unverified"
        assert trust_label(0) == "Unverified"


# ---------------------------------------------------------------------------
# Level 1 — Structural validation
# ---------------------------------------------------------------------------


class TestLevel1:
    """Tests for structural validation."""

    def test_no_manifest(self, tmp_path: Path) -> None:
        """No manifest returns skipped."""
        lr = run_level1(tmp_path / "nonexistent.yaml")
        assert lr.ran is False
        assert lr.score == 0

    def test_valid_manifest(self, agent_with_manifest: Path) -> None:
        """Valid manifest passes."""
        lr = run_level1(agent_with_manifest / "manifest.yaml")
        assert lr.ran is True
        assert lr.passed is True
        assert lr.score == LEVEL_WEIGHTS[1]


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


class TestGenerateManifest:
    """Tests for manifest generation from analysis findings."""

    def test_generates_manifest_from_findings(self, agent_with_tools: Path) -> None:
        """Generated manifest contains detected tools and correct entry point."""
        result = analyze(agent_with_tools, level=2, mode="generate")
        assert result.suggested_manifest is not None
        manifest = result.suggested_manifest

        assert manifest["name"] == "tool-agent"
        assert manifest["runtime"]["language"] == "python"
        assert "entry_point" in manifest["runtime"]
        assert "tools" in manifest.get("capabilities", {})

        # Should detect tool registrations
        tools = manifest["capabilities"]["tools"]
        tool_ids = [t["id"] for t in tools]
        assert "search_documents" in tool_ids or "write_report" in tool_ids

    def test_generate_with_review_markers(self, agent_with_network: Path) -> None:
        """Generated manifest should have REVIEW markers for undetermined fields."""
        result = analyze(agent_with_network, level=2, mode="generate")
        assert result.suggested_manifest is not None
        manifest = result.suggested_manifest

        review_fields = get_review_fields(manifest)
        assert len(review_fields) > 0
        # display_name and author should be review fields
        assert any("display_name" in f for f in review_fields)
        assert any("author" in f for f in review_fields)


# ---------------------------------------------------------------------------
# Pack with --analyze
# ---------------------------------------------------------------------------


class TestPackAnalyze:
    """Tests for pack --analyze integration."""

    def test_pack_analyze_embeds_analysis_block(self, agent_with_manifest: Path, tmp_path: Path) -> None:
        """Packed .agent file contains analysis block in _package."""
        from agentpk.analyzer import analyze as run_analysis, build_analysis_block

        analysis_result = run_analysis(agent_with_manifest, level=2, mode="verify")
        analysis_block = build_analysis_block(analysis_result)

        out = tmp_path / "output" / "clean-agent-0.1.0.agent"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = pack(agent_with_manifest, output_path=out, analysis_block=analysis_block)
        assert result.success

        # Extract and check the _package block
        import zipfile
        with zipfile.ZipFile(out, "r") as zf:
            manifest_text = zf.read("manifest.yaml").decode("utf-8")
        raw = yaml.safe_load(manifest_text)
        pkg = raw.get("_package", {})
        assert "analysis" in pkg
        assert pkg["analysis"]["trust_score"] >= 0
        assert pkg["analysis"]["trust_label"] in ("Verified", "High", "Moderate", "Low", "Unverified")
        assert 2 in pkg["analysis"]["levels_run"]

    def test_pack_without_analyze_has_no_analysis(self, agent_with_manifest: Path, tmp_path: Path) -> None:
        """Packed file without --analyze has no analysis block."""
        out = tmp_path / "output" / "clean-agent-0.1.0.agent"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = pack(agent_with_manifest, output_path=out)
        assert result.success

        import zipfile
        with zipfile.ZipFile(out, "r") as zf:
            manifest_text = zf.read("manifest.yaml").decode("utf-8")
        raw = yaml.safe_load(manifest_text)
        pkg = raw.get("_package", {})
        assert "analysis" not in pkg

    def test_pack_analyze_strict_fails_without_llm(
        self, agent_with_manifest: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--strict --level 3 fails when no LLM API key is present."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "pack",
                str(agent_with_manifest),
                "--analyze",
                "--level",
                "3",
                "--strict",
            ],
        )
        assert result.exit_code != 0

    def test_pack_analyze_no_strict_degrades_gracefully(
        self, agent_with_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --strict, missing LLM subtracts points but packs successfully."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        out = tmp_path / "output"
        out.mkdir(parents=True, exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "pack",
                str(agent_with_manifest),
                "--analyze",
                "--level",
                "3",
                "--out-dir",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert "Packed successfully" in result.output


# ---------------------------------------------------------------------------
# CLI generate command
# ---------------------------------------------------------------------------


class TestGenerateCommand:
    """CLI tests for agent generate."""

    def test_generate_cli(self, agent_with_network: Path) -> None:
        """agent generate produces a manifest.yaml."""
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", str(agent_with_network), "--level", "2"])
        assert result.exit_code == 0
        assert "manifest.yaml written" in result.output
        assert (agent_with_network / "manifest.yaml").exists()

    def test_generate_refuses_existing_manifest(self, agent_with_manifest: Path) -> None:
        """agent generate refuses if manifest.yaml exists and --force not set."""
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", str(agent_with_manifest)])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_generate_force_overwrites(self, agent_with_manifest: Path) -> None:
        """agent generate --force overwrites existing manifest."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["generate", str(agent_with_manifest), "--force", "--level", "2"]
        )
        assert result.exit_code == 0
        assert "manifest.yaml written" in result.output


# ---------------------------------------------------------------------------
# Inspect trust score display
# ---------------------------------------------------------------------------


class TestInspectTrustScore:
    """Tests for inspect command displaying trust score."""

    def test_inspect_shows_unverified_without_analysis(self, agent_with_manifest: Path, tmp_path: Path) -> None:
        """Inspect shows 'unverified' for packages without analysis."""
        out = tmp_path / "output" / "clean-agent-0.1.0.agent"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = pack(agent_with_manifest, output_path=out)
        assert result.success

        runner = CliRunner()
        result = runner.invoke(cli, ["inspect", str(out)])
        assert result.exit_code == 0
        assert "unverified" in result.output.lower()

    def test_inspect_shows_score_with_analysis(self, agent_with_manifest: Path, tmp_path: Path) -> None:
        """Inspect shows trust score for analyzed packages."""
        from agentpk.analyzer import analyze as run_analysis, build_analysis_block

        analysis_result = run_analysis(agent_with_manifest, level=2, mode="verify")
        analysis_block = build_analysis_block(analysis_result)

        out = tmp_path / "output" / "clean-agent-0.1.0.agent"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = pack(agent_with_manifest, output_path=out, analysis_block=analysis_block)
        assert result.success

        runner = CliRunner()
        result = runner.invoke(cli, ["inspect", str(out)])
        assert result.exit_code == 0
        assert "/100" in result.output


# ---------------------------------------------------------------------------
# Analysis block builder
# ---------------------------------------------------------------------------


class TestAnalysisBlock:
    """Tests for the analysis block builder."""

    def test_build_analysis_block_structure(self, agent_with_manifest: Path) -> None:
        """Analysis block has all required fields."""
        result = analyze(agent_with_manifest, level=2, mode="verify")
        block = build_analysis_block(result)

        assert "level_requested" in block
        assert "levels_run" in block
        assert "levels_skipped" in block
        assert "trust_score" in block
        assert "trust_label" in block
        assert "discrepancies" in block
        assert "analyzed_at" in block
        assert "static_findings_summary" in block

    def test_block_contains_findings_summary(self, agent_with_manifest: Path) -> None:
        """Analysis block contains static findings summary."""
        result = analyze(agent_with_manifest, level=2, mode="verify")
        block = build_analysis_block(result)
        summary = block["static_findings_summary"]
        assert "imports_detected" in summary
        assert "network_calls" in summary
        assert "tool_registrations" in summary
        assert "undeclared_capabilities" in summary
