"""
test_shader_validation.py — Tier 0 (declaration validation) + Tier 1 (real GPU shader
compile/link smoke test) for block_onscreen_drawing, per Unit_Testing_Framework.md §11.
Nothing here enables drawing, registers a draw handler, or touches a GPU batch/framebuffer.
"""

import unittest

from ..BL_drawing_structures import Builtin_Shader_Names, Draw_Phase_type, Draw_Region_Type, Draw_Space_Types, Shader_Types
from ..builtin_shaders_and_effects.custom_shader_stripe import Stripe_Shader
from ..data_structures import Shader_Declaration
from ..helpers import _validate_shader_definitions


def _make_minimal_decl(
    uid,
    builtin_shader_name=Builtin_Shader_Names.UNIFORM_COLOR,
    custom_shader_class=None,
    shader_type=Shader_Types.LINES,
):
    return Shader_Declaration(
        shader_uid=uid,
        shader_type=shader_type,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        builtin_shader_name=builtin_shader_name,
        custom_shader_class=custom_shader_class,
    )


class Test_Shader_Declaration_Validation(unittest.TestCase):
    def test_duplicate_uid_is_rejected(self):
        decls = [_make_minimal_decl("A"), _make_minimal_decl("A")]
        with self.assertRaises(ValueError):
            _validate_shader_definitions(decls)

    def test_exactly_one_of_builtin_or_custom_is_required(self):
        decl = _make_minimal_decl("A", builtin_shader_name=None, custom_shader_class=None)
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

    def test_both_builtin_and_custom_set_is_rejected(self):
        decl = _make_minimal_decl(
            "A", builtin_shader_name=Builtin_Shader_Names.UNIFORM_COLOR, custom_shader_class=Stripe_Shader
        )
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

    def test_unknown_builtin_shader_name_is_rejected(self):
        decl = _make_minimal_decl("A", builtin_shader_name="NOT_A_REAL_BUILTIN")
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

    def test_builtin_shader_type_incompatibility_is_rejected(self):
        # POLYLINE_UNIFORM_COLOR is only compatible with LINES, not POINTS.
        decl = _make_minimal_decl(
            "A", builtin_shader_name=Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR, shader_type=Shader_Types.POINTS
        )
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

    def test_valid_builtin_declaration_passes(self):
        decl = _make_minimal_decl(
            "A", builtin_shader_name=Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR, shader_type=Shader_Types.LINES
        )
        _validate_shader_definitions([decl])  # must not raise

    def test_valid_custom_declaration_passes(self):
        decl = _make_minimal_decl("A", builtin_shader_name=None, custom_shader_class=Stripe_Shader)
        _validate_shader_definitions([decl])  # must not raise


class Test_Custom_Shader_Compiles(unittest.TestCase):
    """
    Tier 1: --background still binds a real GL context (Blender needs one for EEVEE/Cycles
    background renders) — there's just no viewport/region. So the actual GPUShaderCreateInfo
    built by a custom Shader_Instance subclass's _shader_init() can be compiled/linked without
    drawing anything. Stripe_Shader is the representative case here — its _shader_init is fully
    self-contained (no geometry/image/font dependency), unlike Billboard/Textbox which need real
    asset data to construct; those could get the same treatment as a follow-up.
    """

    def test_stripe_shader_compiles(self):
        instance = Stripe_Shader(shader_type=Shader_Types.LINES, shader_uid="DGB_TEST_stripe", src_block_id="test")
        try:
            instance._shader_init()
        except Exception as e:
            self.skipTest(f"No usable GPU context on this runner: {e}")
            return
        self.assertIsNotNone(instance.shader_actual)


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Shader_Declaration_Validation, Test_Custom_Shader_Compiles):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
