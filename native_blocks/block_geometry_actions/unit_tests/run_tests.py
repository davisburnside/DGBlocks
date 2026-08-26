"""
run_tests.py — single entry point for the block_geometry_actions test suite.

Interactive (Blender Text Editor / Python Console), addon already enabled:

    from DGBlocks.native_blocks.block_geometry_actions.unit_tests import run_tests
    run_tests.run()

Headless:

    blender --background --python <addon>/native_blocks/block_geometry_actions/unit_tests/run_tests.py

When run headless as __main__ the addon package is imported by name from the folder
three levels up, so no manual sys.path juggling is needed.

This suite also runs as part of the full addon-wide pass via block_core's
Wrapper_Unit_Testing (see hook_get_unit_test_declarations in this block's __init__.py) —
this file remains for standalone/manual use, its shape is unchanged by that wiring.
"""

import unittest


def _ensure_test_runtime() -> None:
    """Initialize RTC defaults when a headless workspace package is not installed as an addon."""
    from ....addon_helpers.data_tools import fast_deepcopy_with_fallback
    from ...block_core.core_features.loggers.feature_wrapper import Wrapper_Loggers
    from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
    from ..common_declarations import Block_RTC_Members

    if Wrapper_Runtime_Cache._cache is None:
        Wrapper_Runtime_Cache._init_wrapper()
    if Wrapper_Loggers._fallback_logger is None:
        Wrapper_Loggers._init_wrapper()
    for member in Block_RTC_Members:
        if Wrapper_Runtime_Cache.get_cache(member) is None:
            Wrapper_Runtime_Cache.create_cache(
                member.name,
                fast_deepcopy_with_fallback(member.value.default_value),
            )


def _group_suite(*test_case_names: str) -> unittest.TestSuite:
    from . import test_geometry_actions as module
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in test_case_names:
        suite.addTests(loader.loadTestsFromTestCase(getattr(module, name)))
    return suite


def build_suite_reads() -> unittest.TestSuite:
    _ensure_test_runtime()
    return _group_suite("Test_Mesh_Reads")


def build_suite_callbacks_and_writes() -> unittest.TestSuite:
    _ensure_test_runtime()
    return _group_suite("Test_Callbacks_And_Writes")


def build_suite_storage_and_grouping() -> unittest.TestSuite:
    _ensure_test_runtime()
    return _group_suite("Test_Storage_And_Grouping")


def build_suite_curves() -> unittest.TestSuite:
    _ensure_test_runtime()
    return _group_suite("Test_Curves")


def build_suite_serialization() -> unittest.TestSuite:
    _ensure_test_runtime()
    return _group_suite("Test_Serialization")


def build_suite() -> unittest.TestSuite:
    """Combined suite — every group together (delegates to test_geometry_actions' own
    build_suite(), the single place that list of classes is maintained). Used by run()/the
    headless __main__ entrypoint below."""
    from .test_geometry_actions import build_suite as build_all
    _ensure_test_runtime()
    return build_all()


def run(verbosity: int = 2) -> bool:
    """Run the suite. Returns True when everything passed."""
    result = unittest.TextTestRunner(verbosity=verbosity).run(build_suite())
    return result.wasSuccessful()


# ==============================================================================================================================
# HEADLESS ENTRY POINT
# ==============================================================================================================================

if __name__ == "__main__":
    import importlib
    import pathlib
    import sys

    import bpy

    block_dir  = pathlib.Path(__file__).resolve().parent.parent   # .../block_geometry_actions
    addon_dir  = block_dir.parent.parent                          # .../DGBlocks
    addon_name = addon_dir.name

    if str(addon_dir.parent) not in sys.path:
        sys.path.insert(0, str(addon_dir.parent))

    # Enabling the addon is what registers the block and its RTC members.
    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
    except Exception:
        pass

    tests_module = importlib.import_module(
        f"{addon_name}.native_blocks.block_geometry_actions.unit_tests.run_tests"
    )
    sys.exit(0 if tests_module.run() else 1)
