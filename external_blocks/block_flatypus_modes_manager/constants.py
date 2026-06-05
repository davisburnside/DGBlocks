
import gpu

from ...addon_helpers.data_structures import Logger_Declaration, RTC_Member_Declaration, String_Comparable_Mixin

from ...native_blocks.block_onscreen_drawing.block_data_structures import Shader_Definition
from ...native_blocks.block_onscreen_drawing.BL_gpu_data_structures import Shader_Types, Builtin_Shader_Names, Draw_Space_Types, Draw_Region_Type, Draw_Phase_type
from ...native_blocks.block_onscreen_drawing.helpers import set_draw_geometry_occluded

from .custom_shaders.billboard_image_shader import Billboard_Shader

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Loggers(String_Comparable_Mixin):
    ASSEMBLY_MODE_LIFECYCLE = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    IS_ASSEMBLY_MODE_ACTIVE = RTC_Member_Declaration(False)


# ==============================================================================================================================
# SHADER DEFINITIONS
# Passed as-is to Wrapper_Draw_Handlers.set_state().
# Both shaders share (VIEW_3D, WINDOW, POST_VIEW) → one Blender draw handler registered for the pair.
# ==============================================================================================================================

def _simple2d_before_draw(self):

    # print("override draw", self)
    self.set_uniform("color", (1,0,0,1))
    gpu.state.line_width_set(5)

def set_occulded(self):

    set_draw_geometry_occluded()

FLATYPUS_SHADER_DEFS = [
    Shader_Definition(
            uid="BILLBOARD",
            group_id="FLATYPUS",
            shader_type=Shader_Types.TRIS,
            space=Draw_Space_Types.VIEW_3D,
            region=Draw_Region_Type.WINDOW,
            phase=Draw_Phase_type.POST_VIEW,
            custom_shader_class=Billboard_Shader,
            custom_shader_kwargs={"image_name": "img"},
    ),
    Shader_Definition(
            uid="SIMPLE_TRIS",
            group_id="FLATYPUS",
            shader_type=Shader_Types.TRIS,
            space=Draw_Space_Types.VIEW_3D,
            region=Draw_Region_Type.WINDOW,
            phase=Draw_Phase_type.POST_VIEW,
            builtin_shader_name=Builtin_Shader_Names.SMOOTH_COLOR,
    ),
        Shader_Definition(
            uid="SIMPLE_2D",
            group_id="FLATYPUS",
            shader_type=Shader_Types.LINES,
            space=Draw_Space_Types.VIEW_3D,
            region=Draw_Region_Type.WINDOW,
            phase=Draw_Phase_type.POST_PIXEL,
            builtin_shader_name=Builtin_Shader_Names.UNIFORM_COLOR,
            builtin_shader_before_draw = _simple2d_before_draw
    ),
]
