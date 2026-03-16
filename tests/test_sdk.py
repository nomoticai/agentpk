"""Tests for the agentpk Python SDK."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from agentpk import (
    init,
    validate,
    InitResult,
    ValidateResult,
    AgentpkError,
)
from agentpk.sdk import (
    ManifestError,
    PackageNotFoundError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def python_agent_fixture(tmp_path: Path) -> Path:
    """Create a minimal valid Python agent fixture."""
    src = tmp_path / "py-agent"
    src.mkdir()
    (src / "src").mkdir()
    (src / "src" / "agent.py").write_text(
        textwrap.dedent("""\
            def main():
                print("Hello")

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )
    (src / "requirements.txt").write_text("", encoding="utf-8")
    manifest = {
        "spec_version": "1.0",
        "name": "py-agent",
        "version": "0.1.0",
        "description": "A test Python agent.",
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


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_validate_valid_agent(self, python_agent_fixture: Path) -> None:
        result = validate(python_agent_fixture)
        assert isinstance(result, ValidateResult)
        assert result.valid is True
        assert result.errors == []

    def test_validate_invalid_manifest(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad_agent"
        bad.mkdir()
        (bad / "manifest.yaml").write_text("not: valid: yaml: [{", encoding="utf-8")
        result = validate(bad)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_never_raises(self, tmp_path: Path) -> None:
        result = validate(tmp_path / "nonexistent")
        assert result.valid is False

    def test_validate_missing_manifest(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = validate(empty)
        assert result.valid is False


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_python_scaffold(self, tmp_path: Path) -> None:
        result = init("my-agent", dest=tmp_path, runtime="python")
        assert isinstance(result, InitResult)
        assert result.project_dir.exists()
        assert (result.project_dir / "manifest.yaml").exists()
        assert (result.project_dir / "src" / "agent.py").exists()
        assert (result.project_dir / "requirements.txt").exists()
        assert result.runtime == "python"

    def test_init_nodejs_scaffold(self, tmp_path: Path) -> None:
        result = init("my-node-agent", dest=tmp_path, runtime="nodejs")
        assert (result.project_dir / "agent.js").exists()
        assert (result.project_dir / "package.json").exists()
        assert result.runtime == "nodejs"

    def test_init_typescript_scaffold(self, tmp_path: Path) -> None:
        result = init("my-ts-agent", dest=tmp_path, runtime="typescript")
        assert (result.project_dir / "agent.ts").exists()
        assert (result.project_dir / "package.json").exists()
        assert (result.project_dir / "tsconfig.json").exists()

    def test_init_go_scaffold(self, tmp_path: Path) -> None:
        result = init("my-go-agent", dest=tmp_path, runtime="go")
        assert (result.project_dir / "main.go").exists()
        assert (result.project_dir / "go.mod").exists()

    def test_init_java_scaffold(self, tmp_path: Path) -> None:
        result = init("my-java-agent", dest=tmp_path, runtime="java")
        assert (result.project_dir / "Agent.java").exists()
        assert (result.project_dir / "pom.xml").exists()

    def test_init_existing_dir_raises_without_force(self, tmp_path: Path) -> None:
        init("my-agent", dest=tmp_path, runtime="python")
        with pytest.raises(AgentpkError):
            init("my-agent", dest=tmp_path, runtime="python")

    def test_init_existing_dir_succeeds_with_force(self, tmp_path: Path) -> None:
        init("my-agent", dest=tmp_path, runtime="python")
        result = init("my-agent", dest=tmp_path, runtime="python", force=True)
        assert result.project_dir.exists()

    def test_init_manifest_has_correct_language(self, tmp_path: Path) -> None:
        """Manifest should reflect the chosen runtime."""
        for runtime in ["python", "nodejs", "typescript", "go", "java"]:
            result = init(f"test-{runtime}", dest=tmp_path, runtime=runtime)
            manifest = yaml.safe_load(
                (result.project_dir / "manifest.yaml").read_text(encoding="utf-8")
            )
            assert manifest["runtime"]["language"] == runtime


# ---------------------------------------------------------------------------
# Init + Validate integration
# ---------------------------------------------------------------------------


class TestInitValidateIntegration:
    def test_init_then_validate_python(self, tmp_path: Path) -> None:
        init_result = init("test-py", dest=tmp_path, runtime="python")
        val_result = validate(init_result.project_dir)
        assert val_result.valid is True

    def test_init_then_validate_nodejs(self, tmp_path: Path) -> None:
        init_result = init("test-node", dest=tmp_path, runtime="nodejs")
        val_result = validate(init_result.project_dir)
        assert val_result.valid is True

    def test_init_then_validate_go(self, tmp_path: Path) -> None:
        init_result = init("test-go", dest=tmp_path, runtime="go")
        val_result = validate(init_result.project_dir)
        assert val_result.valid is True

    def test_init_then_validate_java(self, tmp_path: Path) -> None:
        init_result = init("test-java", dest=tmp_path, runtime="java")
        val_result = validate(init_result.project_dir)
        assert val_result.valid is True

    def test_init_then_validate_typescript(self, tmp_path: Path) -> None:
        init_result = init("test-ts", dest=tmp_path, runtime="typescript")
        val_result = validate(init_result.project_dir)
        assert val_result.valid is True
