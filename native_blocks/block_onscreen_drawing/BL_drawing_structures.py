

from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
import logging
from typing import Any, Optional, Dict, List, final
import numpy as np
import bpy # type: ignore
import gpu # type: ignore
from mathutils import Matrix, Vector # type: ignore
from gpu_extras.batch import batch_for_shader # type: ignore

# ==============================================================================================================================
# DRAW_HANDLER_CONSTANTS
# ==============================================================================================================================

# Defined by Blender's WindowManager
# Tops hierarchy
class Draw_Space_Types(Enum):
    VIEW_3D          = bpy.types.SpaceView3D
    NODE_EDITOR      = bpy.types.SpaceNodeEditor
    IMAGE_EDITOR     = bpy.types.SpaceImageEditor
    SEQUENCE_EDITOR  = bpy.types.SpaceSequenceEditor
    CLIP_EDITOR      = bpy.types.SpaceClipEditor
    DOPESHEET_EDITOR = bpy.types.SpaceDopeSheetEditor
    GRAPH_EDITOR     = bpy.types.SpaceGraphEditor
    # NLA_EDITOR       = bpy.types.SpaceNLAEditor # AttributeError: 'module' object has no attribute 'SpaceNLAEditor'
    TEXT_EDITOR      = bpy.types.SpaceTextEditor
    OUTLINER         = bpy.types.SpaceOutliner
    PROPERTIES       = bpy.types.SpaceProperties
    FILE_BROWSER     = bpy.types.SpaceFileBrowser
    SPREADSHEET      = bpy.types.SpaceSpreadsheet
    CONSOLE          = bpy.types.SpaceConsole
    INFO             = bpy.types.SpaceInfo
    PREFERENCES      = bpy.types.SpacePreferences

# Defined by Blender's WindowManager
# One or more per Draw_Space_Types, not all are valid in all cases
class Draw_Region_Type(StrEnum):
        
    @staticmethod # Preserves uppercase str (lowercase by python default)
    def _generate_next_value_(name, *args):
        return name  
 
    WINDOW          = auto()
    HEADER          = auto()
    TOOL_HEADER     = auto()
    FOOTER          = auto()
    UI              = auto()
    TOOLS           = auto()
    TOOL_PROPS      = auto()
    CHANNELS        = auto()
    PREVIEW         = auto()
    NAVIGATION_BAR  = auto()
    EXECUTE         = auto()
    HUD             = auto()
    TEMPORARY       = auto()
    XR              = auto()

# Defined by Blender's WindowManager
# One or more per Draw_Region_Type, not all are valid in all cases
class Draw_Phase_type(StrEnum):
            
    @staticmethod # Preserves uppercase str (lowercase by python default)
    def _generate_next_value_(name, *args):
        return name  
 
    PRE_VIEW    = auto()
    POST_VIEW   = auto()
    POST_PIXEL  = auto()
    BACKDROP    = auto()

# Defined by Blender's gpu module. This is a non-exhaustive list.
# More info: https://docs.blender.org/api/current/gpu.shader.html  
class Builtin_Shader_Names(StrEnum):
            
    @staticmethod # Preserves uppercase str (lowercase by python default)
    def _generate_next_value_(name, *args):
        return name  
 
    SMOOTH_COLOR = auto()
    UNIFORM_COLOR = auto()
    POLYLINE_UNIFORM_COLOR = auto()
    POLYLINE_SMOOTH_COLOR = auto()
    POINT_UNIFORM_COLOR = auto()
    
# Defined by Blender's gpu module. This is a non-exhaustive list.
# More info: https://docs.blender.org/api/current/gpu_extras.batch.html
class Shader_Types(StrEnum):
            
    @staticmethod # Preserves uppercase str (lowercase by python default)
    def _generate_next_value_(name, *args):
        return name  
 
    POINTS = auto()
    LINES = auto()
    TRIS = auto()


# ==============================================================================================================================
# VALIDATION DATA
# ==============================================================================================================================

# Hardcoded allowlist of known-valid (Draw_Space_Types, Draw_Region_Type, Draw_Phase_type) combinations.
# draw_handler_add will silently fail or crash for invalid combinations, so we validate upfront.
_VALID_SPACE_REGION_PHASE_COMBOS: frozenset = frozenset({
    # VIEW_3D
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.HEADER,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.UI,            Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.TOOLS,         Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.HUD,           Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.XR,            Draw_Phase_type.POST_VIEW),
    # IMAGE_EDITOR
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.HEADER,        Draw_Phase_type.POST_PIXEL),
    # NODE_EDITOR
    (Draw_Space_Types.NODE_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.NODE_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.NODE_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.NODE_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.BACKDROP),
    # SEQUENCE_EDITOR
    (Draw_Space_Types.SEQUENCE_EDITOR,  Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.SEQUENCE_EDITOR,  Draw_Region_Type.PREVIEW,       Draw_Phase_type.POST_PIXEL),
    # CLIP_EDITOR
    (Draw_Space_Types.CLIP_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.CLIP_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    # DOPESHEET_EDITOR / GRAPH_EDITOR / NLA_EDITOR
    (Draw_Space_Types.DOPESHEET_EDITOR, Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.GRAPH_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    # (Draw_Space_Types.NLA_EDITOR,       Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
})

# Maps each builtin shader name to the set of Shader_Types it is compatible with.
# Used to validate Shader_Definition entries in set_state() before any Blender state is mutated.
_BUILTIN_SHADER_COMPATIBLE_TYPES: dict = {
    Builtin_Shader_Names.SMOOTH_COLOR:           {Shader_Types.POINTS, Shader_Types.LINES, Shader_Types.TRIS},
    Builtin_Shader_Names.UNIFORM_COLOR:          {Shader_Types.POINTS, Shader_Types.LINES, Shader_Types.TRIS},
    Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR: {Shader_Types.LINES},
    Builtin_Shader_Names.POLYLINE_SMOOTH_COLOR:  {Shader_Types.LINES},
    Builtin_Shader_Names.POINT_UNIFORM_COLOR:    {Shader_Types.POINTS},
}
