import os
import gpu # type: ignore
import bpy # type: ignore
from gpu_extras.batch import batch_for_shader # type: ignore
from mathutils import Vector, Matrix, Euler

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_tools import get_self_block_module, clear_console
from ...my_addon_config import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...native_blocks import block_core
from ...native_blocks.block_core.core_features.loggers import Core_Block_Loggers, get_logger
from ...native_blocks.block_core.core_features.hooks import Wrapper_Hooks
from ...native_blocks.block_core.core_features.control_plane import Wrapper_Block_Management
from ...native_blocks.block_core.core_features.runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

from ...native_blocks.block_onscreen_drawing.constants import Block_RTC_Members as Onscreen_Draw_Block_RTC_Members
from ...native_blocks.block_onscreen_drawing.feature_draw_handler_manager import Wrapper_Draw_Handlers

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Logger_Definitions, Block_RTC_Members, Assembly_Mode_Shader_Definitions

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-flatypus-assembly-mode" 
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core",
    "block-stable-modal",
    "block-onscreen-drawing"
] 

# ==============================================================================================================================
# vars
# ==============================================================================================================================

_default_modal_options_for_3dview_display = {
    "uid": "viewport_display",
    "label": "viewport_display",
    "timer_interval": 1.0 / 30.0,
    "includes_timer": True,
}
_default_modal_options_for_keymouse_input = {
    "uid": "keymouse_input",
    "label": "keymouse_input",
    "includes_timer": False,
}

# ==============================================================================================================================
# DOWNSTREAM HOOKS
# ==============================================================================================================================

def hook_modal_key_or_mouse_event(context: bpy.types.Context, event: bpy.types.Event, modal_instance: any):
    pass
    # print("subscriber mousekey")
    # print(modal_instance, event)

def hook_modal_timer_event(context: bpy.types.Context, event: bpy.types.Event, modal_instance: any):
    pass
    print("subscriber timer")
    # print(modal_instance, event)

def hook_draw_event(draw_handler_instance):
    
    print("Draw event from hook")
    return True


# ==============================================================================================================================
# Operators
# ==============================================================================================================================





def make_billboard_verts(points_list, colors_list, sizes_list):
    
    # Define quad vertices (2 triangles)
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
        idx_offset = i * 4  # 4 vertices per quad
        
        # Add the same position for all 4 vertices of this quad
        for _ in range(4):
            all_vertices.append(points_list[i])
            all_colors.append(colors_list[i])
            all_sizes.append(sizes_list[i])
        
        # Add UVs for this quad
        all_uvs.extend(quad_uvs)
        
        # Add indices for this quad's two triangles
        for tri in quad_indices:
            all_indices.append((
                idx_offset + tri[0],
                idx_offset + tri[1],
                idx_offset + tri[2]
            ))
            
    return all_vertices, all_uvs,  all_colors, all_sizes, all_indices

def draw_image_billboards(shader_wrapper, points_list, colors_list, sizes_list):
    
    icon_texture = shader_wrapper._texture
    (all_vertices, 
    all_uvs,  
    all_colors, 
    all_sizes, 
    all_indices) = make_billboard_verts(points_list, colors_list, sizes_list)
    
    # Enable blending for transparency
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_mask_set(False)
    
    custom_batch_attributes = {
        'pos': all_vertices,
        'uv': all_uvs,
        'color': all_colors,
        'size': all_sizes,
    }
    _batch = batch_for_shader(
        shader_wrapper.shader_actual,
        shader_wrapper.shader_type,
        custom_batch_attributes,
        indices = all_indices,
    )
    shader_wrapper.shader_actual.bind()
    custom_shader_uniforms = {
        "ModelViewProjectionMatrix": bpy.context.region_data.perspective_matrix.copy(),
        "ViewMatrix": bpy.context.region_data.view_matrix.copy(),
        "offset_distance": 0.01 # (positive = towards camera, negative = away)
    }
    shader_wrapper.shader_actual.uniform_sampler("icon_texture", icon_texture)
    for name, value in custom_shader_uniforms.items():
        shader_wrapper.set_uniform(name, value)
    _batch.draw(shader_wrapper.shader_actual)
    
    gpu.state.depth_mask_set(True)


def _my_draw_callback(draw_handler_instance):

    all_RTC_shaders = Wrapper_Runtime_Cache.get_cache(Onscreen_Draw_Block_RTC_Members.SHADERS)

    gpu.state.line_width_set(4)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')  # Assuming the next draw expects no blending; adjust as needed
    gpu.state.depth_mask_set(True)
    
    shader_name = Assembly_Mode_Shader_Definitions.LINES_T1.name
    shader_wrapper = all_RTC_shaders[shader_name]
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0), (0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    col = [(1.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0),
        (0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)]
    shader_wrapper.set_points(vertices)
    shader_wrapper.set_colors(col)
    shader_wrapper.draw()
    
    shader_name = Assembly_Mode_Shader_Definitions.BILLBOARD.name
    shader_wrapper = all_RTC_shaders[shader_name]
    points = [(0.0, 0.0, 0.0)]
    colors = [(0.0, 0.0, 1.0, 1)]
    sizes = [10]
    draw_image_billboards(shader_wrapper, points, colors, sizes)

class DGBLOCKS_OT_Toggle_Assembly_Mode(bpy.types.Operator):
    bl_idname = "dgblocks.toggle_assembly_mode"
    bl_label = "Toggle Assmbly Mode"
    bl_options = {"REGISTER"}

    test_action_1: bpy.props.StringProperty() # type: ignore 
    test_action_2: bpy.props.StringProperty() # type: ignore 
    
    # This operator can always be executed, even when add
    def execute(self, context):

        
        # modal_op_for_keymouse_input = Wrapper_Modals_Manager.create_instance(**_default_modal_options_for_keymouse_input)
        if self.test_action_1 == "POST_VIEW":
            
            draw_phase_name = "POST_VIEW"

            # (Defined by a different block) get the draw handler instance
            draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Onscreen_Draw_Block_RTC_Members.DRAW_PHASES)[draw_phase_name]
            
            should_enable = draw_handler_instance._generated_handle is None
            if should_enable:
                Wrapper_Draw_Handlers.enable_draw_handler(draw_phase_name, draw_callback = _my_draw_callback)
                for shader_enum in Assembly_Mode_Shader_Definitions:
                    Wrapper_Draw_Handlers.add_shader(draw_phase_name, shader_enum, "ASSY")
            else:
                Wrapper_Draw_Handlers.disable_draw_handler(draw_phase_name)

            


        for area in bpy.context.window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {"FINISHED"}

# ==============================================================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
# ==============================================================================================================================

class DGBLOCKS_PT_Assembly_Mode_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"DGBLOCKS_PT_Assembly_Mode_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0
    
    # @classmethod
    # def poll(cls, context):
    #     return Wrapper_Block_Management.is_block_enabled(_BLOCK_ID)

    def draw_header(self, context):

        ui_draw_block_panel_header(context, self.layout, "FLT-mode-debug", Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")

    def draw(self, context):
        
        layout = self.layout
        layout.operator("dgblocks.toggle_assembly_mode", text = "run 'em")
        op_t1 = layout.operator("dgblocks.toggle_assembly_mode", text = "test drawers").test_action_1 = "POST_VIEW"

# ==============================================================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_OT_Toggle_Assembly_Mode,
    DGBLOCKS_PT_Assembly_Mode_Panel,
]

def register_block():

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_logger_enums = Block_Logger_Definitions,
        block_RTC_member_enums = Block_RTC_Members
    )
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")
