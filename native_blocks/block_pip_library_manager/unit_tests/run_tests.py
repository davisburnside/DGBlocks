"""
run_tests.py — single entry point for the block_pip_library_manager test suite.

Interactive (Blender Text Editor / Python Console), addon already enabled:

    from DGBlocks.native_blocks.block_pip_library_manager.unit_tests import run_tests
    run_tests.run()

Headless:

    blender --background --python <addon>/native_blocks/block_pip_library_manager/unit_tests/run_tests.py

When run headless as __main__ the addon package is imported by name from the folder
three levels up, so no manual sys.path juggling is needed.

This suite also runs as part of the full addon-wide pass via block_core's
Wrapper_Unit_Testing (see hook_get_unit_test_declarations in this block's __init__.py) —
this file remains for standalone/manual use, its shape is unchanged by that wiring.

Unlike block_geometry_actions, these tests touch no RTC/bpy state at all (tempdir-scoped
file operations and pure dataclass/function checks only), so no RTC pre-seeding is needed.
"""

import unittest


def build_suite_security() -> unittest.TestSuite:
    from .test_helpers import Test_Security_Validation
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Security_Validation))
    return suite


def build_suite_helpers() -> unittest.TestSuite:
    from .test_helpers import Test_Requirement_Helpers
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Requirement_Helpers))
    return suite


def build_suite_architecture() -> unittest.TestSuite:
    from .test_helpers import Test_Architecture_Invariants
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Architecture_Invariants))
    return suite


def build_suite_install_worker() -> unittest.TestSuite:
    from .test_install_worker import Test_Pip_Install_Worker
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Pip_Install_Worker))
    return suite


def build_suite() -> unittest.TestSuite:
    """Combined suite — every group together. Used by run()/the headless __main__ entrypoint below."""
    suite = unittest.TestSuite()
    for sub_build in (build_suite_security, build_suite_helpers, build_suite_architecture, build_suite_install_worker):
        suite.addTests(sub_build())
    return suite


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

    block_dir  = pathlib.Path(__file__).resolve().parent.parent   # .../block_pip_library_manager
    addon_dir  = block_dir.parent.parent                          # .../DGBlocks
    addon_name = addon_dir.name

    if str(addon_dir.parent) not in sys.path:
        sys.path.insert(0, str(addon_dir.parent))

    # Enabling the addon is what registers the block.
    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
    except Exception:
        pass

    tests_module = importlib.import_module(
        f"{addon_name}.native_blocks.block_pip_library_manager.unit_tests.run_tests"
    )
    sys.exit(0 if tests_module.run() else 1)
