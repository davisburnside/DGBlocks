"""

Custom Shader_Instance subclass for camera-facing image billboards.

Usage (called in the ON operator after set_state):
    shader.set_points([(x, y, z), ...])   — world-space centre positions
    shader.set_colors([(r, g, b, a), ...]) — per-billboard tint
    shader.set_billboard_sizes([size_float, ...])    — billboard world-space size

draw() is overridden to build quad geometry, set MVP uniforms from bpy.context.region_data, and draw — no external callback needed.

Setup: 'shader_uid' and 'custom_shader_kwargs' are the only Shader_Declaration values you control. The other must match below:
Shader_Declaration(
    shader_uid="BILLBOARD",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=Billboard_Shader,
    custom_shader_kwargs={"image_name": "img"},
)
    
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
from ....native_blocks.block_onscreen_drawing.helpers import set_draw_geometry_occluded

# --------------------------------------------------------------
# Shader Constants

vertex_source = """
void main()
{
    // Extract camera right and up vectors from view matrix
    vec3 camera_right = vec3(ViewMatrix[0][0], ViewMatrix[1][0], ViewMatrix[2][0]);
    vec3 camera_up = vec3(ViewMatrix[0][1], ViewMatrix[1][1], ViewMatrix[2][1]);
    
    // Get the view direction (camera to point direction)
    vec4 view_space_center = ViewMatrix * vec4(pos, 1.0);
    vec3 view_dir = normalize(-view_space_center.xyz);
    
    // Transform view direction back to world space
    // Explicitly construct mat3 from mat4 for Metal compatibility
    mat3 inv_view_rot = transpose(mat3(
        ViewMatrix[0].xyz,
        ViewMatrix[1].xyz,
        ViewMatrix[2].xyz
    ));
    vec3 world_view_dir = inv_view_rot * view_dir;
    
    // Apply offset along the view direction in world space
    vec3 offset_pos = pos + world_view_dir * offset_distance;
    
    // Create billboard quad vertex position
    vec2 centered_uv = uv - vec2(0.5, 0.5);
    
    // Calculate world position of this quad vertex
    vec3 billboard_pos = offset_pos + 
                    camera_right * centered_uv.x * size + 
                    camera_up * centered_uv.y * size;
    
    gl_Position = ModelViewProjectionMatrix * vec4(billboard_pos, 1.0);
    
    uvCoord = uv;
    instance_color = color;
}
"""

fragment_source = """
void main()
{
    vec4 tex_color = texture(icon_texture, uvCoord);
    
    // Apply instance color tinting
    fragColor = tex_color * instance_color;
    
    // Discard fully transparent pixels
    if (fragColor.a < 0.01) {
        discard;
    }
}
"""

def _make_billboard_verts(points_list, colors_list, sizes_list):
    """Build quad vertices (2 tris per point) for billboard rendering."""
    quad_uvs = [
        (0.0, 0.0),  # Bottom-left
        (1.0, 0.0),  # Bottom-right
        (1.0, 1.0),  # Top-right
        (0.0, 1.0),  # Top-left
    ]
    quad_indices = [
        (0, 1, 2),  # First triangle
        (0, 2, 3),  # Second triangle
    ]

    all_vertices = []
    all_uvs = []
    all_colors = []
    all_sizes = []
    all_indices = []

    for i in range(len(points_list)):
        idx_offset = i * 4
        for _ in range(4):
            all_vertices.append(points_list[i])
            all_colors.append(colors_list[i])
            all_sizes.append(sizes_list[i])
        all_uvs.extend(quad_uvs)
        for tri in quad_indices:
            all_indices.append((
                idx_offset + tri[0],
                idx_offset + tri[1],
                idx_offset + tri[2],
            ))

    return all_vertices, all_uvs, all_colors, all_sizes, all_indices


# --------------------------------------------------------------
# Shader Implementation

@dataclass
class Billboard_Shader(Shader_Instance):

    image_name: str = field(default="")
    _sizes: Any = field(init=False, default=None)  # list[float], one per billboard point

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_billboard_sizes(self, value: list) -> None:
        """Set per-billboard world-space sizes (one float per point).

        Stored as a numpy float32 array (task 1) so it matches the numpy points/colors and can
        be animated via the `_sizes` batch attribute.
        """
        self._sizes = np.asarray(value, dtype=np.float32)
        self._needs_new_batch = True

    # ----------------------------------------------------------
    # Private API, Overriding parent class funcs

    def _shader_init(self):

        # Validate image & create GPU texture
        image_base = bpy.data.images.get(self.image_name)
        if image_base is None:
            raise Exception(
                f"Image '{self.image_name}' missing from .blend file. "
                f"Unable to create shader '{self.shader_uid}'"
            )
        self._texture = gpu.texture.from_image(image_base)

        # Define shader inputs / outputs
        vert_out = gpu.types.GPUStageInterfaceInfo("icon_interface")
        vert_out.smooth("VEC2", "uvCoord")
        vert_out.flat("VEC4", "instance_color")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "pos")    # centre position
        shader_info.vertex_in(1, "VEC2", "uv")     # quad UV coordinates
        shader_info.vertex_in(2, "VEC4", "color")  # per-instance tint
        shader_info.vertex_in(3, "FLOAT", "size")  # per-instance world size

        shader_info.push_constant("MAT4", "ViewMatrix")
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("FLOAT", "offset_distance")

        shader_info.sampler(0, "FLOAT_2D", "icon_texture")

        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(vertex_source)
        shader_info.fragment_source(fragment_source)

        self.shader_actual = gpu.shader.create_from_info(shader_info)

    def _shader_update_batch(self):
        """Rebuilds the GPU batch from numpy data"""
        
        (all_vertices,
        all_uvs,
        all_colors,
        all_sizes,
        all_indices) = _make_billboard_verts(self._points, self._colors, self._sizes)

        self._batch = batch_for_shader(
            self.shader_actual,
            self.shader_type,
            {"pos": all_vertices, "uv": all_uvs, "color": all_colors, "size": all_sizes},
            indices=all_indices,
        )

    def _shader_draw(self):

        set_draw_geometry_occluded()
    
        # Set Uniforms, which change with viewing angle 
        self.shader_actual.uniform_sampler("icon_texture", self._texture)
        self.set_uniform("ModelViewProjectionMatrix", bpy.context.region_data.perspective_matrix.copy())
        self.set_uniform("ViewMatrix",                bpy.context.region_data.view_matrix.copy())
        self.set_uniform("offset_distance",           0.01)

        # set_draw_geometry_occluded()
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        # gpu.state.depth_mask_set(True)

        # Invoke default shader draw
        super()._shader_draw()
