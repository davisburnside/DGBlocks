"""
Custom Shader_Instance subclass: a smooth-color POLYLINE with viewport_z_boost
and screen-space arrowheads.

WHY THIS EXISTS
---------------
The dashed polyline shader (Polyline_Dash_Shader) proves that Blender's POLYLINE
quad-expansion technique gives real, Metal-safe line thickness. This shader extends
that technique with three features:

1. SMOOTH_COLOR — per-vertex colors interpolated across each segment quad, so
   you can tint individual points along a line (e.g. gradient wireframes).

2. viewport_z_boost — a uniform float added to clip-space Z so overlapping
   lines / mesh edges don't z-fight. Positive values push lines toward the
   viewer (draw over the mesh); negative values push back. No new batches or
   shader instances are needed — it's a single push constant.

3. Arrowheads — when arrow_length_px > 0, the end of every polyline cluster
   sprouts two short arrow lines at ±arrow_angle from the backward tangent.
   The arrow geometry is generated on the CPU (inside _make_polyline_verts)
   but uses the SAME seg_a/seg_b vertex attributes as the parent segment —
   no new "shader points" in the user's point list. The vertex shader computes
   the screen-space direction (so arrows always face the viewport and never
   skew when the camera moves) and derives the two arrow directions by
   rotating the backward tangent by ±arrow_angle. The arrow adopts the color
   of the cluster's final point.

INDEPENDENCE
------------
All GPU logic lives here. Controlling code only ever calls the small public setters
below and never touches uniforms or GLSL. MVP + viewport uniforms are self-managed
in _shader_draw().

Setup: 'shader_uid' is the only Shader_Declaration value you control. The rest must match:
Shader_Declaration(
    shader_uid="MY_ANNOTATED_LINES",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=Polyline_Annotated_Shader,
)

Geometry input (set_polyline_clusters) is a list of clusters, each a list of
world-space (x, y, z) points where consecutive points form a segment:

    shader.set_polyline_clusters([
        [(0,0,0), (1,0,0), (1,1,0)],    # cluster 0 — 2 segments
        [(2,2,2), (3,3,3)],             # cluster 1 — 1 segment
    ])

Per-point colors (set_colors or via set_polyline_clusters) are one RGBA tuple
per input point. They are expanded to per-vertex (per-quad-corner) colors in
_make_polyline_verts so the GPU interpolates smoothly across each segment.
"""

from dataclasses import dataclass, field
from typing import Any
import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

# --------------------------------------------------------------
# Intra-block imports
from ....native_blocks.block_onscreen_drawing.data_structures import Shader_Instance
from ..helpers import set_draw_geometry_occluded
from .polyline_geometry_utils import SEGMENT_CORNERS, segment_quad_indices

# --------------------------------------------------------------
# Shader Constants

# Every vertex carries BOTH endpoints of its segment (seg_a, seg_b) so the
# vertex shader can compute a consistent screen-space direction.
# Additional per-vertex attributes drive the annotated features:
#   vcol      – per-vertex RGBA color (smoothly interpolated)
#   side      – +1 / -1 (which side of the line this corner offsets to)
#   end_flag  – 0.0 or 1.0 (which endpoint this corner is based on)
#   is_arrow  – 0.0 = main segment quad, 1.0 = arrowhead quad
#   branch    – +1 / -1 (which arrow branch: left / right of backward tangent)
vertex_source = """
void main()
{
    vec4 a_clip = ModelViewProjectionMatrix * vec4(seg_a, 1.0);
    vec4 b_clip = ModelViewProjectionMatrix * vec4(seg_b, 1.0);

    vec2 half_vp = 0.5 * viewport_size;
    vec2 a_scr = (a_clip.xy / a_clip.w) * half_vp;
    vec2 b_scr = (b_clip.xy / b_clip.w) * half_vp;

    // Screen-space segment direction (forward, from A to B).
    vec2 seg_dir = b_scr - a_scr;
    float seg_len = length(seg_dir);
    seg_dir = (seg_len > 0.0) ? seg_dir / seg_len : vec2(1.0, 0.0);

    vec2 along_dir;    // direction along the line element (for positioning)
    vec2 perp_dir;     // perpendicular to along_dir (for thickness)
    float along_len;   // how far along_dir to offset (pixels in screen space)

    if (is_arrow > 0.5) {
        // Arrowhead line: rotate the *backward* tangent by branch * arrow_angle
        // so the two arrow lines splay from the tip at ±arrow_angle.
        vec2 backward = -seg_dir;
        float angle  = branch * radians(arrow_angle);
        float ca = cos(angle);
        float sa = sin(angle);
        along_dir = vec2(backward.x * ca - backward.y * sa,
                         backward.x * sa + backward.y * ca);
        perp_dir  = vec2(-along_dir.y, along_dir.x);
        along_len = arrow_length_px * end_flag;  // 0 at tip, arrow_length at point
    } else {
        // Main segment: offset is purely perpendicular (no along displacement).
        along_dir = seg_dir;   // unused (along_len == 0)
        perp_dir  = vec2(-seg_dir.y, seg_dir.x);
        along_len = 0.0;
    }

    // Base clip-space position:
    //   main segment  → A or B depending on end_flag
    //   arrow         → always B (the tip / last point of the cluster)
    vec4 base_clip = b_clip;
    if (is_arrow < 0.5) {
        base_clip = (end_flag < 0.5) ? a_clip : b_clip;
    }

    // Total pixel-space offset: along the line element + perpendicular thickness.
    vec2 offset_px  = along_dir * along_len + perp_dir * side * (line_thickness * 0.5);
    vec2 offset_ndc = offset_px / half_vp;

    gl_Position = base_clip;
    gl_Position.xy += offset_ndc * base_clip.w;

    // viewport_z_boost: nudge depth so overlapping lines / mesh edges
    // don't z-fight. Positive → toward viewer, negative → away.
    gl_Position.z -= viewport_z_boost * base_clip.w;

    color = vcol;
}
"""

fragment_source = """
void main()
{
    fragColor = color;
}
"""


# --------------------------------------------------------------
# Geometry expansion helper

def _make_annotated_verts(points, colors, cluster_sizes, arrow_length_px):
    """
    Expand a list of polyline clusters into quad geometry (with optional
    arrowheads) ready for batch_for_shader.

    Each input cluster is a contiguous run of points in *points*; consecutive
    points within a cluster form connected line segments. For every segment
    we emit 4 quad corners (2 triangles) using the shared SEGMENT_CORNERS
    pattern. For the last segment of each cluster, when arrow_length_px > 0,
    we additionally emit 2 arrow-line quads (one per branch), each derived
    from the same seg_a / seg_b attributes — so no new “shader points” are
    introduced.

    Parameters
    ----------
    points         : np.ndarray (N, 3) float32 — all cluster points flattened
    colors         : np.ndarray (N, 4) float32 — one RGBA color per point
    cluster_sizes  : np.ndarray (C,) int32   — number of points per cluster
    arrow_length_px: float                      — 0 disables arrow generation

    Returns
    -------
    (pos_a, pos_b, vcol, side, end_flag, is_arrow, branch, indices)
    """
    pos_a     = []
    pos_b     = []
    vcol      = []
    side_arr  = []
    end_flag  = []
    is_arrow  = []
    branch    = []
    indices   = []

    vertex_count = 0
    pt_idx       = 0

    for c_size in cluster_sizes:
        c_size = int(c_size)
        if c_size < 2:
            pt_idx += c_size
            continue

        n_segs = c_size - 1

        for seg_i in range(n_segs):
            a = points[pt_idx + seg_i]
            b = points[pt_idx + seg_i + 1]
            col_a = colors[pt_idx + seg_i]
            col_b = colors[pt_idx + seg_i + 1]

            is_last_seg = (seg_i == n_segs - 1)

            # --- 4 quad corners for the segment ---
            for corner_end, corner_side in SEGMENT_CORNERS:
                pos_a.append(a)
                pos_b.append(b)
                vcol.append(col_a if corner_end < 0.5 else col_b)
                end_flag.append(corner_end)
                side_arr.append(corner_side)
                is_arrow.append(0.0)
                branch.append(0.0)

            indices.extend(segment_quad_indices(vertex_count))
            vertex_count += 4

            # --- 2 arrow-line quads for the last segment of each cluster ---
            if is_last_seg and arrow_length_px > 0.0:
                tip_color = col_b  # adopts final point's color
                for branch_sign in (1.0, -1.0):
                    for corner_end, corner_side in SEGMENT_CORNERS:
                        pos_a.append(a)
                        pos_b.append(b)
                        vcol.append(tip_color)
                        end_flag.append(corner_end)
                        side_arr.append(corner_side)
                        is_arrow.append(1.0)
                        branch.append(branch_sign)
                    indices.extend(segment_quad_indices(vertex_count))
                    vertex_count += 4

        pt_idx += c_size

    return (
        np.asarray(pos_a,     dtype=np.float32),
        np.asarray(pos_b,     dtype=np.float32),
        np.asarray(vcol,      dtype=np.float32),
        np.asarray(side_arr,  dtype=np.float32),
        np.asarray(end_flag,  dtype=np.float32),
        np.asarray(is_arrow,  dtype=np.float32),
        np.asarray(branch,   dtype=np.float32),
        np.asarray(indices,   dtype=np.uint32),
    )


# --------------------------------------------------------------
# Shader Implementation

@dataclass
class Polyline_Annotated_Shader(Shader_Instance):
    """
    A smooth-color, Metal-safe polyline shader with viewport z-boost and
    screen-space arrowheads.

    Geometry is supplied as a list of clusters via set_polyline_clusters().
    Each cluster is a connected series of points (consecutive points form
    segments). Per-point RGBA colors enable smooth interpolation along each
    segment.

    When arrow_length_px > 0, the final segment of each cluster grows two
    short arrow lines at ±arrow_angle from the backward tangent, facing the
    viewport.
    """

    # Frame-varying draw parameters (all self-managed; set via public setters).
    # A value of 0.0 for _line_thickness falls back to gpu.state.line_width_get()
    # in _shader_draw(), so the shader respects gpu.state.line_width_set().
    _line_thickness:   float = field(init=False, default=0.0)
    _viewport_z_boost: float = field(init=False, default=0.0)
    _arrow_length_px:  float = field(init=False, default=0.0)
    _arrow_angle:      float = field(init=False, default=45.0)  # degrees

    # Cluster boundary info — not animatable, stays constant during point
    # animation (same shape, different positions).
    _cluster_sizes:    Any = field(init=False, default=None)

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_polyline_clusters(self, clusters_points: list, clusters_colors=None) -> None:
        """
        Set polyline geometry organised by cluster.

        Args:
            clusters_points: list of clusters; each cluster is a list of
                              (x, y, z) world-space points. Consecutive points
                              form connected line segments.
            clusters_colors: optional list of clusters; each cluster is a list
                              of (r, g, b, a) tuples, one per point. If omitted,
                              all points default to opaque white.
        """
        flat_points = []
        flat_colors = []
        cluster_sizes = []

        for ci, cluster in enumerate(clusters_points):
            cluster_sizes.append(len(cluster))
            flat_points.extend(cluster)
            if clusters_colors is not None and ci < len(clusters_colors):
                flat_colors.extend(clusters_colors[ci])
            else:
                flat_colors.extend([(1.0, 1.0, 1.0, 1.0)] * len(cluster))

        self._points = np.asarray(flat_points, dtype=np.float32)
        self._colors = np.asarray(flat_colors, dtype=np.float32)
        self._cluster_sizes = np.asarray(cluster_sizes, dtype=np.int32)
        self._needs_new_batch = True

    def set_line_thickness(self, value: float) -> None:
        """Line thickness in pixels (Metal-safe via quad expansion)."""
        self._line_thickness = float(value)

    def set_viewport_z_boost(self, value: float) -> None:
        """
        Nudge factor for clip-space Z. Positive → toward viewer (draws over
        mesh / other lines); negative → away. Applied uniformly to all
        vertices via a single push constant — no new batches needed.
        """
        self._viewport_z_boost = float(value)

    def set_arrow_length_px(self, value: float) -> None:
        """
        Arrowhead length in window pixels. <= 0 disables arrowheads entirely
        (lines render as normal lines). When animated as a batch attribute,
        crossing zero causes arrows to appear/disappear.
        """
        self._arrow_length_px = float(value)

    def set_arrow_angle(self, value: float) -> None:
        """
        Arrow half-angle in degrees. The two arrow lines branch from the
        backward tangent at ±this angle.
        """
        self._arrow_angle = float(value)

    # ----------------------------------------------------------
    # Private API, overriding parent class funcs

    def _shader_init(self):
        vert_out = gpu.types.GPUStageInterfaceInfo("annotated_polyline_interface")
        vert_out.smooth("VEC4", "color")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "seg_a")
        shader_info.vertex_in(1, "VEC3", "seg_b")
        shader_info.vertex_in(2, "VEC4", "vcol")
        shader_info.vertex_in(3, "FLOAT", "side")
        shader_info.vertex_in(4, "FLOAT", "end_flag")
        shader_info.vertex_in(5, "FLOAT", "is_arrow")
        shader_info.vertex_in(6, "FLOAT", "branch")

        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC2", "viewport_size")
        shader_info.push_constant("FLOAT", "line_thickness")
        shader_info.push_constant("FLOAT", "viewport_z_boost")
        shader_info.push_constant("FLOAT", "arrow_length_px")
        shader_info.push_constant("FLOAT", "arrow_angle")

        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(vertex_source)
        shader_info.fragment_source(fragment_source)

        self.shader_actual = gpu.shader.create_from_info(shader_info)

    def _shader_update_batch(self):
        """Rebuild the GPU batch from the polyline cluster data."""
        if self._points is None or len(self._points) == 0 or self._cluster_sizes is None:
            self._needs_new_batch = False
            self._batch = None
            return

        (pos_a, pos_b, vcol, side, end_flag, is_arrow, branch, indices) = \
            _make_annotated_verts(
                self._points,
                self._colors,
                self._cluster_sizes,
                self._arrow_length_px,
            )

        self._batch = batch_for_shader(
            self.shader_actual,
            self.shader_type,   # TRIS
            {
                "seg_a": pos_a, 
                "seg_b": pos_b,
                "vcol":  vcol,
                "side":  side,
                "end_flag": end_flag,
                "is_arrow": is_arrow,
                "branch": branch,
            },
            indices=indices,
        )
        self._needs_new_batch = False

    def _shader_draw(self):
        # --- viewport uniforms ---
        region = bpy.context.region
        viewport_size = (float(region.width), float(region.height)) if region else (1.0, 1.0)

        # Respects gpu.state.line_width_set: read the current GL line width and
        # use it as the default thickness. _line_thickness (if > 0) overrides.
        gpu_line_width = gpu.state.line_width_get()
        thickness = self._line_thickness if self._line_thickness > 0.0 else max(1.0, gpu_line_width)

        self.set_uniform("ModelViewProjectionMatrix", bpy.context.region_data.perspective_matrix.copy())
        self.set_uniform("viewport_size", viewport_size)
        self.set_uniform("line_thickness", thickness)
        self.set_uniform("viewport_z_boost", self._viewport_z_boost)
        self.set_uniform("arrow_length_px", self._arrow_length_px)
        self.set_uniform("arrow_angle", self._arrow_angle)

        # Depth testing so viewport_z_boost can resolve z-fighting with the mesh
        # and between overlapping lines. Blend for alpha transparency.
        set_draw_geometry_occluded()
        gpu.state.blend_set('ALPHA')

        super()._shader_draw()
