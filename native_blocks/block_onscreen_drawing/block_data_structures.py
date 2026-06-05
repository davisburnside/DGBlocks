

from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
import logging
from typing import Any, Callable, Optional, Dict, List, final
import numpy as np
import bpy # type: ignore
import gpu # type: ignore
from mathutils import Matrix, Vector # type: ignore
from gpu_extras.batch import batch_for_shader

from .BL_gpu_data_structures import Builtin_Shader_Names, Draw_Phase_type, Draw_Region_Type, Draw_Space_Types, Shader_Types # type: ignore

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

@dataclass
class Drawhandler_Definition:
    """
    Internal grouping structure derived from a set of Shader_Defs that share
    the same (space, region, phase) tuple.  Not constructed by callers — built
    by Draw_Handler_Manager.set_state() during grouping.
    """
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    shaders: list = field(default_factory=list)  # list[Shader_Definition]


@dataclass
class Drawhandler_Instance:
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
class Shader_Definition:
    """
    Flat descriptor for a single shader.  The caller supplies one Shader_Definition per
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
    

    builtin_shader_name: Optional[Builtin_Shader_Names] = None
    builtin_shader_before_draw: Callable = None
    builtin_shader_after_draw: Callable = None

    custom_shader_class: Optional[type] = None # Shader_Instance subclass
    custom_shader_kwargs: dict = field(default_factory=dict)


@dataclass
class Shader_Instance:
    
    # Required fields for init
    shader_type: str # Enum of 'POINTS', 'LINES', 'TRIS'
    shader_uid: str
    shader_group_id: str

    last_draw_attempt_timestamp: int = -1
    is_enabled: bool = True
    shader_error_str: str = None
    
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
    _is_builtin_shader: bool = False
    
    #==========================================
    # CALLED BEFORE SHADER DRAW - Causes expensive batch update.
    # Should only be called if indices, points, or colors have changed since last draw

    @final
    def set_indices(self, value):
        self._indices = np.asarray(value, dtype=np.uint32)
        self._needs_new_batch = True
    
    @final
    def set_points(self, value):
        self._points = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True
    
    @final
    def set_colors(self, value):
        self._colors = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True

    #==========================================
    # CALLED BEFORE SHADER DRAW 
    # No batch update needed

    @final
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
    # Optional, for builtin shaders only

    def _builtin_shader_before_draw(self):
        pass

    def _builtin_shader_after_draw(self):
        pass

    #==========================================
    # Can be overwritten by child classes

    def _shader_init(self):
        
        if self.builtin_shader_name is not None:
            
            # Create a custom Shader. If the builtin name is None, the custom shader must be created manually
            self._is_builtin_shader = True
            self.shader_actual = gpu.shader.from_builtin(self.builtin_shader_name)

    def _shader_update_batch(self):
        """Rebuilds the GPU batch from numpy data"""
        
        if self._points is None:
            return

        content = {"pos": self._points}
        if self._colors is not None:
            content["color"] = self._colors

        self._batch = batch_for_shader(self.shader_actual, self.shader_type, content)
        self._needs_new_batch = False

    def _shader_draw(self):
        
        if self._needs_new_batch:
            self._shader_update_batch()
            self._needs_new_batch = False
        
        if self._batch is None:
            self.logger.error(f"shader {self.shader_uid} _batch is None")
            return

        self.shader_actual.bind()
        self._batch.draw(self.shader_actual)

