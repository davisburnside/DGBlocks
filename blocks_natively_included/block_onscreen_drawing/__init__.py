

import bpy # type: ignore
from typing import Optional

#=================================================================================
# BLOCK DATA - A unique ID & list of Dependencies is required for every Block
#=================================================================================

# import blocks_ununsed.block_event_listeners as block_event_listeners
# _BLOCK_ID = "block-ui-display-modal"
# from ...blocks_natively_included._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
# from ...blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
# from ...blocks_natively_included._block_core.core_features.feature_logs import get_logger

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helper_funcs import get_self_block_module, is_bpy_ready
from ...my_addon_config import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import _block_core
from .._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from .._block_core.core_helpers.helper_uilayouts import uilayout_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_RTC_Members, Block_Logger_Definitions
from .feature_draw_handler_manager import Wrapper_Draw_Handlers, DGBLOCKS_PG_DrawHandler_Instance


#=================================================================================
# BLOCK DEFINITION
#=================================================================================

_BLOCK_ID = "block-onscreen-drawing"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core"
]

#=================================================================================
# CALLBACK HOOK FUNCTIONS 
#=================================================================================

def hook_post_register_init(context):
    
    return True




def _callback_sample_shader_toggle(self, context):

    if not is_bpy_ready():
        return
    
    print("-------------_callback_sample_shader_toggle------------")
    draw_handler_props = context.scene.onscreen_drawing_props
    if draw_handler_props.POST_PIXEL.is_enabled != self.is_sample_1_enabled:
        draw_handler_props.POST_PIXEL.is_enabled = True
        # if self.is_sample_1_enabled:
        #     Wrapper_Draw_Handlers.set_enabled("POST_PIXEL", True)
        # else:
        #     Wrapper_Draw_Handlers.set_enabled("POST_PIXEL", False)


class DGBLOCKS_PG_Debug_Sample_Shaders(bpy.types.PropertyGroup):
 
    is_sample_1_enabled: bpy.props.BoolProperty(update = _callback_sample_shader_toggle) # type: ignore
    is_sample_2_enabled: bpy.props.BoolProperty(update = _callback_sample_shader_toggle) # type: ignore

class DGBLOCKS_PG_Stable_Drawing_Props(bpy.types.PropertyGroup):

    POST_PIXEL: bpy.props.PointerProperty(type = DGBLOCKS_PG_DrawHandler_Instance, name = "POST_PIXEL") # type: ignore
    POST_VIEW:  bpy.props.PointerProperty(type = DGBLOCKS_PG_DrawHandler_Instance, name = "POST_VIEW") # type: ignore
 
    debug_sample_shaders: bpy.props.PointerProperty(type = DGBLOCKS_PG_Debug_Sample_Shaders) # type: ignore






class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label       = "Modal Stack"
    bl_idname      = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = addon_title

    def draw_header(self, context):

        uilayout_draw_block_panel_header(context, self.layout, _BLOCK_ID.lower(), Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")
        

    def draw(self, context):

        layout = self.layout
        drawing_props = context.scene.onscreen_drawing_props

        draw_handler_phases = [
            drawing_props.POST_PIXEL,
            drawing_props.POST_VIEW
        ]

        for phase in draw_handler_phases:
            split = layout.split()
            split.label(text = phase.name)
            layout.prop(phase, "is_enabled")
        

        box = layout.box()
        panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_onscreen_drawing", default_closed=True)
        panel_header.label(text = "All Blocks")
        if panel_body is not None:     
            panel_body.prop(drawing_props.debug_sample_shaders, "is_sample_1_enabled")
            panel_body.prop(drawing_props.debug_sample_shaders, "is_sample_2_enabled")


#=================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#=================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [    
    # DGBLOCKS_DISPLAY_MODAL_PROPS,
    # DGBLOCKS_PT_Modal_Display,
    # DGBLOCKS_OT_DisplayModal]
    DGBLOCKS_PG_DrawHandler_Instance,
    DGBLOCKS_PG_Debug_Sample_Shaders,
    DGBLOCKS_PG_Stable_Drawing_Props,
    DGBLOCKS_PT_Debug_Drawing_Panel,
]

def register_block():

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_feature_wrapper_classes = [Wrapper_Draw_Handlers], 
        block_RTC_member_enums = Block_RTC_Members, 
        block_logger_enums = Block_Logger_Definitions 
    )

    # Create Scene Property to hold modal configuration
    bpy.types.Scene.onscreen_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Stable_Drawing_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")


def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")
    
    
    # Remove block components from RTC
    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "onscreen_drawing_props"):
        del bpy.types.Scene.onscreen_drawing_props

    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")