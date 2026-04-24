import os
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helper_funcs import get_self_block_module, clear_console
from ...my_addon_config import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...blocks_natively_included import _block_core
from ...blocks_natively_included._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from ...blocks_natively_included._block_core.core_features.feature_hooks import Wrapper_Hooks
from ...blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from ...blocks_natively_included._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from ...blocks_natively_included._block_core.core_helpers.helper_uilayouts import uilayout_draw_block_panel_header

from ...blocks_natively_included.block_stable_modal.test1 import Wrapper_Modals_Manager

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Logger_Definitions, Block_RTC_Members
from .helper_unittests import run_operator_in_headless_blender, _sample_unittest, launch_headless_operator

#=================================================================================
# BLOCK DEFINITION
#=================================================================================

_BLOCK_ID = "block-flatypus-assembly-mode" 
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core",
    "block-stable-modal",
] 

#=================================================================================
# vars
#=================================================================================

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

#=================================================================================
# DOWNSTREAM HOOKS
#=================================================================================

def hook_modal_key_or_mouse_event(context: bpy.types.Context, event: bpy.types.Event, modal_instance: any):
    pass
    # print("downstream mousekey")
    # print(modal_instance, event)

def hook_modal_timer_event(context: bpy.types.Context, event: bpy.types.Event, modal_instance: any):
    pass
    print("downstream timer")
    # print(modal_instance, event)


#=================================================================================
# Operators
#=================================================================================

class DGBLOCKS_OT_Toggle_Assembly_Mode(bpy.types.Operator):
    bl_idname = "dgblocks.toggle_assembly_mode"
    bl_label = "Toggle Assmbly Mode"
    bl_options = {"REGISTER"}
    
    # This operator can always be executed, even when add
    def execute(self, context):

        

        modal_op_for_viewport_display = Wrapper_Modals_Manager.create_instance(**_default_modal_options_for_3dview_display)
        modal_op_for_keymouse_input = Wrapper_Modals_Manager.create_instance(**_default_modal_options_for_keymouse_input)

        return {"FINISHED"}

#=================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
#=================================================================================

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

        uilayout_draw_block_panel_header(context, self.layout, "FLT-mode-debug", Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")

    def draw(self, context):
        
        layout = self.layout
        layout.operator("dgblocks.toggle_assembly_mode", text = "run 'em")

#=================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#=================================================================================

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
