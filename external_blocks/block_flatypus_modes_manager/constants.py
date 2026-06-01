
from ...addon_helpers.data_structures import Logger_Declaration, RTC_Member_Declaration, String_Comparable_Mixin
from ...native_blocks.block_onscreen_drawing.data_structures import (
    Shader_Def,
    Shader_Types,
    Builtin_Shader_Names,
    Draw_Space_Types,
    Draw_Region_Type,
    Draw_Phase_type,
)
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

FLATYPUS_SHADER_DEFS = [
    Shader_Def(
        uid="BILLBOARD",
        group_id="FLATYPUS",
        shader_type=Shader_Types.TRIS,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        custom_shader_class=Billboard_Shader,
        custom_shader_kwargs={"image_name": "img"},
    ),
    Shader_Def(
        uid="SIMPLE_TRIS",
        group_id="FLATYPUS",
        shader_type=Shader_Types.TRIS,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        builtin_shader_name=Builtin_Shader_Names.SMOOTH_COLOR,
    ),
]
