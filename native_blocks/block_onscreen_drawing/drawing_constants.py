
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import Callable, Optional
import bpy

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
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

@dataclass
class Shader_Def:
    """
    Flat descriptor for a single shader.  The caller supplies one Shader_Def per
    logical shader, including the space/region/phase it should be drawn in.
    Draw_Handler_Manager groups these by (space, region, phase) and registers one
    Blender draw handler per unique group.

    Exactly one of builtin_shader_name or custom_shader_class must be set:
      - builtin_shader_name  : use a Blender built-in shader (validated against
                               _BUILTIN_SHADER_COMPATIBLE_TYPES).
      - custom_shader_class  : a Shader_Instance subclass that creates its own
                               gpu.shader in __post_init__.  custom_shader_kwargs
                               are forwarded as extra keyword arguments to that class.
    """
    uid: str
    group_id: str
    shader_type: Shader_Types
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    # Exactly one must be provided:
    builtin_shader_name: Optional[Builtin_Shader_Names] = None
    custom_shader_class: Optional[type] = None       # Shader_Instance subclass
    custom_shader_kwargs: dict = field(default_factory=dict)
    # Optional draw override — forwarded to Shader_Instance at creation time.
    # Signature: func(shader_instance, *args).  When set, replaces the default bind+draw pipeline.
    draw_override_func: Optional[Callable] = None
    draw_override_args: tuple = field(default_factory=tuple)


@dataclass
class Handler_Def:
    """
    Internal grouping structure derived from a set of Shader_Defs that share
    the same (space, region, phase) tuple.  Not constructed by callers — built
    by Draw_Handler_Manager.set_state() during grouping.
    """
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    shaders: list = field(default_factory=list)  # list[Shader_Def]


# ==============================================================================================================================
# VALIDATION DATA
# ==============================================================================================================================

# Hardcoded allowlist of known-valid (Draw_Space_Types, Draw_Region_Type, Draw_Phase_type) combinations.
# draw_handler_add will silently fail or crash for invalid combinations, so we validate upfront.
_VALID_SPACE_REGION_PHASE_COMBOS: frozenset = frozenset({
    # VIEW_3D
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.PRE_VIEW),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.HEADER,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.UI,            Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.TOOLS,         Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.HUD,           Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.VIEW_3D,          Draw_Region_Type.XR,            Draw_Phase_type.POST_VIEW),
    # IMAGE_EDITOR
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.PRE_VIEW),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_VIEW),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.WINDOW,        Draw_Phase_type.POST_PIXEL),
    (Draw_Space_Types.IMAGE_EDITOR,     Draw_Region_Type.HEADER,        Draw_Phase_type.POST_PIXEL),
    # NODE_EDITOR
    (Draw_Space_Types.NODE_EDITOR,      Draw_Region_Type.WINDOW,        Draw_Phase_type.PRE_VIEW),
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
# Used to validate Shader_Def entries in set_state() before any Blender state is mutated.
_BUILTIN_SHADER_COMPATIBLE_TYPES: dict = {
    Builtin_Shader_Names.SMOOTH_COLOR:           {Shader_Types.POINTS, Shader_Types.LINES, Shader_Types.TRIS},
    Builtin_Shader_Names.UNIFORM_COLOR:          {Shader_Types.POINTS, Shader_Types.LINES, Shader_Types.TRIS},
    Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR: {Shader_Types.LINES},
    Builtin_Shader_Names.POLYLINE_SMOOTH_COLOR:  {Shader_Types.LINES},
    Builtin_Shader_Names.POINT_UNIFORM_COLOR:    {Shader_Types.POINTS},
}
