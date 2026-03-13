"""Tests for agentpk.validator (6-stage pipeline) and agentpk.checksums integration."""

from __future__ import annotations

import zipfile
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from agentpk.checksums import generate_checksums, write_checksums_file
from agentpk.constants import CHECKSUMS_FILENAME, MANIFEST_FILENAME
from agentpk.manifest import compute_manifest_hash
from agentpk.validator import ValidationResult, validate_directory, validate_package


# ── helpers ────────────────────────────────────────────────────────────────

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"
FRAUD_DIR = EXAMPLES_DIR / "fraud-detection"


def _make_agent_dir(tmp_path: Path, manifest_yaml: str, files: dict[str, str] | None = None) -> Path:
    """Create a minimal agent directory with manifest.yaml and optional files."""
    root = tmp_path / "agent"
    root.mkdir()
    (root / MANIFEST_FILENAME).write_text(dedent(manifest_yaml), encoding="utf-8")
    if files:
        for rel_path, content in files.items():
            p = root / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    return root


def _minimal_manifest() -> str:
    return """\
        spec_version: "1.0"
        name: test-agent
        version: "0.1.0"
        description: "A test agent."
        runtime:
          language: python
          language_version: "3.11"
          entry_point: main.py
        execution:
          type: on-demand
    """


def _build_agent_file(
    tmp_path: Path,
    agent_dir: Path,
    *,
    inject_package_block: bool = False,
) -> Path:
    """Create a .agent ZIP from *agent_dir*, optionally with checksums and _package."""
    # Generate checksums
    checksums = generate_checksums(agent_dir)
    write_checksums_file(checksums, agent_dir / CHECKSUMS_FILENAME)

    if inject_package_block:
        manifest_path = agent_dir / MANIFEST_FILENAME
        mhash = compute_manifest_hash(manifest_path)
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        raw["_package"] = {
            "format": "agent-package-format",
            "format_version": "1.0",
            "packaged_at": "2025-01-01T00:00:00Z",
            "packaged_by": "agentpk-test",
            "manifest_hash": mhash,
            "files_hash": "sha256:placeholder",
            "total_files": len(checksums),
            "package_size_bytes": 0,
        }
        manifest_path.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        # Recompute checksums after rewriting manifest
        checksums = generate_checksums(agent_dir)
        write_checksums_file(checksums, agent_dir / CHECKSUMS_FILENAME)

    out = tmp_path / "test.agent"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(agent_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(agent_dir))
    return out


# ── Stage 1 — Pre-flight ──────────────────────────────────────────────────


class TestStage1Preflight:
    def test_missing_directory(self, tmp_path: Path) -> None:
        r = validate_directory(tmp_path / "nonexistent")
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "does not exist" in r.errors[0].message

    def test_missing_manifest(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "empty"
        agent_dir.mkdir()
        r = validate_directory(agent_dir)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert MANIFEST_FILENAME in r.errors[0].message

    def test_invalid_yaml_returns_single_error(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "bad"
        agent_dir.mkdir()
        (agent_dir / MANIFEST_FILENAME).write_text("{{bad yaml", encoding="utf-8")
        r = validate_directory(agent_dir)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "YAML" in r.errors[0].message

    def test_non_mapping_yaml(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "list"
        agent_dir.mkdir()
        (agent_dir / MANIFEST_FILENAME).write_text("- item\n", encoding="utf-8")
        r = validate_directory(agent_dir)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "mapping" in r.errors[0].message

    def test_missing_spec_version(self, tmp_path: Path) -> None:
        d = _make_agent_dir(tmp_path, "name: x\nversion: '1.0.0'\n")
        r = validate_directory(d)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "spec_version" in r.errors[0].message

    def test_unrecognised_spec_version(self, tmp_path: Path) -> None:
        d = _make_agent_dir(tmp_path, 'spec_version: "99.0"\nname: x\n')
        r = validate_directory(d)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "99.0" in r.errors[0].message

    def test_stage1_failure_stops_pipeline(self, tmp_path: Path) -> None:
        """Invalid YAML should produce exactly 1 error — no stage 2+ errors."""
        agent_dir = tmp_path / "stop"
        agent_dir.mkdir()
        (agent_dir / MANIFEST_FILENAME).write_text("{{bad", encoding="utf-8")
        r = validate_directory(agent_dir)
        assert len(r.errors) == 1
        assert len(r.warnings) == 0


# ── Stage 2 — Identity ────────────────────────────────────────────────────


class TestStage2Identity:
    def test_missing_name(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                version: "0.1.0"
                description: "no name"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert not r.is_valid
        assert any(e.field == "name" for e in r.errors)

    def test_invalid_name_format(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: "Bad Name"
                version: "0.1.0"
                description: "bad"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert not r.is_valid
        assert any(e.field == "name" for e in r.errors)

    def test_name_cannot_start_with_hyphen(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: "-bad"
                version: "0.1.0"
                description: "bad"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any(e.field == "name" for e in r.errors)

    def test_missing_version(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                description: "no version"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any(e.field == "version" for e in r.errors)

    def test_empty_description(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: ""
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any(e.field == "description" for e in r.errors)


# ── Stage 3 — File presence ───────────────────────────────────────────────


class TestStage3FilePresence:
    def test_missing_entry_point_file(self, tmp_path: Path) -> None:
        d = _make_agent_dir(tmp_path, _minimal_manifest())
        # main.py does NOT exist
        r = validate_directory(d)
        assert not r.is_valid
        assert any("entry_point" in (e.field or "") for e in r.errors)
        assert any("main.py" in e.message for e in r.errors)

    def test_missing_dependencies_file(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "deps missing"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                  dependencies: requirements.txt
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("dependencies" in (e.field or "") for e in r.errors)

    def test_existing_files_pass(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": "print('hi')"},
        )
        r = validate_directory(d)
        # No file-presence errors
        assert not any("entry_point" in (e.field or "") for e in r.errors)


# ── Stage 4 — Consistency ─────────────────────────────────────────────────


class TestStage4Consistency:
    def test_invalid_execution_type(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "bad exec"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: once
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("execution.type" in (e.field or "") for e in r.errors)

    def test_scheduled_requires_schedule(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "sched"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: scheduled
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("execution.schedule" in (e.field or "") for e in r.errors)

    def test_invalid_language(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "bad lang"
                runtime:
                  language: cobol
                  language_version: "85"
                  entry_point: main.cob
                execution:
                  type: on-demand
            """,
            files={"main.cob": ""},
        )
        r = validate_directory(d)
        assert any("runtime.language" in (e.field or "") for e in r.errors)

    def test_invalid_tool_scope(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "bad scope"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                capabilities:
                  tools:
                    - id: bad-tool
                      description: "oops"
                      scope: destroy
                      required: true
                execution:
                  type: on-demand
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("scope" in (e.field or "") for e in r.errors)

    def test_invalid_network(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "bad net"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
                resources:
                  network: full-open
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("resources.network" in (e.field or "") for e in r.errors)

    def test_permitted_windows_hours_format(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "bad hours"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
                  permitted_windows:
                    - days: [monday]
                      hours: "9am-5pm"
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("hours" in (e.field or "") for e in r.errors)

    def test_env_allowed_denied_overlap(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            """\
                spec_version: "1.0"
                name: test
                version: "1.0.0"
                description: "overlap"
                runtime:
                  language: python
                  language_version: "3.11"
                  entry_point: main.py
                execution:
                  type: on-demand
                permissions:
                  environments:
                    allowed: [API_KEY, SECRET]
                    denied: [SECRET]
            """,
            files={"main.py": ""},
        )
        r = validate_directory(d)
        assert any("environments" in (e.field or "") for e in r.errors)


# ── validate_directory — full pass ────────────────────────────────────────


class TestValidateDirectoryFullPass:
    def test_valid_directory_passes(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": "print('hello')"},
        )
        r = validate_directory(d)
        assert r.is_valid
        assert len(r.errors) == 0
        assert len(r.warnings) == 0

    def test_example_fraud_detection(self) -> None:
        r = validate_directory(FRAUD_DIR)
        assert r.is_valid, [e.message for e in r.errors]


# ── validate_package (stages 5 & 6) ──────────────────────────────────────


class TestValidatePackage:
    def test_valid_agent_file(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": "print('hello')"},
        )
        agent_file = _build_agent_file(tmp_path, d)
        r = validate_package(agent_file)
        assert r.is_valid, [e.message for e in r.errors]

    def test_missing_checksums_file(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": ""},
        )
        # Build ZIP WITHOUT writing checksums
        out = tmp_path / "nochecksum.agent"
        with zipfile.ZipFile(out, "w") as zf:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(d))
        r = validate_package(out)
        assert not r.is_valid
        assert any(CHECKSUMS_FILENAME in e.message for e in r.errors)

    def test_tampered_file_fails_checksum_stage(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": "original content"},
        )
        # Write valid checksums first
        checksums = generate_checksums(d)
        write_checksums_file(checksums, d / CHECKSUMS_FILENAME)

        # Now tamper main.py AFTER checksumming
        (d / "main.py").write_text("TAMPERED", encoding="utf-8")

        out = tmp_path / "tampered.agent"
        with zipfile.ZipFile(out, "w") as zf:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(d))

        r = validate_package(out)
        assert not r.is_valid
        assert any("mismatch" in e.message.lower() for e in r.errors)

    def test_manifest_hash_mismatch(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": ""},
        )
        # Build with _package block containing wrong manifest_hash
        manifest_path = d / MANIFEST_FILENAME
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        raw["_package"] = {
            "format": "agent-package-format",
            "format_version": "1.0",
            "packaged_at": "2025-01-01T00:00:00Z",
            "packaged_by": "test",
            "manifest_hash": "sha256:000wronghash000",
            "files_hash": "sha256:placeholder",
            "total_files": 1,
            "package_size_bytes": 0,
        }
        manifest_path.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        checksums = generate_checksums(d)
        write_checksums_file(checksums, d / CHECKSUMS_FILENAME)

        out = tmp_path / "badhash.agent"
        with zipfile.ZipFile(out, "w") as zf:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(d))

        r = validate_package(out)
        assert not r.is_valid
        assert any("manifest_hash" in (e.field or "") for e in r.errors)

    def test_not_a_zip(self, tmp_path: Path) -> None:
        bad = tmp_path / "not_zip.agent"
        bad.write_text("this is not a zip", encoding="utf-8")
        r = validate_package(bad)
        assert not r.is_valid
        assert any("ZIP" in e.message for e in r.errors)

    def test_nonexistent_package(self, tmp_path: Path) -> None:
        r = validate_package(tmp_path / "missing.agent")
        assert not r.is_valid

    def test_valid_with_package_block(self, tmp_path: Path) -> None:
        d = _make_agent_dir(
            tmp_path,
            _minimal_manifest(),
            files={"main.py": ""},
        )
        agent_file = _build_agent_file(tmp_path, d, inject_package_block=True)
        r = validate_package(agent_file)
        assert r.is_valid, [e.message for e in r.errors]


# ── ValidationResult ──────────────────────────────────────────────────────


class TestValidationResult:
    def test_empty_is_valid(self) -> None:
        r = ValidationResult()
        assert r.is_valid

    def test_add_error_makes_invalid(self) -> None:
        r = ValidationResult()
        r.add_error("boom")
        assert not r.is_valid
        assert r.errors[0].severity == "fatal"

    def test_add_warning_stays_valid(self) -> None:
        r = ValidationResult()
        r.add_warning("heads up")
        assert r.is_valid
        assert r.warnings[0].severity == "warning"
