def make_dotted_line_shader(self):
        
        # This was sourced from user "X Y" on stackoverflow
        #https://blender.stackexchange.com/questions/327274/how-to-draw-consistent-dotted-line-similar-to-default-blender-measure-tool
        
        vert_out = gpu.types.GPUStageInterfaceInfo("my_interface")
        vert_out.no_perspective("VEC2", "stipple_start")
        vert_out.flat("VEC2", "stipple_pos")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, "VEC3", "pos")

        shader_info.push_constant("MAT4", "ModelMatrix")
        shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
        shader_info.push_constant("VEC2", "viewport_size")
        shader_info.push_constant("FLOAT", "dash_width")
        shader_info.push_constant("FLOAT", "udash_factor")
        shader_info.push_constant("INT", "colors_len")
        shader_info.push_constant("VEC4", "color")
        shader_info.push_constant("VEC4", "color2")
        shader_info.push_constant("FLOAT", "phase")
        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, "VEC4", "fragColor")

        # https://github.com/blender/blender/blob/blender-v4.3-release/source/blender/gpu/shaders/gpu_shader_3D_line_dashed_uniform_color_vert.glsl
        shader_info.vertex_source("""
        void main()
        {
        vec4 pos_4d = vec4(pos, 1.0);
        gl_Position = ModelViewProjectionMatrix * pos_4d;
        stipple_start = stipple_pos = viewport_size * 0.5 * (gl_Position.xy / gl_Position.w);
        }
        """)

        # https://github.com/blender/blender/blob/blender-v4.3-release/source/blender/gpu/shaders/gpu_shader_2D_line_dashed_frag.glsl
        shader_info.fragment_source("""
        void main()
        {
            float distance_along_line = distance(stipple_pos, stipple_start) + (phase * dash_width);
            /* Solid line case, simple. */
            if (udash_factor >= 1.0f) {
                fragColor = color;
            }
            /* Actually dashed line... */
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
        """)

        shader = gpu.shader.create_from_info(shader_info)
        del vert_out
        del shader_info
        
        return shader