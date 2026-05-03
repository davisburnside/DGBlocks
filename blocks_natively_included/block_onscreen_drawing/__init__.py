

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
from .constants import Block_RTC_Members, Block_Logger_Definitions, Block_Hook_Sources
from .feature_draw_handler_manager import Wrapper_Draw_Handlers


#=================================================================================
# BLOCK DEFINITION
#=================================================================================

_BLOCK_ID = "block-onscreen-drawing"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core"
]

#=================================================================================
# UI - Draw debugging panel
#=================================================================================

class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    def draw_header(self, context):
        uilayout_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "RESTRICT_VIEW_ON")
        
    def draw(self, context):

        layout = self.layout
        all_rtc_draw_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        for draw_handler_instance in all_rtc_draw_handlers.values():
            name = draw_handler_instance.draw_phase_name
            is_enabled = draw_handler_instance._generated_handle is not None
            row = layout.row(align=True)
            row.label(text = name)
            row.label(text = str(is_enabled))

#=================================================================================
# REGISTRATION EVENTS
#=================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [    
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
        block_logger_enums = Block_Logger_Definitions,
        block_hook_source_enums = Block_Hook_Sources,
    )

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")
    
    # Remove block components from RTC
    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")