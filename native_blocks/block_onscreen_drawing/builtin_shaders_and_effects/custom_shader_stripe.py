"""

Custom Shader_Instance subclass: a "holdout" alternating-stripe pattern.

WHY THIS EXISTS
---------------
Unlike the other example shaders, this one draws its geometry at ARBITRARY 3D points in the
viewport (a normal ModelViewProjectionMatrix pass), but the alternating stripe pattern is
computed ENTIRELY from each fragment's WINDOW-SPACE pixel coordinate (gl_FragCoord.xy) — never
from its 3D position or UV. The result is a static, screen-locked 2D stripe pattern: no matter
where a TRI sits in 3D, and no matter how the camera orbits it, the stripes stay glued to the
window and slide across the geometry. That is the intentionally "glitchy" holdout effect.

INDEPENDENCE
------------
All GPU logic lives here. Controlling code only ever calls the small public setters below
(set_points / set_indices / set_stripe_angle / set_stripe_width / set_stripe_colors) and never
touches uniforms or GLSL. MVP uniform is self-managed in _shader_draw().

Setup: 'shader_uid' is the only Shader_Declaration value you control. The rest must match:
Shader_Declaration(
    shader_uid="MY_STRIPE",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=Stripe_Shader,
)

Geometry input (set_points) is world-space (x, y, z) triangle vertices; pass an optional index
array via set_indices for shared vertices. Every point/attr passed to the batch is numpy.
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

vertex_source = """
void main()
{
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
}
"""

fragment_source = """
void main()
{
    // Window-space pixel coordinate. gl_FragCoord is independent of the fragment's 3D
    // position, which is exactly what makes this a screen-locked "holdout" pattern.
    vec2 p = gl_FragCoord.xy;

    // Stripe direction from the user angle (radians), in window space.
    vec2 dir = vec2(cos(stripe_angle), sin(stripe_angle));

    // Alternate the stripe color across each shared-width band. fract(dot/width) runs
    // 0..1 across every period; one half of each period is color_a, the other color_b.
    // `phase` scrolls (shifts) the bands along the stripe direction.
    float band = fract((dot(p, dir) / stripe_width) + phase);

    fragColor = (band < 0.5) ? color_a : color_b;
}
"""


@dataclass
class Stripe_Shader(Shader_Instance):

    # Frame-varying draw parameters (all self-managed; set via the public setters below).
    _stripe_angle: float = field(init=False, default=0.0)      # radians
    _stripe_width: float = field(init=False, default=40.0)     # window pixels
    _phase: float = field(init=False, default=0.0)             # 0..1 band scroll offset
    _color_a: Any = field(init=False, default=(1.0, 0.0, 1.0, 1.0))
    _color_b: Any = field(init=False, default=(0.0, 1.0, 1.0, 1.0))

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_stripe_angle(self, value: float) -> None:
        """Stripe direction in RADIANS (0 = vertical bands)."""
        self._stripe_angle = float(value)

    def set_stripe_width(self, value: float) -> None:
        """Shared band width in window pixels (each stripe = half a period)."""
        self._stripe_width = max(1.0, float(value))

    def set_phase(self, value: float) -> None:
        """Stripe scroll phase along the stripe direction, hard-capped to 0.0 - 1.0."""
        self._phase = min(1.0, max(0.0, float(value)))

    def set_stripe_colors(self, color_a, color_b=(0.0, 0.0, 0.0, 0.0)) -> None:
        """The two alternating stripe colors (RGBA)."""
        self._color_a = tuple(color_a)
        self._color_b = tuple(color_b)

    # ----------------------------------------------------------
    # Private API, overriding parent class funcs

    def _shader_init(self):
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "pos")

        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("FLOAT", "stripe_angle")
        shader_info.push_constant("FLOAT", "stripe_width")
        shader_info.push_constant("VEC4", "color_a")
        shader_info.push_constant("VEC4", "color_b")
        shader_info.push_constant("FLOAT", "phase")

        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(vertex_source)
        shader_info.fragment_source(fragment_source)

        self.shader_actual = gpu.shader.create_from_info(shader_info)

    def _shader_update_batch(self):
        """Rebuild the GPU batch from the (indexed) triangle geometry.

        Overridden because the base Shader_Instance._shader_update_batch does NOT pass the
        index array to batch_for_shader. set_indices() always feeds this shader's cube TRIs.
        """
        if self._points is None or len(self._points) == 0:
            self._needs_new_batch = False
            return

        self._batch = batch_for_shader(
            self.shader_actual,
            self.shader_type,
            {"pos": self._points},
            indices=self._indices,
        )
        self._needs_new_batch = False

    def _shader_draw(self):
        # Set self-managed uniforms (change with viewport / user parameters).
        self.set_uniform(
            "ModelViewProjectionMatrix",
            bpy.context.region_data.perspective_matrix.copy(),
        )
        self.set_uniform("stripe_angle", self._stripe_angle)
        self.set_uniform("stripe_width", self._stripe_width)
        self.set_uniform("color_a", self._color_a)
        self.set_uniform("color_b", self._color_b)
        self.set_uniform("phase", self._phase)

        gpu.state.blend_set('ALPHA')

        super()._shader_draw()
