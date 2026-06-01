
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
import time
from typing import Any, Callable, Optional

import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

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


@dataclass
class Handler_Instance:
    """
    Owns a single live Blender draw handler and the Shader_Instance objects
    that belong to it.  Responsible for its own full teardown.
    """
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    shaders: list = field(default_factory=list)  # list[Shader_Instance]
    _handle: Any = field(init=False, default=None)

    def teardown(self) -> None:
        """Remove the Blender draw handler and discard all shader references."""
        if self._handle is not None:
            try:
                self.space.value.draw_handler_remove(self._handle, self.region.value)
            except Exception:
                pass  # handler may already be gone (e.g. context teardown)
            self._handle = None
        self.shaders.clear()


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
class Shader_Instance:
    
    # Required fields for init
    shader_type: str # Enum of 'POINTS', 'LINES', 'TRIS'
    shader_uid: str
    shader_group_id: str

    last_draw_attempt_timestamp: int = -1
    is_enabled: bool = True
    error_str: str = None

    # Optional draw override.  Signature: func(shader_instance, *args).
    # When set, replaces the default bind+batch-draw pipeline entirely.
    # draw_error_count and batch telemetry are still auto-tracked by the outer callback.
    draw_override_func: Optional[Callable] = None
    draw_override_args: tuple = field(default_factory=tuple)

    # Telemetry — auto-tracked; do not set manually
    batch_creation_duration_ms: float = 0.0  # wall-clock ms of the last _update_batch() call
    batch_creation_count: int = 0             # total number of batches created on this instance
    draw_error_count: int = 0                 # total exceptions caught by callback_omnishader_draw

    # If 'builtin_shader_name' is None, the shader is custom and must must self-create inside its __post_init__ override
    builtin_shader_name: Optional[str] = None 
    shader_actual: Any = field(init=False, default=None) # Actual gpu.shader. Will be populated for both custom and builtin shaders

    # Internal State
    _batch: gpu.types.GPUBatch = field(init=False, default=None) # Expensive to update, should only update if _points or _colors change
    _texture: Any = field(init=False, default=None) # Only used for Images
    _points: np.ndarray = field(init=False, default=None)
    _colors: np.ndarray = field(init=False, default=None) # Only used for SMOOTH_COLOR, not UNIFORM_COLOR Shaders
    _indices: np.ndarray = field(init=False, default=None) # Only used for TRIS-type shaders
    _highest_index: int = -1 # used when dynamically updating a batch with new tris
    _needs_new_batch: bool = True

    def __post_init__(self):
        
        shader_types_list = [i.name for i in list(Shader_Types)]
        if self.shader_type not in shader_types_list:
            raise Exception(f"Invalid Shader type '{self.shader_type }', must be {shader_types_list}")
                
        if self.builtin_shader_name is not None:
            
            bulitin_shaders_list =  [i.name for i in list(Builtin_Shader_Names)]
            if self.builtin_shader_name not in bulitin_shaders_list:
                raise Exception(f"Invalid Shader bulitin name '{self.builtin_shader_name }', must be {bulitin_shaders_list}")
            
            # Create a custom Shader. If the builtin name is None, the custom shader must be created manually
            self.shader_actual = gpu.shader.from_builtin(self.builtin_shader_name)

    #==========================================
    # CALLED BEFORE SHADER DRAW - Causes expensive batch update.
    # Should only be called if indices, points, or colors have changed since last draw

    def set_indices(self, value):
        self._indices = np.asarray(value, dtype=np.uint32)
        self._needs_new_batch = True
    
    def set_points(self, value):
        self._points = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True
    
    def set_colors(self, value):
        self._colors = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True

    #==========================================
    # CALLED BEFORE SHADER DRAW 
    # No batch update needed

    def set_uniform(self, name: str, value: Any):
        """Handles uniform mapping to GPU types"""
        
        if isinstance(value, (tuple, list, Matrix, Vector, float, np.ndarray)):
            self.shader_actual.uniform_float(name, value)
        elif isinstance(value, bool):
            self.shader_actual.uniform_bool(name, value)
        elif isinstance(value, int):
            self.shader_actual.uniform_int(name, value)
        elif isinstance(value, gpu.types.GPUTexture):
            self.shader_actual.uniform_sampler(name, value)

    #==========================================
    # SHADER DRAW

    def _update_batch(self):
        """Rebuilds the GPU batch from numpy data.  Tracks timing and creation count."""

        if self._points is None:
            return

        content = {"pos": self._points}
        if self._colors is not None:
            content["color"] = self._colors

        _t0 = time.perf_counter()
        self._batch = batch_for_shader(self.shader_actual, self.shader_type, content)
        self.batch_creation_duration_ms = (time.perf_counter() - _t0) * 1000.0
        self.batch_creation_count += 1
        self._needs_new_batch = False

    def draw(self):
        """
        Draw this shader.  If draw_override_func is set it is called instead of the
        default bind+batch pipeline.  Signature: func(shader_instance, *draw_override_args).
        draw_error_count is incremented by callback_omnishader_draw on any exception,
        so both paths are automatically tracked.
        """

        if self._needs_new_batch:
            self._update_batch()
            self._needs_new_batch = False

        if self._batch is None:
            raise Exception(f"Shader {self.shader_uid} batch is null")

        if self.draw_override_func is not None:
            self.draw_override_func(self, *self.draw_override_args)
            return

        self.shader_actual.bind()
        self._batch.draw(self.shader_actual)





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
