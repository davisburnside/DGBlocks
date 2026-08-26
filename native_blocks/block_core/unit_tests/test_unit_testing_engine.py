"""
test_unit_testing_engine.py — Wrapper_Unit_Testing testing itself.

Scoped deliberately narrow: collect_all()/run_all() are this block's own "repoll()"-equivalent
master rebuild — calling them from inside a test would pull in and execute every OTHER block's
currently-registered tests as a side effect, exactly the anti-pattern §9 already warns against
for every other block's enable_*/repoll(). So this suite tests only the pure, private-but-plain
functions underneath that engine: suite_group defaulting and unittest-result-to-catalog mapping.
"""

import time
import unittest

from ..core_features.unit_testing.data_structures import (
    DEFAULT_SUITE_GROUP_LABEL,
    Unit_Test_Case_Info,
    Unit_Test_Status,
)
from ..core_features.unit_testing.helpers import _resolve_suite_group, apply_result_to_catalog


class _Fake_Declaration:
    def __init__(self, suite_group=None):
        self.suite_group = suite_group


class Test_Suite_Group_Defaulting(unittest.TestCase):
    def test_none_resolves_to_default_label(self):
        self.assertEqual(_resolve_suite_group(_Fake_Declaration(None)), DEFAULT_SUITE_GROUP_LABEL)

    def test_blank_string_resolves_to_default_label(self):
        self.assertEqual(_resolve_suite_group(_Fake_Declaration("")), DEFAULT_SUITE_GROUP_LABEL)

    def test_custom_group_is_preserved(self):
        self.assertEqual(_resolve_suite_group(_Fake_Declaration("Validation")), "Validation")


class _Fake_Test:
    """Stand-in for a unittest.TestCase instance — only .id() is ever used by apply_result_to_catalog."""
    def __init__(self, test_id):
        self._test_id = test_id

    def id(self):
        return self._test_id


class _Fake_Result:
    def __init__(self, failures=(), errors=(), skipped=(), test_timings=None):
        self.failures = list(failures)
        self.errors = list(errors)
        self.skipped = list(skipped)
        self.test_timings = test_timings or {}


def _make_case(test_id: str) -> Unit_Test_Case_Info:
    return Unit_Test_Case_Info(
        test_id=test_id, short_label=test_id, block_id="block-test", suite_id="suite",
        suite_label="suite",
    )


class Test_Apply_Result_To_Catalog(unittest.TestCase):
    def test_test_not_in_any_result_list_is_marked_passed(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(catalog, ["a"], _Fake_Result(), run_at=123.0)
        self.assertEqual(catalog["a"].status, Unit_Test_Status.PASSED)
        self.assertIsNone(catalog["a"].error_text)
        self.assertEqual(catalog["a"].last_run_at, 123.0)

    def test_failure_sets_failed_status_and_last_trace_line(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(
            catalog, ["a"],
            _Fake_Result(failures=[(_Fake_Test("a"), "Traceback...\nAssertionError: boom")]),
            run_at=1.0,
        )
        self.assertEqual(catalog["a"].status, Unit_Test_Status.FAILED)
        self.assertEqual(catalog["a"].error_text, "AssertionError: boom")

    def test_error_sets_error_status(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(
            catalog, ["a"],
            _Fake_Result(errors=[(_Fake_Test("a"), "Traceback...\nValueError: bad")]),
            run_at=1.0,
        )
        self.assertEqual(catalog["a"].status, Unit_Test_Status.ERROR)

    def test_skip_sets_skipped_status_with_reason(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(
            catalog, ["a"],
            _Fake_Result(skipped=[(_Fake_Test("a"), "no GPU context")]),
            run_at=1.0,
        )
        self.assertEqual(catalog["a"].status, Unit_Test_Status.SKIPPED)
        self.assertEqual(catalog["a"].error_text, "no GPU context")

    def test_duration_is_read_from_test_timings(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(catalog, ["a"], _Fake_Result(test_timings={"a": 0.42}), run_at=1.0)
        self.assertEqual(catalog["a"].duration_seconds, 0.42)

    def test_unknown_test_id_in_ran_list_is_ignored_not_raised(self):
        catalog = {"a": _make_case("a")}
        apply_result_to_catalog(catalog, ["a", "does-not-exist"], _Fake_Result(), run_at=1.0)
        self.assertEqual(catalog["a"].status, Unit_Test_Status.PASSED)


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Suite_Group_Defaulting, Test_Apply_Result_To_Catalog):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
