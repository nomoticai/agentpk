"""Tests for agentpk.manifest and agentpk.models."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from agentpk.exceptions import ManifestNotFoundError, ManifestParseError
from agentpk.manifest import compute_manifest_hash, dump_manifest, load_manifest
from agentpk.models import (
    AgentManifest,
    CapabilitiesConfig,
    ExecutionConfig,
    PackageMetadata,
    RuntimeConfig,
    ToolDeclaration,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "valid"
FRAUD_MANIFEST = EXAMPLES_DIR / "fraud-detection" / "manifest.yaml"


# ── helpers ────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, text: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "manifest.yaml"
    p.write_text(dedent(text), encoding="utf-8")
    return p


def _minimal_yaml() -> str:
    """Smallest valid manifest YAML."""
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


# ── load_manifest ─────────────────────────────────────────────────────────


class TestLoadManifest:
    def test_load_example_fraud_detection(self) -> None:
        m = load_manifest(FRAUD_MANIFEST)
        assert m.name == "fraud-detection"
        assert m.version == "0.1.0"
        assert m.spec_version == "1.0"
        assert m.runtime.language == "python"
        assert m.runtime.language_version == "3.11"
        assert m.runtime.entry_point == "src/agent.py"
        assert len(m.capabilities.tools) == 3

    def test_load_example_tools(self) -> None:
        m = load_manifest(FRAUD_MANIFEST)
        tool_ids = [t.id for t in m.capabilities.tools]
        assert tool_ids == [
            "scan_transaction",
            "flag_transaction",
            "alert_compliance_team",
        ]
        scan = m.capabilities.tools[0]
        assert scan.scope == "read"
        assert scan.required is True

        alert = m.capabilities.tools[2]
        assert alert.scope == "write"
        assert alert.required is False

    def test_load_minimal(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, _minimal_yaml())
        m = load_manifest(p)
        assert m.name == "test-agent"
        assert m.package_metadata is None

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestNotFoundError):
            load_manifest(tmp_path / "nonexistent.yaml")

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "{{bad yaml")
        with pytest.raises(ManifestParseError):
            load_manifest(p)

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(ManifestParseError, match="mapping"):
            load_manifest(p)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        # Missing 'name' field
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            version: "0.1.0"
            description: "Missing name."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError):
            load_manifest(p)

    def test_package_metadata_from_yaml(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: pkg-test
            version: "1.0.0"
            description: "With package block."
            runtime:
              language: python
              language_version: "3.12"
              entry_point: main.py
            execution:
              type: on-demand
            _package:
              format: agent-package-format
              format_version: "1.0"
              packaged_at: "2025-01-01T00:00:00Z"
              packaged_by: agentpk
              manifest_hash: "sha256:abc123"
              files_hash: "sha256:def456"
              total_files: 5
              package_size_bytes: 1024
            """,
        )
        m = load_manifest(p)
        assert m.package_metadata is not None
        assert m.package_metadata.format_version == "1.0"
        assert m.package_metadata.total_files == 5


# ── validation errors for invalid field values ────────────────────────────


class TestModelValidation:
    def test_invalid_language(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-lang
            version: "0.1.0"
            description: "Bad language."
            runtime:
              language: cobol
              language_version: "85"
              entry_point: main.cob
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="language"):
            load_manifest(p)

    def test_invalid_scope(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-scope
            version: "0.1.0"
            description: "Bad scope."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            capabilities:
              tools:
                - id: tool1
                  description: "A tool."
                  scope: destroy
                  required: true
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="scope"):
            load_manifest(p)

    def test_invalid_execution_type(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-exec
            version: "0.1.0"
            description: "Bad exec type."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: once
            """,
        )
        with pytest.raises(ManifestParseError, match="execution type"):
            load_manifest(p)

    def test_invalid_name_uppercase(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: BadName
            version: "0.1.0"
            description: "Uppercase."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="lowercase"):
            load_manifest(p)

    def test_invalid_name_spaces(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: "bad name"
            version: "0.1.0"
            description: "Spaces."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="lowercase"):
            load_manifest(p)

    def test_invalid_version_not_semver(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-ver
            version: "v1"
            description: "Bad version."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="semantic version"):
            load_manifest(p)

    def test_invalid_network(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-net
            version: "0.1.0"
            description: "Bad network."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            execution:
              type: on-demand
            resources:
              network: full-open
            """,
        )
        with pytest.raises(ManifestParseError, match="network"):
            load_manifest(p)

    def test_invalid_framework(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: bad-fw
            version: "0.1.0"
            description: "Bad framework."
            runtime:
              language: python
              language_version: "3.11"
              entry_point: main.py
            framework:
              name: django
            execution:
              type: on-demand
            """,
        )
        with pytest.raises(ManifestParseError, match="framework name"):
            load_manifest(p)



# ── compute_manifest_hash ─────────────────────────────────────────────────


class TestComputeManifestHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, _minimal_yaml())
        h1 = compute_manifest_hash(p)
        h2 = compute_manifest_hash(p)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_content(self, tmp_path: Path) -> None:
        p1 = tmp_path / "a.yaml"
        p1.write_text(dedent(_minimal_yaml()), encoding="utf-8")

        p2 = tmp_path / "b.yaml"
        alt = _minimal_yaml().replace("test-agent", "other-agent")
        p2.write_text(dedent(alt), encoding="utf-8")

        assert compute_manifest_hash(p1) != compute_manifest_hash(p2)

    def test_strips_package_block(self, tmp_path: Path) -> None:
        base_yaml = dedent(_minimal_yaml())
        f_without = tmp_path / "without.yaml"
        f_without.write_text(base_yaml, encoding="utf-8")

        with_pkg = base_yaml + dedent("""\
            _package:
              format: agent-package-format
              format_version: "1.0"
              packaged_at: "2025-01-01T00:00:00Z"
              packaged_by: agentpk
              manifest_hash: "sha256:000"
              files_hash: "sha256:000"
              total_files: 1
              package_size_bytes: 100
        """)
        f_with = tmp_path / "with.yaml"
        f_with.write_text(with_pkg, encoding="utf-8")

        assert compute_manifest_hash(f_without) == compute_manifest_hash(f_with)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestNotFoundError):
            compute_manifest_hash(tmp_path / "nope.yaml")


# ── dump_manifest & round-trip ────────────────────────────────────────────


class TestDumpManifest:
    def test_roundtrip_minimal(self, tmp_path: Path) -> None:
        src = _write_yaml(tmp_path, _minimal_yaml())
        original = load_manifest(src)

        out = tmp_path / "out.yaml"
        dump_manifest(original, out)

        reloaded = load_manifest(out)
        assert reloaded.name == original.name
        assert reloaded.version == original.version
        assert reloaded.runtime.language == original.runtime.language
        assert reloaded.execution.type == original.execution.type

    def test_roundtrip_full(self, tmp_path: Path) -> None:
        """Load the example, dump it, reload — models should match."""
        original = load_manifest(FRAUD_MANIFEST)

        out = tmp_path / "roundtrip.yaml"
        dump_manifest(original, out)

        reloaded = load_manifest(out)
        assert reloaded.name == original.name
        assert reloaded.version == original.version
        assert len(reloaded.capabilities.tools) == len(original.capabilities.tools)
        for orig_t, new_t in zip(
            original.capabilities.tools, reloaded.capabilities.tools
        ):
            assert orig_t.id == new_t.id
            assert orig_t.scope == new_t.scope
            assert orig_t.required == new_t.required

    def test_roundtrip_with_package_metadata(self, tmp_path: Path) -> None:
        src = _write_yaml(
            tmp_path,
            """\
            spec_version: "1.0"
            name: pkg-rt
            version: "2.0.0"
            description: "Round-trip with package."
            runtime:
              language: go
              language_version: "1.21"
              entry_point: main.go
            execution:
              type: triggered
            _package:
              format: agent-package-format
              format_version: "1.0"
              packaged_at: "2025-06-01T12:00:00Z"
              packaged_by: agentpk
              manifest_hash: "sha256:aaa"
              files_hash: "sha256:bbb"
              total_files: 3
              package_size_bytes: 2048
            """,
        )
        original = load_manifest(src)
        assert original.package_metadata is not None

        out = tmp_path / "pkg_out.yaml"
        dump_manifest(original, out)

        reloaded = load_manifest(out)
        assert reloaded.package_metadata is not None
        assert reloaded.package_metadata.format_version == "1.0"
        assert reloaded.package_metadata.total_files == 3

    def test_dump_excludes_none_fields(self, tmp_path: Path) -> None:
        src = _write_yaml(tmp_path, _minimal_yaml())
        m = load_manifest(src)

        out = tmp_path / "sparse.yaml"
        dump_manifest(m, out)

        raw = out.read_text(encoding="utf-8")
        assert "_package" not in raw
        assert "framework" not in raw
