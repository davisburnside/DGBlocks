

import threading
import bpy # type: ignore

from ..addon_config import (
        addon_name, 
        addon_title,
        addon_bl_type_prefix,
        should_show_developer_ui_panels,
        Documentation_URLs)

from ...blocks_natively_included import _block_core
from ..blocks_natively_included._block_core.core_feature_runtime_cache import delete_from_addon_runtime_cache, Wrapper_Runtime_Cache.set_cache
from ..blocks_natively_included._block_core.core_helper_uilayouts import uilayout_draw_block_panel_header
from ..blocks_natively_included._block_core.core_helper_functions import register_block_components, unregister_block_components
from ..blocks_natively_included._block_core.core_feature_logs import get_logger
from ..blocks_natively_included._block_core.core_block_constants import (Core_Block_Loggers)

from ...blocks_natively_included import block_event_listeners
from ..block_event_listeners.block_constants import Block_Logger_Definitions as event_listener_loggers

from .feature_datablock_import import feature_wrapper_datablock_import
from .feature_library_import import library_installation_wrapper
from . import feature_stable_datablock_id
from .helper_uilayout_functions import uilayout_draw_main_panel
from .block_config import my_stable_id_target_list
from .block_constants import (
        Block_Runtime_Cache_Member_Definitions,
        Block_Logger_Definitions)

#================================================================
# BLOCK DATA - A unique ID & list of Dependencies is required for every Block
# =============================================================================

_BLOCK_ID = "block-data-enforcement"
_BLOCK_DEPENDENCIES = [_block_core._BLOCK_ID, block_event_listeners._BLOCK_ID]

#================================================================
# INIT EVENTS - Called after register_block() finishes & bpy.context is fully usable
# This function is automatically called by event_listeners
#================================================================

def hook_post_register_init(context):
    
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    feature_stable_datablock_id.initialize_permanent_id_manager()
    
    return True

#================================================================

#================================================================

def block_api_depsgraph_update_post(context, depsraph):
    
    logger = get_logger(event_listener_loggers.LISTENERS)
    logger.debug(f"Starting block_api_depsgraph_post_callback for '{_BLOCK_ID}'")
    
    # feature_stable_datablock_id.initialize_permanent_id_manager()
        
    logger.debug(f"Finished block_api_depsgraph_post_callback for '{_BLOCK_ID}'")
    return True

# =============================================================================
# DATABLOCKS - Attached to Scene & Object
# Stores state info of each listener type
# =============================================================================

class DGBLOCKS_PG_Scene_Data_Enforcement_Props(bpy.types.PropertyGroup):
    enforce_stable_datablock_ids = bpy.props.BoolProperty(name="Enable Stable ID Enforcement", default=False) # type: ignore
    enforce_object_modifier_stack = bpy.props.BoolProperty(name="Enable Object Modifier Stack Enforcement", default=False) # type: ignore

class DGBLOCKS_PG_Any_Datablock_Stable_Id_Props(bpy.types.PropertyGroup):
    stable_id: bpy.props.StringProperty(name="Permanent ID", default="") # type: ignore

# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

#================================================================
# UI
#================================================================

class DGBLOCKS_PT_Data_Enforcement_Developer_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Enforcement_Developer_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return should_show_developer_ui_panels and context.scene.dgblocks_core_props.addon_is_active
    
    def draw_header(self, context):
        uilayout_draw_block_panel_header(context, self.layout, _BLOCK_ID.upper(), Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "DOCUMENTS")
    
    def draw(self, context):
        uilayout_draw_main_panel(context, self.layout)

#================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
        DGBLOCKS_PG_Scene_Data_Enforcement_Props,
        DGBLOCKS_PG_Any_Datablock_Stable_Id_Props,
        DGBLOCKS_PT_Data_Enforcement_Developer_Panel,
        library_installation_wrapper.DGBLOCKS_OT_Library_Manager,
        library_installation_wrapper.DGBLOCKS_OT_Cancel_Library_Operation,
        library_installation_wrapper.DGBLOCKS_OT_Show_Library_Result,
        library_installation_wrapper.DGBLOCKS_OT_Open_Folder]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(classes = _block_classes_to_register, loggers = Block_Logger_Definitions)
    
    bpy.types.Scene.dgblocks_data_enforcement_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Scene_Data_Enforcement_Props) 
    
    # Create Scene Property to hold listener state info
    # Attach the PointerProperty to every target DataBlock type
    for rna_type in my_stable_id_target_list:
        rna_type.dgblocks_object_stable_id_props = bpy.props.PointerProperty(
            type=DGBLOCKS_PG_Any_Datablock_Stable_Id_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    unregister_block_components(_block_classes_to_register)
    
    # Remove the properties from the RNA types
    for rna_type in my_stable_id_target_list:
        if hasattr(rna_type, "dgblocks_object_stable_id_props"):
            del rna_type.dgblocks_object_stable_id_props
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_object_stable_id_props"):
        del bpy.types.Scene.dgblocks_object_stable_id_props
    
    feature_stable_datablock_id.destroy_permanent_id_manager()
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")