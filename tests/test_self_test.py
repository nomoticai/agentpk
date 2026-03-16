"""Tests for the built-in self-test suite (agentpk.testing)."""

from agentpk.testing import TEST_CASES, run_tests


class TestSelfTestSuite:
    """Verify the self-test infrastructure itself."""

    def test_all_cases_pass(self) -> None:
        """The built-in suite should pass on a correctly installed agentpk."""
        result = run_tests()
        failures = [r for r in result.results if not r.passed]
        assert result.all_passed, (
            f"{result.failed} test(s) failed: "
            + "; ".join(f"{r.name}: {r.detail}" for r in failures)
        )

    def test_case_count(self) -> None:
        """Ensure we have the expected number of built-in test cases."""
        assert len(TEST_CASES) == 17

    def test_valid_cases_exist(self) -> None:
        """At least one valid test case should be registered."""
        valid = [tc for tc in TEST_CASES if tc.expect_valid]
        assert len(valid) == 7

    def test_invalid_cases_exist(self) -> None:
        """At least one invalid test case should be registered."""
        invalid = [tc for tc in TEST_CASES if not tc.expect_valid]
        assert len(invalid) == 10

    def test_all_invalid_have_error_fragment(self) -> None:
        """Every invalid test case should specify an expected error fragment."""
        for tc in TEST_CASES:
            if not tc.expect_valid:
                assert tc.error_fragment, f"{tc.name} missing error_fragment"

    def test_result_counts(self) -> None:
        """Verify the result counters are consistent."""
        result = run_tests()
        assert result.total == len(TEST_CASES)
        assert result.passed + result.failed == result.total

    def test_verbose_mode(self) -> None:
        """Verbose flag should not change outcomes."""
        result = run_tests(verbose=True)
        assert result.all_passed
