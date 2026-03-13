"""Built-in self-test suite for agentpk.

Generates minimal agent fixtures in a temporary directory, runs the
validation pipeline against each one, and reports pass/fail results.
Used by the ``agent test`` CLI command.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from agentpk.validator import validate_directory

# ---------------------------------------------------------------------------
# Test case model
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    """A single self-test case."""

    name: str
    description: str
    expect_valid: bool
    setup: Callable[[Path], None]
    error_fragment: str | None = None  # substring expected in error messages


@dataclass
class TestResult:
    """Result of running a single test case."""

    name: str
    description: str
    passed: bool
    detail: str = ""


@dataclass
class TestSuiteResult:
    """Aggregate result for the full self-test suite."""

    results: list[TestResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


# ---------------------------------------------------------------------------
# Fixture writers — each populates a directory with an agent project
# ---------------------------------------------------------------------------

_MINIMAL_MANIFEST = """\
spec_version: "1.0"
name: "{name}"
version: "1.0.0"
description: "{description}"
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
execution:
  type: {exec_type}
"""

_SCHEDULED_MANIFEST = """\
spec_version: "1.0"
name: "{name}"
version: "1.0.0"
description: "{description}"
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
execution:
  type: scheduled
  schedule: "0 */6 * * *"
"""

_AGENT_PY = '# placeholder agent\ndef main(): pass\n'
_REQUIREMENTS_TXT = ''


def _write(d: Path, name: str, content: str) -> None:
    (d / name).write_text(content, encoding="utf-8")


# ── valid fixtures ──────────────────────────────────────────────────────────

def _setup_valid_minimal(d: Path) -> None:
    _write(d, "manifest.yaml", _MINIMAL_MANIFEST.format(
        name="test-minimal", description="Minimal valid agent", exec_type="on-demand"))
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_valid_scheduled(d: Path) -> None:
    _write(d, "manifest.yaml", _SCHEDULED_MANIFEST.format(
        name="test-scheduled", description="Scheduled agent with cron"))
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_valid_triggered(d: Path) -> None:
    manifest = """\
spec_version: "1.0"
name: "test-triggered"
version: "1.0.0"
description: Triggered agent with event list.
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
execution:
  type: triggered
  triggers:
    - event: new_order
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_valid_nodejs(d: Path) -> None:
    manifest = """\
spec_version: "1.0"
name: "test-nodejs"
version: "1.0.0"
description: Node.js agent.
runtime:
  language: nodejs
  language_version: "20"
  entry_point: agent.js
  dependencies: package.json
execution:
  type: on-demand
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.js", "// placeholder\nmodule.exports.main = () => {};\n")
    _write(d, "package.json", '{"name": "test-nodejs", "version": "1.0.0"}\n')


# ── invalid fixtures ───────────────────────────────────────────────────────

def _setup_missing_manifest(d: Path) -> None:
    _write(d, "agent.py", _AGENT_PY)


def _setup_malformed_yaml(d: Path) -> None:
    _write(d, "manifest.yaml", "spec_version: \"1.0\"\nname \"bad yaml\n  broken:\n")
    _write(d, "agent.py", _AGENT_PY)


def _setup_missing_spec_version(d: Path) -> None:
    manifest = """\
name: "no-spec-version"
version: "1.0.0"
description: Missing spec_version.
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
execution:
  type: on-demand
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.py", _AGENT_PY)


def _setup_invalid_name(d: Path) -> None:
    _write(d, "manifest.yaml", _MINIMAL_MANIFEST.format(
        name="My Bad Name", description="Invalid name format", exec_type="on-demand"))
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_missing_entry_point(d: Path) -> None:
    _write(d, "manifest.yaml", _MINIMAL_MANIFEST.format(
        name="no-entry", description="Entry point missing", exec_type="on-demand"))
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)
    # deliberately no agent.py


def _setup_missing_deps(d: Path) -> None:
    _write(d, "manifest.yaml", _MINIMAL_MANIFEST.format(
        name="no-deps", description="Deps file missing", exec_type="on-demand"))
    _write(d, "agent.py", _AGENT_PY)
    # deliberately no requirements.txt


def _setup_invalid_exec_type(d: Path) -> None:
    _write(d, "manifest.yaml", _MINIMAL_MANIFEST.format(
        name="bad-exec", description="Invalid exec type", exec_type="always-running"))
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_scheduled_no_cron(d: Path) -> None:
    manifest = """\
spec_version: "1.0"
name: "no-cron"
version: "1.0.0"
description: Scheduled without schedule field.
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
execution:
  type: scheduled
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_invalid_scope(d: Path) -> None:
    manifest = """\
spec_version: "1.0"
name: "bad-scope"
version: "1.0.0"
description: Tool has invalid scope.
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
capabilities:
  tools:
    - id: bad-tool
      description: Tool with invalid scope
      scope: superuser
      required: true
execution:
  type: on-demand
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


def _setup_env_overlap(d: Path) -> None:
    manifest = """\
spec_version: "1.0"
name: "env-overlap"
version: "1.0.0"
description: Env var in both allowed and denied.
runtime:
  language: python
  language_version: "3.11"
  entry_point: agent.py
  dependencies: requirements.txt
permissions:
  environments:
    allowed:
      - DATABASE_URL
      - STAGING_HOST
    denied:
      - SECRET_TOKEN
      - STAGING_HOST
execution:
  type: on-demand
"""
    _write(d, "manifest.yaml", manifest)
    _write(d, "agent.py", _AGENT_PY)
    _write(d, "requirements.txt", _REQUIREMENTS_TXT)


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TEST_CASES: list[TestCase] = [
    # ── valid ──
    TestCase(
        name="valid-minimal",
        description="Minimal on-demand Python agent",
        expect_valid=True,
        setup=_setup_valid_minimal,
    ),
    TestCase(
        name="valid-scheduled",
        description="Scheduled agent with cron expression",
        expect_valid=True,
        setup=_setup_valid_scheduled,
    ),
    TestCase(
        name="valid-triggered",
        description="Triggered agent with event list",
        expect_valid=True,
        setup=_setup_valid_triggered,
    ),
    TestCase(
        name="valid-nodejs",
        description="Node.js on-demand agent",
        expect_valid=True,
        setup=_setup_valid_nodejs,
    ),
    # ── invalid ──
    TestCase(
        name="missing-manifest",
        description="No manifest.yaml present",
        expect_valid=False,
        setup=_setup_missing_manifest,
        error_fragment="manifest.yaml not found",
    ),
    TestCase(
        name="malformed-yaml",
        description="manifest.yaml contains invalid YAML",
        expect_valid=False,
        setup=_setup_malformed_yaml,
        error_fragment="Invalid YAML",
    ),
    TestCase(
        name="missing-spec-version",
        description="spec_version field is absent",
        expect_valid=False,
        setup=_setup_missing_spec_version,
        error_fragment="spec_version",
    ),
    TestCase(
        name="invalid-name",
        description="Name contains uppercase and spaces",
        expect_valid=False,
        setup=_setup_invalid_name,
        error_fragment="name must",
    ),
    TestCase(
        name="missing-entry-point",
        description="Entry-point file does not exist",
        expect_valid=False,
        setup=_setup_missing_entry_point,
        error_fragment="Entry-point file not found",
    ),
    TestCase(
        name="missing-deps",
        description="Dependencies file does not exist",
        expect_valid=False,
        setup=_setup_missing_deps,
        error_fragment="Dependencies file not found",
    ),
    TestCase(
        name="invalid-exec-type",
        description="Unrecognized execution type",
        expect_valid=False,
        setup=_setup_invalid_exec_type,
        error_fragment="execution.type must be one of",
    ),
    TestCase(
        name="scheduled-no-cron",
        description="Scheduled type without schedule field",
        expect_valid=False,
        setup=_setup_scheduled_no_cron,
        error_fragment="execution.schedule is required",
    ),
    TestCase(
        name="invalid-scope",
        description="Tool has unrecognized scope value",
        expect_valid=False,
        setup=_setup_invalid_scope,
        error_fragment="scope must be one of",
    ),
    TestCase(
        name="env-overlap",
        description="Environment variable in allowed and denied",
        expect_valid=False,
        setup=_setup_env_overlap,
        error_fragment="overlap",
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_tests(*, verbose: bool = False) -> TestSuiteResult:
    """Run all built-in test cases and return aggregated results.

    Each test case is set up in a fresh temporary directory, validated,
    and the directory is cleaned up immediately after.
    """
    suite = TestSuiteResult()

    for tc in TEST_CASES:
        tmp = tempfile.mkdtemp(prefix=f"agentpk-test-{tc.name}-")
        tmp_path = Path(tmp)
        try:
            # Set up the fixture
            tc.setup(tmp_path)

            # Run validation
            vr = validate_directory(tmp_path)

            # Evaluate
            if tc.expect_valid:
                if vr.is_valid:
                    suite.results.append(TestResult(
                        name=tc.name,
                        description=tc.description,
                        passed=True,
                        detail="Validated successfully",
                    ))
                else:
                    errors = "; ".join(e.message for e in vr.errors)
                    suite.results.append(TestResult(
                        name=tc.name,
                        description=tc.description,
                        passed=False,
                        detail=f"Expected valid but got errors: {errors}",
                    ))
            else:
                if not vr.is_valid:
                    # Check error fragment if specified
                    all_msgs = " ".join(e.message for e in vr.errors)
                    if tc.error_fragment and tc.error_fragment not in all_msgs:
                        suite.results.append(TestResult(
                            name=tc.name,
                            description=tc.description,
                            passed=False,
                            detail=(
                                f"Expected error containing '{tc.error_fragment}' "
                                f"but got: {all_msgs}"
                            ),
                        ))
                    else:
                        suite.results.append(TestResult(
                            name=tc.name,
                            description=tc.description,
                            passed=True,
                            detail=f"Correctly rejected: {vr.errors[0].message}",
                        ))
                else:
                    suite.results.append(TestResult(
                        name=tc.name,
                        description=tc.description,
                        passed=False,
                        detail="Expected validation failure but passed",
                    ))
        except Exception as exc:
            suite.results.append(TestResult(
                name=tc.name,
                description=tc.description,
                passed=False,
                detail=f"Unexpected exception: {exc}",
            ))
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    return suite
