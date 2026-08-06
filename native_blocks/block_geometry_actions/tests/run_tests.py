"""
run_tests.py — single entry point for the block_geometry_actions test suite.

Interactive (Blender Text Editor / Python Console), addon already enabled:

    from DGBlocks.native_blocks.block_geometry_actions.tests import run_tests
    run_tests.run()

Headless:

    blender --background --python <addon>/native_blocks/block_geometry_actions/tests/run_tests.py

When run headless as __main__ the addon package is imported by name from the folder
three levels up, so no manual sys.path juggling is needed.
"""

import unittest


def run(verbosity: int = 2) -> bool:
    """Run the suite. Returns True when everything passed."""
    from .test_geometry_actions import build_suite

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
        f"{addon_name}.native_blocks.block_geometry_actions.tests.run_tests"
    )
    sys.exit(0 if tests_module.run() else 1)
