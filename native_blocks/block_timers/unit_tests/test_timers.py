"""
test_timers.py — validate_timer_definitions (pure) and Wrapper_Timer_Manager.get_timer
(read-only lookup against a saved/restored RTC snapshot — never touches the live timer set,
per Unit_Testing_Framework.md §9's "never call enable_and_poll_for_timers()/repoll() from a
test" rule).
"""

import unittest

from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..common_declarations import Block_RTC_Members
from ..data_structures import Timer_Definition
from ..feature_timer_manager import Wrapper_Timer_Manager
from ..helpers import validate_timer_definitions


def _noop(_timer_instance):
    pass


class Test_Timer_Definition_Validation(unittest.TestCase):
    def test_duplicate_non_blank_uid_is_rejected(self):
        defs = [Timer_Definition("DUP", 1.0, _noop), Timer_Definition("DUP", 2.0, _noop)]
        with self.assertRaises(ValueError):
            validate_timer_definitions(defs)

    def test_blank_uids_may_repeat(self):
        # Auto-assignment happens later in _rebuild_all_timers, not here — validation only
        # rejects DUPLICATE NON-blank uids, so several blank ones must pass.
        defs = [Timer_Definition("", 1.0, _noop), Timer_Definition("", 1.0, _noop)]
        validate_timer_definitions(defs)  # must not raise

    def test_non_positive_frequency_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_timer_definitions([Timer_Definition("T", 0.0, _noop)])
        with self.assertRaises(ValueError):
            validate_timer_definitions([Timer_Definition("T", -1.0, _noop)])

    def test_non_callable_callback_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_timer_definitions([Timer_Definition("T", 1.0, callback="not_callable")])

    def test_empty_list_is_valid(self):
        validate_timer_definitions([])  # must not raise


class Test_Timer_Manager_Lookup(unittest.TestCase):
    def setUp(self):
        self._saved = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS, should_copy=True)

    def tearDown(self):
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.TIMERS, self._saved)

    def test_get_timer_returns_none_for_unknown_uid(self):
        self.assertIsNone(Wrapper_Timer_Manager.get_timer("DGB_TEST_DOES_NOT_EXIST"))


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Timer_Definition_Validation, Test_Timer_Manager_Lookup):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
