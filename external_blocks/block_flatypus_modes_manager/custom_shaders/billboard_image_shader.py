import bpy
import gpu 
from ....blocks_natively_included.block_onscreen_drawing.feature_shader import Shader_Instance

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

class Billboard_Shader(Shader_Instance):

    image_name: str
        
    def __post_init__(self):

        super().__post_init__()  # Runs Shader_Instance's __post_init__

        # Validate Image & create texture from it
        image_base = bpy.data.images.get(self.image_name)
        if image_base is None:
            raise Exception(f"Image missing from .blend file: {self.image_name}")
        icon_texture = gpu.texture.from_image(image_base)
        self._texture = icon_texture

        # Define Shader inputs & outputs
        vert_out = gpu.types.GPUStageInterfaceInfo("icon_interface")
        vert_out.smooth("VEC2", "uvCoord")
        vert_out.flat("VEC4", "instance_color")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "pos")  # Center position
        shader_info.vertex_in(1, "VEC2", "uv")   # UV coordinates for quad
        shader_info.vertex_in(2, "VEC4", "color") # Per-instance color
        shader_info.vertex_in(3, "FLOAT", "size") # Per-instance size

        shader_info.push_constant("MAT4", "ViewMatrix")
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("FLOAT", "offset_distance")  # NEW: offset parameter

        shader_info.sampler(0, "FLOAT_2D", "icon_texture")

        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        shader_info.vertex_source(vertex_source)
        shader_info.fragment_source(fragment_source)

        # del vert_out
        # del shader_info
        self._shader_actual  = gpu.shader.create_from_info(shader_info)
