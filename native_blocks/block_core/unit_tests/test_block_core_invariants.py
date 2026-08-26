"""
test_block_core_invariants.py — block_core is mostly startup/lifecycle code, not runtime
logic (per Unit_Testing_Framework.md), so this suite asserts on already-live registry state
from the current session rather than exercising register/unregister transitions directly —
registering/unregistering block_core mid-session isn't something a test should ever do.
All of these are read-only, so idempotency is automatic.
"""

import unittest

from ..core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache, get_actual_rtc_key
from ..core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..core_helpers.constants import Core_Runtime_Cache_Members


class Test_Block_Registry_Invariants(unittest.TestCase):
    def test_all_registered_blocks_are_valid(self):
        """Every block currently registered this session must have completed registration cleanly."""
        blocks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)
        invalid = [b.block_id for b in blocks if not b.is_valid]
        self.assertEqual(invalid, [], f"Blocks failed registration: {invalid}")

    def test_block_core_itself_is_registered(self):
        """block_core is a hard dependency of every other block, so it must always be present."""
        blocks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)
        self.assertIn("block-core", [b.block_id for b in blocks])


class Test_Hook_Source_Registry_Invariants(unittest.TestCase):
    def test_hook_sources_have_no_negative_subscriber_counts(self):
        """A rebuilt hook-subscriber cache should never report a negative subscriber count for any hook."""
        # rebuild_hook_subs_cache() fully recomputes from scratch every call (see
        # hooks/feature_wrapper.py) and touches no other block's live state — a deliberate,
        # narrow exception to "don't call repoll() from inside a test".
        Wrapper_Hooks.rebuild_hook_subs_cache()
        sources = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES)
        self.assertTrue(all(s.subscriber_count >= 0 for s in sources))

    def test_unit_test_hook_source_is_registered(self):
        """hook_get_unit_test_declarations (this very framework's own hook) must be a known hook source."""
        sources = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES)
        self.assertIn("hook_get_unit_test_declarations", [s.hook_func_name for s in sources])


class Test_RTC_Key_Resolution(unittest.TestCase):
    def test_enum_and_string_resolve_identically(self):
        """An RTC key passed as an enum member or as its raw string name must resolve to the same key."""
        self.assertEqual(
            get_actual_rtc_key(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS),
            get_actual_rtc_key("REGISTRY_ALL_BLOCKS"),
        )


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Block_Registry_Invariants, Test_Hook_Source_Registry_Invariants, Test_RTC_Key_Resolution):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
