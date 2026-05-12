import os
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...my_addon_config import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix
from ...addon_helpers.generic_helpers import get_self_block_module, clear_console
from ...addon_helpers.data_structures import Enum_Sync_Events

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import block_core
from ..block_core.core_features.loggers import Core_Block_Loggers, get_logger
from ..block_core.core_features.hooks import Wrapper_Hooks
from ..block_core.core_features.control_plane import Wrapper_Control_Plane
from ..block_core.core_features.runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Loggers, Block_Runtime_Cache_Member_Definitions

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-pip-manager" # Defined in constants, To Prevent circular imports. Other Blocks can assign directly
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = ["block-core", "block-timers"] 

def hook_core_event_undo():
    print("undo hook run")

# ==============================================================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
# ==============================================================================================================================

class DGBLOCKS_PT_Pip_Manager_Debug_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"DGBLOCKS_PT_Pip_Manager_Debug_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")

    def draw(self, context):
        self.layout.label(text = "test")

# ==============================================================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PT_Pip_Manager_Debug_Panel,
]

def register_block(event: Enum_Sync_Events):

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Control_Plane) # returns this __init__.py file
    Wrapper_Control_Plane.create_instance(
        event,
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_logger_enums = Block_Loggers,
        block_RTC_member_enums = Block_Runtime_Cache_Member_Definitions,
    )

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Control_Plane.destroy_instance(event, block_id = _BLOCK_ID)
    
    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")
