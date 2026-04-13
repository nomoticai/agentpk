"""Tests for AIR v1.1 JSON Schemas and 8-component expansion."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema" / "air"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# All 8 component names + the bundle manifest
ALL_SCHEMA_FILES = [
    "air.schema.json",
    "audit.schema.json",
    "fingerprint.schema.json",
    "trust.schema.json",
    "org_context.schema.json",
    "compliance_state.schema.json",
    "domain_model.schema.json",
    "interaction_patterns.schema.json",
    "knowledge_state.schema.json",
]

# Mapping: schema file -> (example dir, example file)
# Only components that exist as files in the examples
FRAUD_DIR = EXAMPLES_DIR / "valid" / "fraud-detector-with-memory" / "intelligence"
HEALTHCARE_DIR = EXAMPLES_DIR / "valid" / "healthcare-agent-strict-redaction" / "intelligence"

EXAMPLE_VALIDATIONS = [
    ("air.schema.json", FRAUD_DIR / "air.json"),
    ("fingerprint.schema.json", FRAUD_DIR / "fingerprint.json"),
    ("trust.schema.json", FRAUD_DIR / "trust.json"),
    ("org_context.schema.json", FRAUD_DIR / "org_context.json"),
    ("knowledge_state.schema.json", FRAUD_DIR / "knowledge_state.json"),
    ("compliance_state.schema.json", FRAUD_DIR / "compliance_state.json"),
    ("domain_model.schema.json", FRAUD_DIR / "domain_model.json"),
    ("interaction_patterns.schema.json", FRAUD_DIR / "interaction_patterns.json"),
    ("air.schema.json", HEALTHCARE_DIR / "air.json"),
    ("fingerprint.schema.json", HEALTHCARE_DIR / "fingerprint.json"),
    ("org_context.schema.json", HEALTHCARE_DIR / "org_context.json"),
    ("compliance_state.schema.json", HEALTHCARE_DIR / "compliance_state.json"),
]


class TestSchemaFilesValid:
    """Each schema file in schema/air/ must be valid JSON."""

    @pytest.mark.parametrize("filename", ALL_SCHEMA_FILES)
    def test_schema_is_valid_json(self, filename: str) -> None:
        path = SCHEMA_DIR / filename
        assert path.exists(), f"Schema file missing: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "$schema" in data
        assert "type" in data or "properties" in data

    def test_all_nine_schemas_present(self) -> None:
        """9 schema files: 1 manifest + 8 components."""
        for filename in ALL_SCHEMA_FILES:
            assert (SCHEMA_DIR / filename).exists(), f"Missing: {filename}"


class TestExampleValidation:
    """Validate each example component file against its schema."""

    @pytest.mark.parametrize(
        "schema_file,example_file",
        EXAMPLE_VALIDATIONS,
        ids=[f"{s.split('.')[0]}:{e.parent.parent.name}" for s, e in EXAMPLE_VALIDATIONS],
    )
    def test_example_validates_against_schema(
        self, schema_file: str, example_file: Path
    ) -> None:
        schema = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
        instance = json.loads(example_file.read_text(encoding="utf-8"))
        jsonschema.validate(instance=instance, schema=schema)


class TestComponentSet:
    """The _VALID_AIR_COMPONENTS set in cli.py must contain all 8 names."""

    def test_all_eight_components_in_cli(self) -> None:
        from agentpk.cli import cli

        runner = CliRunner()
        # Pass an unknown component name to trigger the error message
        # which lists all valid names
        result = runner.invoke(
            cli,
            ["pack", ".", "--memory", "--memory-components", "nonexistent"],
        )
        assert result.exit_code != 0
        output = result.output
        expected = {
            "audit",
            "fingerprint",
            "trust",
            "org_context",
            "compliance_state",
            "domain_model",
            "interaction_patterns",
            "knowledge_state",
        }
        for comp in expected:
            assert comp in output, f"Component '{comp}' not listed in error output"

    def test_unknown_component_rejected(self) -> None:
        from agentpk.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["pack", ".", "--memory", "--memory-components", "unknown_thing"],
        )
        assert result.exit_code != 0
        assert "unknown AIR component" in result.output.lower() or "unknown" in result.output.lower()


class TestValidatorComponentMap:
    """Validator must recognize all 8 component file mappings."""

    def test_fraud_detector_validates_with_8_components(self) -> None:
        from agentpk.validator import validate_directory

        fraud_dir = EXAMPLES_DIR / "valid" / "fraud-detector-with-memory"
        result = validate_directory(fraud_dir)
        assert result.is_valid, f"Validation failed: {[e.message for e in result.errors]}"

    def test_healthcare_validates_with_compliance_state(self) -> None:
        from agentpk.validator import validate_directory

        healthcare_dir = EXAMPLES_DIR / "valid" / "healthcare-agent-strict-redaction"
        result = validate_directory(healthcare_dir)
        assert result.is_valid, f"Validation failed: {[e.message for e in result.errors]}"
