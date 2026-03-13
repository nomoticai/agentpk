"""Tests for the CLI layer (agentpk.cli)."""

from pathlib import Path

from click.testing import CliRunner

from agentpk.cli import cli

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


class TestValidateNoArgument:
    """Improvement 2: agent validate with no argument gives clean error."""

    def test_exit_code_is_1(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate"])
        assert result.exit_code == 1

    def test_error_message(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate"])
        assert "no target specified" in result.output

    def test_shows_usage_hints(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate"])
        assert "agent validate" in result.output
        assert ".agent" in result.output


class TestValidateVerboseValid:
    """Improvement 1: --verbose shows each validation stage on a valid directory."""

    def test_stages_appear_in_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "valid" / "fraud-detection"), "--verbose",
        ])
        assert result.exit_code == 0
        assert "Pre-flight" in result.output
        assert "Identity" in result.output
        assert "File presence" in result.output
        assert "Consistency" in result.output
        assert "Checksums" in result.output
        assert "Package integrity" in result.output

    def test_directory_skips_stages_5_6(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "valid" / "fraud-detection"), "--verbose",
        ])
        assert result.exit_code == 0
        # Stages 5-6 should show SKIP with reason
        assert "SKIP" in result.output
        assert "directory, not package" in result.output

    def test_all_stages_pass(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "valid" / "fraud-detection"), "--verbose",
        ])
        assert result.exit_code == 0
        assert "Validation passed" in result.output

    def test_non_verbose_does_not_show_stages(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "valid" / "fraud-detection"),
        ])
        assert result.exit_code == 0
        assert "Pre-flight" not in result.output
        assert "Validation passed" in result.output


class TestValidateVerboseInvalid:
    """Improvement 1: --verbose shows FAIL and SKIP stages on an invalid directory."""

    def test_stage2_fails_on_invalid_name(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "invalid" / "04-invalid-name"), "--verbose",
        ])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "Validation failed" in result.output

    def test_stage1_fail_skips_later_stages(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "validate", str(EXAMPLES_DIR / "invalid" / "01-missing-manifest"), "--verbose",
        ])
        assert result.exit_code == 1
        # Stage 1 fails, stages 2-4 should be SKIP
        assert "FAIL" in result.output
        assert "SKIP" in result.output


class TestValidateHelp:
    """Improvement 3: --help shows descriptive usage text."""

    def test_help_shows_examples(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "agent validate" in result.output
        assert ".agent" in result.output

    def test_help_mentions_6_stage_pipeline(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert "6-stage" in result.output

    def test_help_mentions_verbose_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert "--verbose" in result.output


class TestValidateNonExistentPath:
    """agent validate with a non-existent path gives a clean error."""

    def test_exit_code_is_1(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "nonexistent-path-12345"])
        assert result.exit_code == 1

    def test_error_message(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "nonexistent-path-12345"])
        assert "does not exist" in result.output
