

def draw_simple_box(context, shader_wrapper):
    
    if shader_wrapper is None:
        raise Exception("Shader wrapper is null")
    
    """The 'Paint' phase of your Flexbox system"""
    # 1. Layout Phase: Calculate center (Simulating a simple Flexbox 'justify: center')
    region = context.region
    width = region.width
    height = region.height
    
    size = 20
    center_x = width / 2
    center_y = height / 2
    
    # 2. Define vertices for a square centered at (center_x, center_y)
    # Counter-clockwise: bottom-left, bottom-right, top-right, top-left
    vertices = (
        (center_x - size/2, center_y - size/2),
        (center_x + size/2, center_y - size/2),
        (center_x + size/2, center_y + size/2),
        (center_x - size/2, center_y + size/2),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    
    # In this simple example, the batch is updated every draw call. 
    # It is a high-cost operatation, so it's suboptimal to update if changes are need made. Later examples will introduce a caching system
    shader_wrapper.set_indices(indices)
    shader_wrapper.set_points(vertices)
    
    # Uniforms can be updated every draw call for low cost
    shader_wrapper.set_uniform(name = "color", value = (1.0, 0.0, 0.0, 1.0))
    shader_wrapper.draw()

    # # 3. GPU State Setup
    # shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    # batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    
    # shader.bind()
    # shader.uniform_float("color", (1.0, 0.0, 0.0, 1.0)) # Pure Red
    
    # gpu.state.blend_set('ALPHA')
    # batch.draw(shader)
    # gpu.state.blend_set('NONE')
