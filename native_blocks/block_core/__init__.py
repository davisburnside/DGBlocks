import os
import sys

import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration

# Core block imports
from .core_helpers.constants import Core_Block_Hook_Sources, Core_Block_Loggers, Core_Data_Mirrors, Core_Runtime_Cache_Members, _BLOCK_ID as core_block_id
from .core_helpers.ops import DGBLOCKS_OT_Copy_To_Clipboard, DGBLOCKS_OT_Debug_Clear_And_Restore_Caches, DGBLOCKS_OT_Force_Reload_Refresh_UI, DGBLOCKS_OT_Force_Reload_Scripts, DGBLOCKS_OT_Open_Help_Page
from .core_helpers.props import DGBLOCKS_PG_Core_Props
from .core_helpers.debugging import debug_extract_core_block_data_to_print, debug_ui_draw_core_block_printing_options
from .core_helpers.ui import DGBLOCKS_PT_Core_Block_Panel
from .core_features.loggers.feature_wrapper import Wrapper_Loggers
from .core_features.loggers.data_structures import DGBLOCKS_PG_Logger_Instance
from .core_features.loggers.ui import _uilayout_draw_logger_settings
from .core_features.control_plane.data_structures import DGBLOCKS_PG_Block_Record
from .core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
from .core_features.control_plane.ui import _uilayout_draw_block_manager_settings
from .core_features.hooks.data_structures import DGBLOCKS_PG_Hook_Reference
from .core_features.hooks.feature_wrapper import Wrapper_Hooks
from .core_features.hooks.ui import _uilayout_draw_hooks_settings
from .core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .core_helpers.ui import DGBLOCKS_UL_Shared_Debug_List

# This hook has an inverted "downstream" dependency direction, but it still works.
# In other words, block-console-debug-print depends on block-core, but can still call hooks in block-core. 
def hook_debug_get_state_data_to_print(other_input: str):
    return debug_extract_core_block_data_to_print(bpy.context, other_input)

def hook_debug_uilayout_draw_console_print_settings(ui_container: bpy.types.UILayout):
    debug_ui_draw_core_block_printing_options(bpy.context, ui_container, core_block_id)

# BLOCK DEFINITION
# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Block_Record,
    DGBLOCKS_PG_Logger_Instance,
    DGBLOCKS_PG_Hook_Reference,
    DGBLOCKS_PG_Core_Props,
    DGBLOCKS_OT_Open_Help_Page,
    DGBLOCKS_OT_Copy_To_Clipboard,
    DGBLOCKS_OT_Force_Reload_Refresh_UI,
    DGBLOCKS_OT_Force_Reload_Scripts,
    DGBLOCKS_OT_Debug_Clear_And_Restore_Caches,
    DGBLOCKS_PT_Core_Block_Panel,
    DGBLOCKS_UL_Shared_Debug_List,
]

# All core-block feature wrapper
_feature_wrapper_classes_to_register = [
    Wrapper_Control_Plane,
    Wrapper_Runtime_Cache,
    Wrapper_Loggers,
    Wrapper_Hooks,
]

# REQUIRED 
_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__], # this __init__.py file
    block_id = core_block_id, # unique block id
    block_dependencies = [], # ids of blocks that this one depends on
    block_bpy_classes = _block_classes_to_register, # Blender-registerable classes
    block_feature_wrapper_classes = _feature_wrapper_classes_to_register,
    block_loggers = Core_Block_Loggers,
    block_hook_sources = Core_Block_Hook_Sources,
    block_RTC_members = Core_Runtime_Cache_Members,
    block_data_mirrors = Core_Data_Mirrors,
)

def register_block_props():
    bpy.types.Scene.dgblocks_core_props = bpy.props.PointerProperty(type = DGBLOCKS_PG_Core_Props)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_core_props"):
        del bpy.types.Scene.dgblocks_core_props
