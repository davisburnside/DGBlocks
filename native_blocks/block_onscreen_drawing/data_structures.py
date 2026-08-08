

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, final
import numpy as np
import bpy # type: ignore
import gpu # type: ignore
from mathutils import Matrix, Vector # type: ignore
from gpu_extras.batch import batch_for_shader

from .BL_drawing_structures import Builtin_Shader_Names, Draw_Phase_type, Draw_Region_Type, Draw_Space_Types, Shader_Types # type: ignore

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

@dataclass
class Drawhandler_Instance:
    """
    Owns a single live Blender draw handler, and the names of shaders that it draws. 
    Unlike most '_Instance' classes, this one has no associated '_Definition' class. It is created ad-hoc
    """
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    shader_names: list = field(default_factory=list)  # list[Shader_Instance]
    _handle: Any = field(init=False, default=None)


@dataclass
class Shader_Definition:
    """
    Flat descriptor for a single shader.  The caller supplies one Shader_Definition per
    logical shader, including the space/region/phase it should be drawn in.
    Wrapper_Shader_Manager groups these by (space, region, phase) internally and registers
    one Blender draw handler per unique group.

    Exactly one of builtin_shader_name or custom_shader_class must be set:
      - builtin_shader_name  : use a Blender built-in shader (validated against
                               _BUILTIN_SHADER_COMPATIBLE_TYPES).
      - custom_shader_class  : a Shader_Instance subclass that creates its own
                               gpu.shader in _shader_init.  custom_shader_kwargs
                               are forwarded as extra keyword arguments to that class.
    """
    shader_uid: str
    shader_type: Shader_Types
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type

    builtin_shader_name: Optional[Builtin_Shader_Names] = None
    builtin_shader_before_draw: Callable = None
    builtin_shader_after_draw: Callable = None

    custom_shader_class: Optional[type] = None  # Shader_Instance subclass
    custom_shader_kwargs: dict = field(default_factory=dict)


@dataclass
class Shader_Instance:

    # Primary fields
    shader_type: str  # Enum value of 'POINTS', 'LINES', 'TRIS'
    shader_uid: str
    src_block_id: str

    # Draw location — populated by Wrapper_Shader_Manager at creation time
    draw_space:  Any = None  # Draw_Space_Types
    draw_region: Any = None  # Draw_Region_Type
    draw_phase:  Any = None  # Draw_Phase_type

    # Shader & batch stats
    shader_creation_timestamp: int = 0
    last_batch_creation_timestamp: int = 0
    last_draw_timestamp: int = 0
    draw_count_of_batch: int = 0 # Resets to 0 when batch is recreated
    batch_count_of_shader: int = 0 # Resets to 0 when shader is recreated
    last_batch_creation_duration: float = 0.0
    
    # Status
    is_enabled: bool = True
    shader_error_str: str = None   # set by _universal_draw_callback on exception; None = no error

    # If builtin_shader_name is None, the shader is custom and must self-create in _shader_init
    builtin_shader_name: Optional[str] = None
    shader_actual: Any = field(init=False, default=None)  # Actual gpu.shader

    # Internal state
    _batch: Any = field(init=False, default=None)  # GPUBatch — expensive to rebuild
    _texture: Any = field(init=False, default=None)
    _points: np.ndarray = field(init=False, default=None)
    _colors: np.ndarray = field(init=False, default=None)
    _indices: np.ndarray = field(init=False, default=None)
    _highest_index: int = -1
    _needs_new_batch: bool = True
    _uniforms: dict = field(init=False, default_factory=dict, repr=False)  # Python-side cache of all set_uniform() calls

    # Optional callbacks for deault shaders
    _builtin_shader_before_draw = None
    _builtin_shader_after_draw = None

    # ----------------------------------------------------------
    # CALLED BEFORE SHADER DRAW — triggers expensive batch update

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

    # ----------------------------------------------------------
    # CALLED BEFORE SHADER DRAW — no batch update needed

    @final
    def set_uniform(self, name: str, value: Any):
        """Handles uniform mapping to GPU types and caches the value for Python-side read-back."""
        self._uniforms[name] = value
        if isinstance(value, (tuple, list, Matrix, Vector, float, np.ndarray)):
            self.shader_actual.uniform_float(name, value)
        elif isinstance(value, bool):
            self.shader_actual.uniform_bool(name, value)
        elif isinstance(value, int):
            self.shader_actual.uniform_int(name, value)
        elif isinstance(value, gpu.types.GPUTexture):
            self.shader_actual.uniform_sampler(name, value)

    @final
    def get_uniform(self, name: str) -> Any:
        """Return the last Python-side value passed to set_uniform(name), or None if never set."""
        return self._uniforms.get(name)

    # ----------------------------------------------------------
    # Computed helpers

    @property
    def _is_builtin_shader(self) -> bool:
        """True when this instance uses a Blender built-in shader program."""
        return self.builtin_shader_name is not None

    # ----------------------------------------------------------
    # Optional, for builtin shaders only

    # def _builtin_shader_before_draw(self):
    #     pass

    # def _builtin_shader_after_draw(self):
    #     pass

    # ----------------------------------------------------------
    # Can be overridden by child classes

    def _shader_init(self):
        if self.builtin_shader_name is not None:
            self.shader_actual = gpu.shader.from_builtin(self.builtin_shader_name)

    def _shader_update_batch(self):
        """Rebuilds the GPU batch from numpy data."""
        if self._points is None or len(self._points) == 0:
            self._needs_new_batch = False
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
            return

        self.shader_actual.bind()
        self._batch.draw(self.shader_actual)
