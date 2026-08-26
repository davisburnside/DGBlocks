
import inspect
import io
import time
import unittest
from typing import Optional

# Addon-level imports
from .....addon_helpers.generic_tools import get_exception_last_n_lines

# Inter-block (within block_core) imports
from ..hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from ...core_helpers.constants import Core_Block_Hook_Sources
from .data_structures import (
    DEFAULT_SUITE_GROUP_LABEL,
    RTC_Unit_Test_Block_Row_Instance,
    RTC_Unit_Test_Group_Row_Instance,
    Unit_Test_Case_Info,
    Unit_Test_Status,
)

# ==============================================================================================================================
# UNITTEST INTROSPECTION

def _flatten_suite(suite: unittest.TestSuite) -> list:
    """Recursively walk a TestSuite (which may nest other suites) into individual TestCase instances."""
    cases = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            cases.extend(_flatten_suite(item))
        else:
            cases.append(item)
    return cases


class _Timed_Test_Result(unittest.TextTestResult):
    """Records wall-clock duration per individual test, keyed by test.id()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_timings: dict = {}
        self._current_start: Optional[float] = None

    def startTest(self, test):
        self._current_start = time.time()
        super().startTest(test)

    def stopTest(self, test):
        if self._current_start is not None:
            self.test_timings[test.id()] = time.time() - self._current_start
        super().stopTest(test)

# ==============================================================================================================================
# COLLECTION — discover tests, execute nothing

def _resolve_suite_group(declaration) -> str:
    return declaration.suite_group if declaration.suite_group else DEFAULT_SUITE_GROUP_LABEL


def collect_declarations_and_catalog(logger) -> tuple:
    """
    Fires hook_get_unit_test_declarations, builds every returned suite, and flattens the
    result into the three shapes this feature keeps in RTC: block rows, group rows, and the
    flat test-case catalog. Executes no test — building a suite (importing the test module,
    instantiating TestCases) is the only thing that can raise here, and a broken suite
    degrades to that one block's collection_error rather than breaking discovery for every
    other block (mirrors the isolation Wrapper_Hooks.run_hooked_funcs already gives per-block).

    Returns (block_rows, group_rows, catalog) — none of these carry over any prior run
    history; the caller (Wrapper_Unit_Testing.collect_all) is responsible for merging that in.
    """
    declarations_by_block = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name = Core_Block_Hook_Sources.hook_get_unit_test_declarations,
        should_halt_on_exception = False,
    ) or {}

    block_rows = []
    group_rows = []
    catalog = []

    for block_id, declarations in declarations_by_block.items():
        collection_error = None
        seen_groups = []

        for declaration in (declarations or []):
            suite_group = _resolve_suite_group(declaration)
            if suite_group not in seen_groups:
                seen_groups.append(suite_group)
            try:
                suite = declaration.build_suite()
                for test in _flatten_suite(suite):
                    test_method = getattr(test, test._testMethodName, None)
                    catalog.append(Unit_Test_Case_Info(
                        test_id         = test.id(),
                        short_label     = test.id().rsplit(".", 1)[-1],
                        block_id        = block_id,
                        suite_id        = declaration.suite_id,
                        suite_label     = declaration.label or declaration.suite_id,
                        suite_group     = suite_group,
                        cold_start_only = declaration.cold_start_only,
                        docstring       = inspect.getdoc(test_method) if test_method else None,
                    ))
            except Exception as e:
                logger.error(f"Suite '{declaration.suite_id}' (block '{block_id}') raised during collection", exc_info=True)
                collection_error = get_exception_last_n_lines(2, e)

        block_rows.append(RTC_Unit_Test_Block_Row_Instance(
            block_id = block_id,
            label = block_id,
            collection_error = collection_error,
        ))
        for suite_group in seen_groups:
            group_rows.append(RTC_Unit_Test_Group_Row_Instance(block_id = block_id, suite_group = suite_group))

    return block_rows, group_rows, catalog

# ==============================================================================================================================
# EXECUTION

def run_test_ids(test_ids: list, verbosity: int = 2):
    """
    Runs exactly the given (already-collected) test ids in one batch.
    Returns (unittest.TestResult, captured_text_output) — callers apply the result to
    whichever catalog/row entries are in scope for their own level; this function touches no
    RTC state itself.
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(test_id) for test_id in test_ids)
    stream = io.StringIO()
    runner = unittest.TextTestRunner(resultclass = _Timed_Test_Result, verbosity = verbosity, stream = stream)
    result = runner.run(suite)
    return result, stream.getvalue()


def apply_result_to_catalog(catalog_by_id: dict, ran_test_ids: list, result, run_at: float) -> None:
    """Mutates the matching Unit_Test_Case_Info entries in place (catalog_by_id holds live RTC objects)."""
    failed_ids  = {test.id() for test, _ in result.failures}
    errored_ids = {test.id() for test, _ in result.errors}
    skipped     = {test.id(): reason for test, reason in result.skipped}
    trace_by_id = {test.id(): trace for test, trace in (result.failures + result.errors)}

    for test_id in ran_test_ids:
        case = catalog_by_id.get(test_id)
        if case is None:
            continue
        if test_id in failed_ids:
            case.status = Unit_Test_Status.FAILED
            case.error_text = trace_by_id[test_id].strip().splitlines()[-1]
        elif test_id in errored_ids:
            case.status = Unit_Test_Status.ERROR
            case.error_text = trace_by_id[test_id].strip().splitlines()[-1]
        elif test_id in skipped:
            case.status = Unit_Test_Status.SKIPPED
            case.error_text = skipped[test_id]
        else:
            case.status = Unit_Test_Status.PASSED
            case.error_text = None
        case.duration_seconds = result.test_timings.get(test_id, 0.0)
        case.last_run_at = run_at
