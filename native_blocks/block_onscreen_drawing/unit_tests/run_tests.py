"""
run_tests.py — single entry point for the block_onscreen_drawing test suite.

Interactive (Blender Text Editor / Python Console), addon already enabled:

    from DGBlocks.native_blocks.block_onscreen_drawing.unit_tests import run_tests
    run_tests.run()

Headless:

    blender --background --factory-startup --python-exit-code 1 --python <addon>/native_blocks/block_onscreen_drawing/unit_tests/run_tests.py

Also runs as part of the addon-wide pass via the Unit Tests panel / Wrapper_Unit_Testing (this
block subscribes through hook_get_unit_test_declarations) — this file remains for standalone use.
"""

import unittest


def build_suite_shader_validation() -> unittest.TestSuite:
    from .test_shader_validation import Test_Shader_Declaration_Validation
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Shader_Declaration_Validation))
    return suite


def build_suite_shader_creation() -> unittest.TestSuite:
    from .test_shader_validation import Test_Custom_Shader_Compiles
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Custom_Shader_Compiles))
    return suite


def build_suite_geometry_math() -> unittest.TestSuite:
    from .test_pure_math import build_suite
    return build_suite()


def build_suite() -> unittest.TestSuite:
    """Combined suite — every group together. Used by run()/the headless __main__ entrypoint below."""
    suite = unittest.TestSuite()
    for sub_build in (build_suite_shader_validation, build_suite_shader_creation, build_suite_geometry_math):
        suite.addTests(sub_build())
    return suite


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

    block_dir  = pathlib.Path(__file__).resolve().parent.parent   # .../block_onscreen_drawing
    addon_dir  = block_dir.parent.parent                          # .../DGBlocks
    addon_name = addon_dir.name

    if str(addon_dir.parent) not in sys.path:
        sys.path.insert(0, str(addon_dir.parent))

    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
    except Exception:
        pass

    tests_module = importlib.import_module(
        f"{addon_name}.native_blocks.block_onscreen_drawing.unit_tests.run_tests"
    )
    sys.exit(0 if tests_module.run() else 1)
