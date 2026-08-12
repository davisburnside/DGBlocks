"""

Custom Shader_Instance subclass: a dashed POLYLINE with true, Metal-safe line thickness.

WHY THIS EXISTS
---------------
The legacy dashed-line shader (see legacy_custom_shader_linedash.py) drew GL_LINES and relied
on gpu.state.line_width_set()/GL line width for thickness. That is ignored on macOS/Metal, so
the line always rendered 1px there. Blender's own POLYLINE_* builtins avoid this by expanding
each segment into a screen-space quad (2 triangles) in the vertex shader and offsetting the
corners perpendicular to the segment by half the thickness — thickness then becomes real
geometry that every backend honours. This shader does exactly that, and additionally carries
the legacy dash fragment logic (dash_width / udash_factor / two colors).

INDEPENDENCE
------------
All GPU logic lives here. Controlling code only ever calls the small public setters below
(set_polyline / set_line_thickness / set_dash_width / set_dash_ratio / set_dash_colors) and
never touches uniforms or GLSL. MVP + viewport uniforms are self-managed in _shader_draw().

Setup: 'shader_uid' is the only Shader_Declaration value you control. The rest must match:
Shader_Declaration(
    shader_uid="MY_DASH",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=Polyline_Dash_Shader,
)

Geometry input (set_polyline) is a flat list of segment endpoint PAIRS, i.e. every two
consecutive points define one line segment:
    shader.set_polyline([A, B,  B, C,  C, D, ...])   # world-space (x, y, z)
"""


from dataclasses import dataclass, field
from typing import Any
import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# --------------------------------------------------------------
# Inter-block imports
from ....native_blocks.block_onscreen_drawing.data_structures import Shader_Instance

# --------------------------------------------------------------
# Shader Constants

# Each vertex carries BOTH endpoints of its segment (seg_a, seg_b) so the vertex shader can
# compute a consistent screen-space direction, plus which end this corner sits on (end_flag)
# and which side of the line it offsets to (side, +1 / -1). seg_a doubles as the dash origin.
vertex_source = """
void main()
{
    vec4 a_clip = ModelViewProjectionMatrix * vec4(seg_a, 1.0);
    vec4 b_clip = ModelViewProjectionMatrix * vec4(seg_b, 1.0);

    vec2 half_vp = 0.5 * viewport_size;
    vec2 a_scr = (a_clip.xy / a_clip.w) * half_vp;
    vec2 b_scr = (b_clip.xy / b_clip.w) * half_vp;

    vec2 dir = b_scr - a_scr;
    float len = length(dir);
    dir = (len > 0.0) ? dir / len : vec2(1.0, 0.0);
    vec2 nrm = vec2(-dir.y, dir.x);

    vec4 base_clip = (end_flag < 0.5) ? a_clip : b_clip;

    vec2 offset_px  = nrm * side * (line_thickness * 0.5);
    vec2 offset_ndc = offset_px / half_vp;

    gl_Position = base_clip;
    gl_Position.xy += offset_ndc * base_clip.w;

    // Screen-space positions used for the dash pattern (view-correct dashing).
    stipple_co    = (base_clip.xy / base_clip.w) * half_vp + offset_px;
    stipple_start = a_scr;
}
"""

# Ported from Blender's gpu_shader_2D_line_dashed_frag.glsl (see legacy file for source URL).
fragment_source = """
void main()
{
    float distance_along_line = distance(stipple_co, stipple_start) + (phase * dash_width);

    /* Solid line case. */
    if (udash_factor >= 1.0) {
        fragColor = color;
    }
    /* Actually dashed line. */
    else {
        float normalized_distance = fract(distance_along_line / dash_width);
        if (normalized_distance <= udash_factor) {
            fragColor = color;
        }
        else if (colors_len > 0) {
            fragColor = color2;
        }
        else {
            discard;
        }
    }
}
"""


def _make_polyline_verts(points_list):
    """
    Expand a flat list of segment endpoint pairs into quad geometry (2 tris per segment).

    points_list[2*i], points_list[2*i + 1] are the two endpoints (A, B) of segment i.
    Returns (seg_a, seg_b, side, end_flag, indices) arrays ready for batch_for_shader.
    """
    seg_a = []
    seg_b = []
    side = []
    end_flag = []
    indices = []

    seg_count = len(points_list) // 2
    for i in range(seg_count):
        a = points_list[2 * i]
        b = points_list[2 * i + 1]

        # 4 corners: (A, +1), (A, -1), (B, +1), (B, -1)
        for corner_end, corner_side in ((0.0, 1.0), (0.0, -1.0), (1.0, 1.0), (1.0, -1.0)):
            seg_a.append(a)
            seg_b.append(b)
            end_flag.append(corner_end)
            side.append(corner_side)

        o = i * 4
        indices.append((o + 0, o + 1, o + 2))
        indices.append((o + 2, o + 1, o + 3))

    # All geometry arrays are numpy (task 1: every point/attr passed to the batch is numpy).
    return (
        np.asarray(seg_a, dtype=np.float32),
        np.asarray(seg_b, dtype=np.float32),
        np.asarray(side, dtype=np.float32),
        np.asarray(end_flag, dtype=np.float32),
        np.asarray(indices, dtype=np.uint32),
    )



# --------------------------------------------------------------
# Shader Implementation

@dataclass
class Polyline_Dash_Shader(Shader_Instance):

    # Frame-varying draw parameters (all self-managed; set via the public setters below).
    _thickness: float = field(init=False, default=6.0)      # in pixels
    _dash_width: float = field(init=False, default=20.0)    # dash period in pixels
    _dash_ratio: float = field(init=False, default=0.5)     # lit fraction of each period (0..1)
    _phase: float = field(init=False, default=0.0)
    _color: Any = field(init=False, default=(1.0, 1.0, 1.0, 1.0))
    _color2: Any = field(init=False, default=(0.0, 0.0, 0.0, 0.0))

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_polyline(self, value: list) -> None:
        """Set the polyline geometry as a flat list of segment endpoint PAIRS.

        Stored as a numpy float32 array (task 1) so every point handled by this shader — and
        every array passed to batch_for_shader — is numpy. Animatable via `_points`.
        """
        self._points = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True

    def set_phase(self, value: float) -> None:
        """Dash scroll phase, hard-capped to 0.0 - 1.0 (task 2)."""
        self._phase = min(1.0, max(0.0, float(value)))

    def set_line_thickness(self, value: float) -> None:
        self._thickness = float(value)

    def set_dash_width(self, value: float) -> None:
        self._dash_width = max(1.0, float(value))

    def set_dash_ratio(self, value: float) -> None:
        self._dash_ratio = min(1.0, max(0.0, float(value)))

    def set_dash_colors(self, color, color2=(0.0, 0.0, 0.0, 0.0)) -> None:
        """Lit-dash color and (optional) gap color. A gap alpha of 0 discards the gap."""
        self._color = tuple(color)
        self._color2 = tuple(color2)

    # ----------------------------------------------------------
    # Private API, overriding parent class funcs

    def _shader_init(self):

        vert_out = gpu.types.GPUStageInterfaceInfo("dash_interface")
        vert_out.no_perspective("VEC2", "stipple_co")
        vert_out.flat("VEC2", "stipple_start")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "seg_a")
        shader_info.vertex_in(1, "VEC3", "seg_b")
        shader_info.vertex_in(2, "FLOAT", "side")
        shader_info.vertex_in(3, "FLOAT", "end_flag")

        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC2", "viewport_size")
        shader_info.push_constant("FLOAT", "line_thickness")
        shader_info.push_constant("FLOAT", "dash_width")
        shader_info.push_constant("FLOAT", "udash_factor")
        shader_info.push_constant("FLOAT", "phase")
        shader_info.push_constant("INT", "colors_len")
        shader_info.push_constant("VEC4", "color")
        shader_info.push_constant("VEC4", "color2")

        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(vertex_source)
        shader_info.fragment_source(fragment_source)

        self.shader_actual = gpu.shader.create_from_info(shader_info)

    def _shader_update_batch(self):
        """Rebuild the GPU batch (quad geometry) from the polyline point pairs."""
        if self._points is None or len(self._points) < 2:
            self._needs_new_batch = False
            self._batch = None
            return

        seg_a, seg_b, side, end_flag, indices = _make_polyline_verts(self._points)

        self._batch = batch_for_shader(
            self.shader_actual,
            self.shader_type,  # TRIS
            {"seg_a": seg_a, "seg_b": seg_b, "side": side, "end_flag": end_flag},
            indices=indices,
        )
        self._needs_new_batch = False

    def _shader_draw(self):

        region = bpy.context.region
        viewport_size = (float(region.width), float(region.height)) if region else (1.0, 1.0)

        # Set self-managed uniforms (change with viewport / user parameters).
        self.set_uniform("ModelViewProjectionMatrix", bpy.context.region_data.perspective_matrix.copy())
        self.set_uniform("viewport_size", viewport_size)
        self.set_uniform("line_thickness", self._thickness)
        self.set_uniform("dash_width", self._dash_width)
        self.set_uniform("udash_factor", self._dash_ratio)
        self.set_uniform("phase", self._phase)
        # colors_len > 0 tells the fragment shader to draw the gap in color2 rather than discard.
        self.set_uniform("colors_len", 1 if self._color2[3] > 0.0 else 0)
        self.set_uniform("color", self._color)
        self.set_uniform("color2", self._color2)

        gpu.state.blend_set('ALPHA')

        super()._shader_draw()
