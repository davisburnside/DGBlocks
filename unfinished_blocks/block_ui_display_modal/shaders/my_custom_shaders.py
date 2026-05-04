import gpu

def create_grid_tri_shader():
    
    vert_out = gpu.types.GPUStageInterfaceInfo("grid_interface")
    vert_out.smooth("VEC3", "worldPosition")
    vert_out.smooth("VEC3", "worldNormal")
    vert_out.flat("VEC3", "triangleCenter")  # Use flat interpolation
    
    # Create shader info
    shader_info = gpu.types.GPUShaderCreateInfo()
    
    # Define vertex inputs
    shader_info.vertex_in(0, "VEC3", "position")
    shader_info.vertex_in(1, "VEC3", "normal")
    shader_info.vertex_in(2, "VEC3", "center")  # Add center as vertex attribute
    
    # Define uniforms/push constants
    shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
    shader_info.push_constant("FLOAT", "gridSize")
    shader_info.push_constant("FLOAT", "lineThickness")
    shader_info.push_constant("FLOAT", "fadeStrength")
    shader_info.push_constant("FLOAT", "fadeDistance")
    
    # Define the UBO block in the shader
    shader_info.typedef_source("struct ColorData { vec4 patternColor; vec4 backgroundColor; };")
    shader_info.uniform_buf(0, "ColorData", "colorBlock")
    
    # Set interface between vertex and fragment shaders
    shader_info.vertex_out(vert_out)
    
    # Define fragment shader output
    shader_info.fragment_out(0, "VEC4", "fragColor")
    
    # Vertex shader source
    shader_info.vertex_source("""
    void main()
    {
        gl_Position = ModelViewProjectionMatrix * vec4(position, 1.0);
        worldPosition = position;
        worldNormal = normal;
        triangleCenter = center;  // Pass through center (will be flat-interpolated)
    }
    """)
    
    # Fragment shader (same as before)
    shader_info.fragment_source("""
    void main()
    {
        // Calculate tangent space for consistent grid orientation
        vec3 normal = normalize(worldNormal);
        
        // Create a consistent tangent space
        vec3 tangent;
        vec3 bitangent;
        
        // Find least-aligned global axis to use for tangent calculation
        if (abs(normal.x) < abs(normal.y) && abs(normal.x) < abs(normal.z)) {
            tangent = normalize(cross(vec3(1.0, 0.0, 0.0), normal));
        } else if (abs(normal.y) < abs(normal.z)) {
            tangent = normalize(cross(vec3(0.0, 1.0, 0.0), normal));
        } else {
            tangent = normalize(cross(vec3(0.0, 0.0, 1.0), normal));
        }
        
        bitangent = normalize(cross(normal, tangent));
        
        // Project world position onto the tangent plane
        vec2 uv;
        uv.x = dot(worldPosition, tangent);
        uv.y = dot(worldPosition, bitangent);
        
        // Apply grid size for precise measurement
        uv = uv / gridSize;
        
        // Apply a half-cell offset to align with world grid
        uv = uv + 0.5;
        
        // Create uniform square grid pattern
        vec2 grid = abs(fract(uv) - 0.5);
        float line = min(grid.x, grid.y);
        
        // Use lineThickness to control the smoothstep transition
        float gridIntensity = 1.0 - smoothstep(0.0, lineThickness, line);
        
        // Mix between pattern color and background color
        vec4 baseColor = mix(colorBlock.backgroundColor, colorBlock.patternColor, gridIntensity);
        
        // Calculate radial fade from triangle center
        float distFromCenter = length(worldPosition - triangleCenter);
        
        // Create fade based on distance
        float fade = 1.0 - smoothstep(0.0, fadeDistance, distFromCenter);
        
        // Apply fade strength
        fade = mix(1.0, fade, fadeStrength);
        
        // Apply fade to alpha channel
        fragColor = vec4(baseColor.rgb, baseColor.a * fade);
    }
    """)
    
    # Create the shader from info
    shader = gpu.shader.create_from_info(shader_info)
    
    # Clean up
    del vert_out
    del shader_info
    
    return shader
