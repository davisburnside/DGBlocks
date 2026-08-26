"""
run_tests.py — single entry point for the block_timers test suite.

Interactive (Blender Text Editor / Python Console), addon already enabled:

    from DGBlocks.native_blocks.block_timers.unit_tests import run_tests
    run_tests.run()

Headless:

    blender --background --factory-startup --python-exit-code 1 --python <addon>/native_blocks/block_timers/unit_tests/run_tests.py

Also runs as part of the addon-wide pass via the Unit Tests panel / Wrapper_Unit_Testing (this
block subscribes through hook_get_unit_test_declarations) — this file remains for standalone use.
"""

import unittest


def build_suite() -> unittest.TestSuite:
    from .test_timers import build_suite as build_timers_suite
    return build_timers_suite()


def run(verbosity: int = 2) -> bool:
    return unittest.TextTestRunner(verbosity=verbosity).run(build_suite()).wasSuccessful()


# ==============================================================================================================================
# HEADLESS ENTRY POINT
# ==============================================================================================================================

if __name__ == "__main__":
    import importlib
    import pathlib
    import sys

    import bpy

    block_dir  = pathlib.Path(__file__).resolve().parent.parent   # .../block_timers
    addon_dir  = block_dir.parent.parent                          # .../DGBlocks
    addon_name = addon_dir.name

    if str(addon_dir.parent) not in sys.path:
        sys.path.insert(0, str(addon_dir.parent))

    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
    except Exception:
        pass

    tests_module = importlib.import_module(
        f"{addon_name}.native_blocks.block_timers.unit_tests.run_tests"
    )
    sys.exit(0 if tests_module.run() else 1)
