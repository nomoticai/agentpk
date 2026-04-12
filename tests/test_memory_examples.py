"""Integration tests for AIR memory example agents."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from agentpk.constants import MANIFEST_FILENAME
from agentpk.packer import pack
from agentpk.validator import validate_directory


_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


# ── helpers ──────────────────────────────────────────────────────────────────


def _read_packed_manifest(agent_path: Path) -> dict:
    with zipfile.ZipFile(agent_path, "r") as zf:
        return yaml.safe_load(zf.read(MANIFEST_FILENAME))


def _read_packed_file(agent_path: Path, inner_path: str) -> bytes:
    with zipfile.ZipFile(agent_path, "r") as zf:
        return zf.read(inner_path)


def _packed_file_exists(agent_path: Path, inner_path: str) -> bool:
    with zipfile.ZipFile(agent_path, "r") as zf:
        return inner_path in zf.namelist()


# ── valid example: fraud-detector-with-memory ────────────────────────────────


class TestFraudDetectorWithMemory:
    """Pack fraud-detector-with-memory with --memory and verify."""

    @pytest.fixture(autouse=True)
    def _pack(self, tmp_path: Path) -> None:
        source = _EXAMPLES_DIR / "valid" / "fraud-detector-with-memory"
        self.result = pack(source, output_path=tmp_path / "out.agent")

    def test_pack_succeeds(self) -> None:
        assert self.result.success

    def test_archive_contains_air_json(self) -> None:
        assert _packed_file_exists(self.result.output_path, "intelligence/air.json")

    def test_archive_contains_fingerprint(self) -> None:
        assert _packed_file_exists(self.result.output_path, "intelligence/fingerprint.json")

    def test_air_json_version(self) -> None:
        air = json.loads(_read_packed_file(self.result.output_path, "intelligence/air.json"))
        assert air["air_version"] == "1.0"

    def test_air_json_has_fingerprint_component(self) -> None:
        air = json.loads(_read_packed_file(self.result.output_path, "intelligence/air.json"))
        assert "fingerprint" in air["components"]


# ── valid example: healthcare-agent-strict-redaction ─────────────────────────


class TestHealthcareStrictRedaction:
    """Pack healthcare-agent-strict-redaction with --memory and verify."""

    @pytest.fixture(autouse=True)
    def _pack(self, tmp_path: Path) -> None:
        source = _EXAMPLES_DIR / "valid" / "healthcare-agent-strict-redaction"
        self.result = pack(source, output_path=tmp_path / "out.agent")

    def test_pack_succeeds(self) -> None:
        assert self.result.success

    def test_strict_redaction_profile(self) -> None:
        air = json.loads(_read_packed_file(self.result.output_path, "intelligence/air.json"))
        assert air["redaction_profile"] == "strict"

    def test_components_fingerprint_and_org_context(self) -> None:
        air = json.loads(_read_packed_file(self.result.output_path, "intelligence/air.json"))
        assert sorted(air["components"]) == ["fingerprint", "org_context"]

    def test_no_audit_file(self) -> None:
        assert not _packed_file_exists(self.result.output_path, "intelligence/audit.jsonl")


# ── invalid example: memory-hash-mismatch ────────────────────────────────────


class TestMemoryHashMismatch:
    """Validate memory-hash-mismatch and verify failure."""

    def test_validation_fails_with_hash_error(self) -> None:
        source = _EXAMPLES_DIR / "invalid" / "memory-hash-mismatch"
        vr = validate_directory(source)
        assert not vr.is_valid
        errors = " ".join(e.message for e in vr.errors)
        assert "hash" in errors.lower()
        assert "mismatch" in errors.lower() or "does not match" in errors.lower()


# ── invalid example: memory-missing-component ────────────────────────────────


class TestMemoryMissingComponent:
    """Validate memory-missing-component and verify failure."""

    def test_validation_fails_with_missing_component(self) -> None:
        source = _EXAMPLES_DIR / "invalid" / "memory-missing-component"
        vr = validate_directory(source)
        assert not vr.is_valid
        errors = " ".join(e.message for e in vr.errors)
        assert "trust" in errors.lower()
        assert "not present" in errors.lower() or "missing" in errors.lower()


# ── invalid example: memory-malformed-air-json ───────────────────────────────


class TestMemoryMalformedAirJson:
    """Validate memory-malformed-air-json and verify failure."""

    def test_validation_fails_with_required_field_errors(self) -> None:
        source = _EXAMPLES_DIR / "invalid" / "memory-malformed-air-json"
        vr = validate_directory(source)
        assert not vr.is_valid
        errors = " ".join(e.message for e in vr.errors)
        assert "air_version" in errors or "components" in errors
