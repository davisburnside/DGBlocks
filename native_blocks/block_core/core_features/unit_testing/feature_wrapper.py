
import time
from typing import Optional
import bpy

# Addon-level imports
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Shared_UIList_Draw, Enum_Sync_Events

# Inter-block (within block_core) imports
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger
from ..control_plane.feature_wrapper import Wrapper_Control_Plane

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from .data_structures import Unit_Test_Run_Report
from .helpers import apply_result_to_catalog, collect_declarations_and_catalog, run_test_ids

# Aliases
cache_key_block_rows  = Core_Runtime_Cache_Members.UNIT_TEST_BLOCK_ROWS
cache_key_group_rows  = Core_Runtime_Cache_Members.UNIT_TEST_GROUP_ROWS
cache_key_catalog     = Core_Runtime_Cache_Members.UNIT_TEST_CASE_CATALOG
cache_key_last_report = Core_Runtime_Cache_Members.LAST_UNIT_TEST_REPORT


class Wrapper_Unit_Testing(Abstract_Feature_Wrapper, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        cls.collect_all()
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        pass

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation

    @classmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        return shared_uilist_instance.scene_colprop_path

    # ----------------------------------------------------------
    # Public query API — read-only, never mutates RTC

    @classmethod
    def get_all_block_rows(cls) -> list:
        return Wrapper_Runtime_Cache.get_cache(cache_key_block_rows)

    @classmethod
    def get_block_row(cls, block_id: str):
        _, row, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_block_rows, "block_id", block_id)
        return row

    @classmethod
    def get_groups_for_block(cls, block_id: str) -> list:
        """Distinct suite_group labels declared by this block, in first-seen order."""
        seen = []
        for case in cls.get_tests_for_block(block_id):
            if case.suite_group not in seen:
                seen.append(case.suite_group)
        return seen

    @classmethod
    def get_group_row(cls, block_id: str, suite_group: str):
        for row in Wrapper_Runtime_Cache.get_cache(cache_key_group_rows):
            if row.block_id == block_id and row.suite_group == suite_group:
                return row
        return None

    @classmethod
    def get_tests_for_block(cls, block_id: str) -> list:
        return [c for c in Wrapper_Runtime_Cache.get_cache(cache_key_catalog) if c.block_id == block_id]

    @classmethod
    def get_tests_for_group(cls, block_id: str, suite_group: str) -> list:
        return [c for c in cls.get_tests_for_block(block_id) if c.suite_group == suite_group]

    @classmethod
    def get_test(cls, test_id: str):
        for case in Wrapper_Runtime_Cache.get_cache(cache_key_catalog):
            if case.test_id == test_id:
                return case
        return None

    @classmethod
    def get_last_report(cls) -> Optional[Unit_Test_Run_Report]:
        return Wrapper_Runtime_Cache.get_cache(cache_key_last_report)

    # ----------------------------------------------------------
    # Public run API — operators call these directly; no operator re-implements this logic

    @classmethod
    def collect_all(cls) -> None:
        """
        (Re)discovers every block's declared tests without running any of them.
        Preserves prior run history for block_ids/groups/tests that still exist: is_enabled
        and both persisted last_run fields are seeded from the BL mirror (survives file
        save/reload); group/test status history is seeded from the current in-memory RTC
        (survives a mid-session Refresh, resets on Blender restart — it was never mirrored).
        """
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)

        core_props = bpy.context.scene.dgblocks_core_props
        bl_state_by_block_id = {
            row.block_id: (row.is_enabled, row.last_run_at, row.last_run_duration_seconds)
            for row in core_props.unit_test_block_rows
        }
        previous_group_rows = {(r.block_id, r.suite_group): r for r in Wrapper_Runtime_Cache.get_cache(cache_key_group_rows)}
        previous_catalog     = {c.test_id: c for c in Wrapper_Runtime_Cache.get_cache(cache_key_catalog)}

        block_rows, group_rows, catalog = collect_declarations_and_catalog(logger)

        for row in block_rows:
            is_enabled, last_run_at, last_run_duration = bl_state_by_block_id.get(row.block_id, (True, 0.0, 0.0))
            row.is_enabled = is_enabled
            row.last_run_at = last_run_at
            row.last_run_duration_seconds = last_run_duration

        for row in group_rows:
            prior = previous_group_rows.get((row.block_id, row.suite_group))
            if prior is not None:
                row.last_run_at = prior.last_run_at
                row.last_run_duration_seconds = prior.last_run_duration_seconds

        for case in catalog:
            prior = previous_catalog.get(case.test_id)
            if prior is not None:
                case.status = prior.status
                case.duration_seconds = prior.duration_seconds
                case.error_text = prior.error_text
                case.last_run_at = prior.last_run_at

        Wrapper_Runtime_Cache.set_cache(cache_key_block_rows, block_rows)
        Wrapper_Runtime_Cache.set_cache(cache_key_group_rows, group_rows)
        Wrapper_Runtime_Cache.set_cache(cache_key_catalog, catalog)
        cls._sync_block_rows_to_BL(logger)

    @classmethod
    def run_all(cls, verbosity: int = 2, include_cold_start_only: bool = False) -> Unit_Test_Run_Report:
        """
        Runs every enabled block's tests. The only level that updates the global report.

        include_cold_start_only: pass True only from a process that is itself a fresh,
        just-booted Blender (i.e. Developer/run_all_unit_tests.py) — see cold_start_only on
        Unit_Test_Suite_Declaration. The interactive "Run All Unit Tests" button always uses
        the default False, since a live session is never a fresh process.
        """
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)

        # Headless-safe: guarantee hook subscribers are wired even if the deferred post-bpy
        # timer hasn't ticked yet (bpy.app.timers is not guaranteed to fire before a
        # `--background --python script.py` process exits). No-op in the normal interactive
        # case where startup has already completed.
        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.ADDON_METADATA)
        if not ADDON_METADATA.POST_REG_INIT_HAS_RUN:
            Wrapper_Control_Plane.init_post_bpy()

        cls.collect_all()

        started_at = time.time()
        block_ids_run = []
        for row in cls.get_all_block_rows():
            if not row.is_enabled:
                continue
            cls._run_tests_for_block(row.block_id, verbosity, logger, include_cold_start_only)
            block_ids_run.append(row.block_id)

        report = Unit_Test_Run_Report(started_at = started_at, finished_at = time.time(), block_ids_run = block_ids_run)
        Wrapper_Runtime_Cache.set_cache(cache_key_last_report, report)
        cls._sync_block_rows_to_BL(logger)
        return report

    @classmethod
    def run_block_unit_tests(cls, block_id: str, verbosity: int = 2, include_cold_start_only: bool = False):
        """Runs every test belonging to one block, regardless of suite_group."""
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)
        row = cls._run_tests_for_block(block_id, verbosity, logger, include_cold_start_only)
        cls._sync_block_rows_to_BL(logger)
        return row

    @classmethod
    def run_group_unit_tests(cls, block_id: str, suite_group: str, verbosity: int = 2, include_cold_start_only: bool = False):
        """Runs only the tests in one (block_id, suite_group) subgroup."""
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)
        cases = cls.get_tests_for_group(block_id, suite_group)
        test_ids = cls._runnable_test_ids(cases, include_cold_start_only)
        run_at = time.time()
        cls._execute_and_apply(test_ids, verbosity, logger, run_at = run_at)

        group_row = cls.get_group_row(block_id, suite_group)
        if group_row is not None:
            group_row.last_run_at = run_at
            group_row.last_run_duration_seconds = time.time() - run_at
        return group_row

    @classmethod
    def run_one_test(cls, test_id: str, verbosity: int = 2, include_cold_start_only: bool = False):
        """
        Runs exactly one test. Does not bump any block/group last_run_at — narrower scope.
        No-ops (with a warning) if the test is cold_start_only and include_cold_start_only is
        False — the UI is expected to grey out this test's Run button in that case, so reaching
        this guard means a caller invoked it directly (e.g. from the Python console).
        """
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)
        case = cls.get_test(test_id)
        if case is not None and case.cold_start_only and not include_cold_start_only:
            logger.warning(f"run_one_test: '{test_id}' is cold_start_only — skipping (not a fresh process)")
            return case
        cls._execute_and_apply([test_id], verbosity, logger)
        return cls.get_test(test_id)

    # ----------------------------------------------------------
    # Internal

    @classmethod
    def _runnable_test_ids(cls, cases: list, include_cold_start_only: bool) -> list:
        return [c.test_id for c in cases if include_cold_start_only or not c.cold_start_only]

    @classmethod
    def _run_tests_for_block(cls, block_id: str, verbosity: int, logger, include_cold_start_only: bool = False):
        cases = cls.get_tests_for_block(block_id)
        test_ids = cls._runnable_test_ids(cases, include_cold_start_only)
        run_at = time.time()
        cls._execute_and_apply(test_ids, verbosity, logger, run_at = run_at)

        row = cls.get_block_row(block_id)
        if row is not None:
            row.last_run_at = run_at
            row.last_run_duration_seconds = time.time() - run_at
        return row

    @classmethod
    def _execute_and_apply(cls, test_ids: list, verbosity: int, logger, run_at: Optional[float] = None) -> float:
        run_at = run_at if run_at is not None else time.time()
        if not test_ids:
            return run_at
        try:
            result, output_text = run_test_ids(test_ids, verbosity)
            print(output_text)  # full unittest output stays visible in console/log
        except Exception:
            logger.error(f"Unable to run test id(s): {test_ids}", exc_info = True)
            return run_at

        catalog_by_id = {c.test_id: c for c in Wrapper_Runtime_Cache.get_cache(cache_key_catalog)}
        apply_result_to_catalog(catalog_by_id, test_ids, result, run_at)
        return run_at

    @classmethod
    def _sync_block_rows_to_BL(cls, logger) -> None:
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event = Enum_Sync_Events.PROPERTY_UPDATE,
            BL_is_truth_source = False,
            cache_key = cache_key_block_rows,
            logger = logger,
        )
