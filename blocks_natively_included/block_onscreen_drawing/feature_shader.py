
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
import logging
from typing import Any, Optional, Dict, List
import numpy as np
import bpy # type: ignore
import gpu # type: ignore
from mathutils import Matrix, Vector # type: ignore
from gpu_extras.batch import batch_for_shader # type: ignore

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Shader_Types, Builtin_Shader_Names

#================================================================
# SHADER INSTANCE
#================================================================

# Wrapper_Shader differs from most other wrapper classes. It is not a subclass of Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, or Abstract_Datawrapper_Instance_Manager
# Each shader's lifecycle is 100% managed though Wrapper_Draw_Handlers, so Wrapper_Shader does not need any instance-mgmt funcs 
@dataclass
class Shader_Instance:
    
    # Required fields
    shader_type: str
    shader_uid: str
    shader_group_id: str
    
    # Shader wrappers must have a either a builtin or custom builder callback, not both
    builtin_shader_name: Optional[str] = None

    # Internal State
    _batch: gpu.types.GPUBatch = field(init=False, default=None) # Expensive to update, should only update if _points or _colors change
    _shader_actual: Any = field(init=False, default=None) # Actual gpu.shader
    _texture: Any = field(init=False, default=None) # Only used for Images
    _points: np.ndarray = field(init=False, default=None)
    _colors: np.ndarray = field(init=False, default=None) # Only used for SMOOTH_COLOR, not UNIF9RM_COLOR Shaders
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
            self._shader_actual = gpu.shader.from_builtin(self.builtin_shader_name)

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
            self._shader_actual.uniform_float(name, value)
        elif isinstance(value, bool):
            self._shader_actual.uniform_bool(name, value)
        elif isinstance(value, int):
            self._shader_actual.uniform_int(name, value)
        elif isinstance(value, gpu.types.GPUTexture):
            self._shader_actual.uniform_sampler(name, value)

    #==========================================
    # SHADER DRAW

    def _update_batch(self):
        """Rebuilds the GPU batch from numpy data"""
        
        if self._points is None:
            return

        content = {"pos": self._points}
        if self._colors is not None:
            content["color"] = self._colors

        self._batch = batch_for_shader(self._shader_actual, self.shader_type, content)
        self._needs_new_batch = False

    def draw(self):
        
        if self._needs_new_batch:
            self._update_batch()
        
        if self._batch is None:
            self.logger.error(f"shader {self.shader_uid} _batch is None")
            return

        self._shader_actual.bind()
        self._batch.draw(self._shader_actual)
