
# from dataclasses import dataclass, field
# from enum import Enum, StrEnum, auto
# import logging
# from typing import Any, Optional, Dict, List
# import numpy as np
# import bpy
# from mathutils import Matrix, Vector
# import gpu
# from gpu_extras.batch import batch_for_shader

# from ..blocks_natively_included._block_core.core_feature_logs import get_logger
# from .shaders.my_custom_shaders import create_grid_tri_shader


#================================================================
# CONSTANTS
#================================================================

# Defined by Blender's gpu module, not DGBlocks
# This is a non-exhaustive list. You can update it to suite your addon's needs
# More info: https://docs.blender.org/api/current/gpu.shader.html  
class Basic_Builtin_Shader_Names(StrEnum):
    SMOOTH_COLOR = auto()
    UNIFORM_COLOR = auto()
    POLYLINE_UNIFORM_COLOR = auto()
    POLYLINE_SMOOTH_COLOR = auto()
    POINT_UNIFORM_COLOR = auto()
    
# Defined by Blender's gpu module, not DGBlocks
# This is a non-exhaustive list. You can update it to suite your addon's needs
# More info: https://docs.blender.org/api/current/gpu_extras.batch.html
class Shader_Types(StrEnum):
    POINTS = auto()
    LINES = auto()
    TRIS = auto()

#================================================================
# SHADER WRAPPER
#================================================================

@dataclass
class Shader_Instance:
    
    # Reason for @dataclass shader-wrapper structure:
    # The methods operate on the instance's own data
    # The shader wrapper class represents a cohesive "thing" with both state and behavior
    # Boilerplate reduction 
    
    # Required fields
    shader_type: str
    shader_uid: str
    
    # Shader wrappers must have a either a builtin or custom builder callback, not both
    builtin_shader_name: Optional[str] = None
    callback_build_custom_shader: callable = None

    # Group is an optional field, used for getting/killing several shaders at once
    shader_group_id: Optional[str] = None
    
    # Internal State
    _batch: gpu.types.GPUBatch = field(init=False, default=None) # Expensive to update, should only update if _points or _colors change
    _shader_actual: Any = field(init=False, default=None) # Actual gpu.shader
    _texture: Any = field(init=False, default=None) # Only used for Images
    _points: np.ndarray = field(init=False, default=None)
    _indices: np.ndarray = field(init=False, default=None) # Only used for TRIS-type shaders
    _colors: np.ndarray = field(init=False, default=None) # Only used for SMOOTH_COLOR, not UNIF9RM_COLOR Shaders
    
    _needs_new_batch: bool = True


class Wrapper_Shader_Manager:

    #==========================================
    # CALLED DURING SHADER INITIALIZATION

    def __post_init__(self):
        
        self._setup_shader()

    def _setup_shader(self):
        
        self.logger = get_logger()
        
        # Input validation
        if self.builtin_shader_name is None and self.custom_shader_name is None:
            raise Exception("Basic and Custom Shader names are both None, unable to create Shader")
        if self.builtin_shader_name is not None and self.custom_shader_name is not None:
            raise Exception("Basic and Custom Shader names are both not None, you must create either one or the other")
        
        # Create a custom Shader
        if self.callback_build_custom_shader is None: 
            self._shader_actual = gpu.shader.from_builtin(self.builtin_shader_name)

        # Create a basic builtin Shader
        else: 
            self._shader_actual = self.callback_build_custom_shader()

    #==========================================
    # CALLED AFTER SHADER INITIALIZATION

    @_points.setter
    def points(self, value):
        self._points = np.array(value, dtype=np.float32) if not isinstance(value, np.ndarray) else value
        self._needs_new_batch = True

    @_colors.setter
    def colors(self, value):
        self._colors = np.array(value, dtype=np.float32) if not isinstance(value, np.ndarray) else value
        self._needs_new_batch = True

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
