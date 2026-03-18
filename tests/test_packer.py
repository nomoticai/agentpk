"""Tests for agentpk.packer."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

from agentpk.constants import CHECKSUMS_FILENAME, MANIFEST_FILENAME
from agentpk.exceptions import PackageCorruptError
from agentpk.packer import PackResult, inspect, pack, unpack


# ── helpers ────────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal valid agent project tree and return its root."""
    project = tmp_path / "my-agent"
    project.mkdir()
    (project / "src").mkdir()

    manifest = {
        "spec_version": "1.0",
        "name": "my-agent",
        "version": "0.1.0",
        "description": "A test agent.",
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
    (project / MANIFEST_FILENAME).write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    (project / "src" / "agent.py").write_text(
        'def main():\n    print("hello")\n', encoding="utf-8"
    )
    (project / "requirements.txt").write_text("# none\n", encoding="utf-8")
    return project


def _copy_fraud_detection(tmp_path: Path) -> Path:
    """Copy the examples/fraud-detection fixture into tmp_path and return its root."""
    src = Path(__file__).resolve().parent.parent / "examples" / "valid" / "fraud-detection"
    dest = tmp_path / "fraud-detection"
    shutil.copytree(src, dest)
    return dest


# ── pack ───────────────────────────────────────────────────────────────────


class TestPack:
    def test_pack_creates_valid_agent_file(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project)

        assert result.success
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.output_path.suffix == ".agent"
        assert result.size_bytes > 0
        assert result.file_count > 0
        assert result.manifest_hash.startswith("sha256:")
        assert result.files_hash.startswith("sha256:")

        # Must be a valid archive
        assert zipfile.is_zipfile(result.output_path)

    def test_pack_output_contains_manifest_and_checksums(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project)

        assert result.success and result.output_path is not None
        with zipfile.ZipFile(result.output_path, "r") as zf:
            names = zf.namelist()
            assert MANIFEST_FILENAME in names
            assert CHECKSUMS_FILENAME in names

    def test_pack_dry_run_produces_no_file(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project, dry_run=True)

        assert result.success
        assert result.output_path is not None
        # Dry run: the output path is computed but the file is NOT created
        assert not result.output_path.exists()
        assert result.size_bytes == 0
        assert result.manifest_hash.startswith("sha256:")

    def test_pack_custom_output_path(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        out = tmp_path / "custom.agent"
        result = pack(project, output_path=out)

        assert result.success
        assert result.output_path == out
        assert out.exists()

    def test_pack_rejects_invalid_source(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "nonexistent"
        bad_dir.mkdir()
        # No manifest
        result = pack(bad_dir)

        assert not result.success
        assert len(result.errors) > 0

    def test_pack_rejects_missing_directory(self, tmp_path: Path) -> None:
        result = pack(tmp_path / "does-not-exist")
        assert not result.success

    def test_pack_restores_source_directory(self, tmp_path: Path) -> None:
        """After packing, source dir should be restored to original state."""
        project = _make_project(tmp_path)

        manifest_before = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")
        had_checksums = (project / CHECKSUMS_FILENAME).exists()

        pack(project)

        manifest_after = (project / MANIFEST_FILENAME).read_text(encoding="utf-8")
        assert manifest_before == manifest_after
        # Checksums file should not linger if it wasn't there before
        if not had_checksums:
            assert not (project / CHECKSUMS_FILENAME).exists()

    def test_pack_fraud_detection_example(self, tmp_path: Path) -> None:
        project = _copy_fraud_detection(tmp_path)
        result = pack(project)

        assert result.success
        assert result.output_path is not None
        assert result.output_path.exists()

    def test_pack_manifest_contains_package_block(self, tmp_path: Path) -> None:
        """The .agent file's manifest should have a _package block."""
        project = _make_project(tmp_path)
        result = pack(project)

        assert result.success and result.output_path is not None
        with zipfile.ZipFile(result.output_path, "r") as zf:
            raw = yaml.safe_load(zf.read(MANIFEST_FILENAME).decode("utf-8"))
            assert "_package" in raw
            pkg = raw["_package"]
            assert pkg["manifest_hash"] == result.manifest_hash
            assert pkg["files_hash"] == result.files_hash
            assert pkg["total_files"] == result.file_count
            assert pkg["package_size_bytes"] > 0


# ── unpack ─────────────────────────────────────────────────────────────────


class TestUnpack:
    def test_unpack_extracts_all_files(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project)
        assert result.success and result.output_path is not None

        dest = tmp_path / "unpacked"
        unpack(result.output_path, dest)

        assert dest.exists()
        assert (dest / MANIFEST_FILENAME).exists()
        assert (dest / CHECKSUMS_FILENAME).exists()
        assert (dest / "src" / "agent.py").exists()
        assert (dest / "requirements.txt").exists()

    def test_unpack_corrupt_file_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.agent"
        bad_file.write_bytes(b"not-an-archive")

        with pytest.raises(PackageCorruptError):
            unpack(bad_file, tmp_path / "out")

    def test_unpack_tampered_package_raises(self, tmp_path: Path) -> None:
        """A package whose files have been tampered with should fail unpack."""
        project = _make_project(tmp_path)
        result = pack(project)
        assert result.success and result.output_path is not None

        # Tamper: modify a file inside the archive
        tampered = tmp_path / "tampered.agent"
        with zipfile.ZipFile(result.output_path, "r") as zf_in:
            with zipfile.ZipFile(tampered, "w") as zf_out:
                for item in zf_in.infolist():
                    data = zf_in.read(item.filename)
                    if item.filename == "src/agent.py":
                        data = b"# TAMPERED CONTENT\n"
                    zf_out.writestr(item, data)

        with pytest.raises(PackageCorruptError):
            unpack(tampered, tmp_path / "out2")


# ── inspect ────────────────────────────────────────────────────────────────


class TestInspect:
    def test_inspect_returns_correct_fields(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        result = pack(project)
        assert result.success and result.output_path is not None

        info = inspect(result.output_path)

        assert info["manifest"] is not None
        assert info["manifest"].name == "my-agent"
        assert info["manifest"].version == "0.1.0"
        assert info["is_valid"] is True
        assert info["size_bytes"] > 0
        assert isinstance(info["files"], list)
        assert MANIFEST_FILENAME in info["files"]

    def test_inspect_invalid_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.agent"
        bad.write_bytes(b"not an archive")

        info = inspect(bad)
        assert info["manifest"] is None
        assert len(info["errors"]) > 0

    def test_inspect_fraud_detection(self, tmp_path: Path) -> None:
        project = _copy_fraud_detection(tmp_path)
        result = pack(project)
        assert result.success and result.output_path is not None

        info = inspect(result.output_path)
        assert info["manifest"].name == "fraud-detection"
        assert info["manifest"].version == "0.1.0"
        assert info["is_valid"] is True
        # Should have tool declarations
        assert len(info["manifest"].capabilities.tools) == 3


# ── PackResult ─────────────────────────────────────────────────────────────


class TestPackResult:
    def test_default_values(self) -> None:
        pr = PackResult(success=False)
        assert pr.success is False
        assert pr.output_path is None
        assert pr.manifest_hash == ""
        assert pr.files_hash == ""
        assert pr.errors == []
        assert pr.warnings == []
        assert pr.file_count == 0
        assert pr.size_bytes == 0
