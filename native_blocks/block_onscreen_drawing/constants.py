
from enum import StrEnum, auto
import bpy
from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, String_Comparable_Mixin

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    hook_draw_event = Hook_Source_Declaration({"draw_handler_instance": any})


class Block_Loggers(String_Comparable_Mixin):    
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("DEBUG")
    SHADER_BATCH_EVENTS = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration({})
    SHADERS = RTC_Member_Declaration({})


# ==============================================================================================================================
# BLOCK-SPECIFIC DATA
# ==============================================================================================================================

# Defined by Blender's gpu module, not DGBlocks. This is a non-exhaustive list.
class Draw_Phase_Types(StrEnum):
    POST_PIXEL = auto()
    POST_VIEW  = auto()
    
# Defined by Blender's gpu module, not DGBlocks
# This is a non-exhaustive list. You can update it to suite your addon's needs
# More info: https://docs.blender.org/api/current/gpu.shader.html  
class Builtin_Shader_Names(StrEnum):
    SMOOTH_COLOR = auto()
    UNIFORM_COLOR = auto()
    POLYLINE_UNIFORM_COLOR = auto()
    POLYLINE_SMOOTH_COLOR = auto()
    POINT_UNIFORM_COLOR = auto()
    
# Defined by Blender's gpu module, not DGBlocks. This is a non-exhaustive list.
# More info: https://docs.blender.org/api/current/gpu_extras.batch.html
class Shader_Types(StrEnum):
    POINTS = auto()
    LINES = auto()
    TRIS = auto()
