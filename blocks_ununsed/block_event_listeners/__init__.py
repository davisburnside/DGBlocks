
import bpy # type: ignore
from bpy.props import BoolProperty # type: ignore

from ..addon_helper_funcs import get_members_and_values_of_propertygroup_with_name_prefix
from ..addon_config import (
        addon_name, 
        addon_title,
        addon_bl_type_prefix,
        should_show_developer_ui_panels,
        Documentation_URLs)

from ...blocks_natively_included import _block_core
from ..blocks_natively_included._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache
from ..blocks_natively_included._block_core.core_helper_uilayouts import ui_box_with_header, uilayout_draw_block_panel_header
from ..blocks_natively_included._block_core.core_helper_functions import register_block_components, unregister_block_components
from ..blocks_natively_included._block_core.core_helper_debug_functions import make_pretty_json_string_from_data
from ..blocks_natively_included._block_core.core_feature_logs import get_logger
from ..blocks_natively_included._block_core.core_block_constants import (
        Core_Block_Loggers)

from . import feature_generic_listener_wrapper

from .block_constants import (
        Enum_Event_Listener_Definitions,
        Block_Logger_Definitions,
        Enum_Runtime_Cache_Keys)

#=================================================================================
# BLOCK DATA - A unique ID & list of Dependencies is required for every Block
#=================================================================================

_BLOCK_ID = "block-event-listener"
_BLOCK_DEPENDENCIES = [_block_core._BLOCK_ID]

#=================================================================================
# CALLBACK HOOK FUNCTIONS 
#=================================================================================

# --------------------------------------------------------------
# Addon init, called after register_block() finishes & bpy.context is fully usable
# --------------------------------------------------------------

def hook_post_register_init(context):
    
    logger = get_logger(Block_Logger_Definitions.LISTENERS)
    feature_generic_listener_wrapper.create_hook_references_for_all_event_listeners(context, logger)
    return True

# --------------------------------------------------------------
# Used in Debugging
# --------------------------------------------------------------

def hook_debug_get_state_data_to_print(context, other_input: str) -> dict:
    
    return {"hASDASDSDi": []}

def hook_debug_uilayout_draw_console_print_settings(context, container):
    
    container.label(text = "dfgdfgfdgdfgd")
    
# =============================================================================
# DATABLOCKS - Attached to Scene
# Stores state info of each listener type
# =============================================================================

class DGBLOCKS_PG_Event_Listener_Props(bpy.types.PropertyGroup):
    
    debug_print_only_active_listeners: bpy.props.BoolProperty(default = False) # type: ignore
    debug_print_last_trigger_time: bpy.props.BoolProperty(default = False) # type: ignore
    debug_print_hooked_blocks: bpy.props.BoolProperty(default = False) # type: ignore
    
    enable_listener_depsgraph_pre: BoolProperty(
        name="Depsgraph Pre",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.DEPSGRAPH_PRE),
    )
    enable_listener_depsgraph_post: BoolProperty(
        name="Depsgraph Post",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.DEPSGRAPH_POST),
    )
    enable_listener_frame_change_pre: BoolProperty(
        name="Frame Change Pre",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.FRAME_CHANGE_PRE),
    )
    enable_listener_frame_change_post: BoolProperty(
        name="Frame Change Post",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.FRAME_CHANGE_POST),
    )
    enable_listener_undo_pre: BoolProperty(
        name="Undo Pre",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.UNDO_PRE),
    )
    enable_listener_undo_post: BoolProperty(
        name="Undo Post",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.UNDO_POST),
    )
    enable_listener_redo_pre: BoolProperty(
        name="Redo Pre",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.REDO_PRE),
    )
    enable_listener_redo_post: BoolProperty(
        name="Redo Post",
        default=True,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.REDO_POST),
    )
    enable_listener_save_pre: BoolProperty(
        name="Save Pre",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.SAVE_PRE),
    )
    enable_listener_save_post: BoolProperty(
        name="Save Post",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.SAVE_POST),
    )
    enable_listener_bake_pre: BoolProperty(
        name="Bake Pre",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.OBJECT_BAKE_PRE),
    )
    enable_listener_bake_post: BoolProperty(
        name="Bake Post",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.OBJECT_BAKE_POST),
    )
    enable_listener_composite_pre: BoolProperty(
        name="Composite Pre",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.COMPOSITE_PRE),
    )
    enable_listener_composite_post: BoolProperty(
        name="Composite Post",
        default=False,
        update=feature_generic_listener_wrapper._factory_property_update_func(Enum_Event_Listener_Definitions.COMPOSITE_POST),
    )

#================================================================
# OPERATORS
#================================================================
    
class DGBLOCKS_OT_Debug_Print_Event_Listener_Wrapper_Cache(bpy.types.Operator):
    bl_idname = "dgblocks.debug_print_event_listener_wrapper_cache"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}

    def execute(self, context):
        
        event_listener_props = context.scene.dgblocks_event_listener_props
        
        all_listener_wrappers = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.EVENT_LISTENER_WRAPPER_CACHE)
        
        data_to_show = {}
        for listener_wrapper in all_listener_wrappers:
            is_active = listener_wrapper.is_registered
            data_label = listener_wrapper.handler_type
            data_content = [f"Active={is_active}"]
            data_to_show[data_label] = data_content
            
        make_pretty_json_string_from_data(data_to_show)
        
        
        return {'FINISHED'}
    
    # def invoke(self, context, event):
    #     # This will show the properties in a popup dialog
    #     return context.window_manager.invoke_props_dialog(self)

#================================================================
# UI - Panel for Modal Display & Shader toggles
#================================================================

class DGBLOCKS_PT_Debug_Event_Handlers(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Debug_Event_Handlers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return should_show_developer_ui_panels and context.scene.dgblocks_core_props.addon_is_active
    
    def draw_header(self, context):
        
        # Determine which Icon to use
        event_handler_props = context.scene.dgblocks_event_listener_props
        listener_control_props_list = get_members_and_values_of_propertygroup_with_name_prefix(event_handler_props, "enable_")
        icon_name = "OUTLINER_OB_LIGHT" if any(listener_control_props_list.values()) else "OUTLINER_DATA_LIGHT"
        uilayout_draw_block_panel_header(context, self.layout, _BLOCK_ID.upper(), Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = icon_name)

    def draw(self, context):
        
        layout = self.layout
        event_listener_props = context.scene.dgblocks_event_listener_props
        
        box =  ui_box_with_header(context, layout, "Active Event Listeners")
        # box.operator("dgblocks.debug_print_event_listener_wrapper_cache")
        
        event_handler_props = context.scene.dgblocks_event_listener_props
        listener_control_props_list = get_members_and_values_of_propertygroup_with_name_prefix(event_handler_props, "enable_")
        grid = box.grid_flow(columns=2, row_major = True)
        for prop_name in listener_control_props_list:
            grid.prop(event_handler_props, prop_name)
        
#================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Event_Listener_Props,
    DGBLOCKS_OT_Debug_Print_Event_Listener_Wrapper_Cache,
    DGBLOCKS_PT_Debug_Event_Handlers]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(_block_classes_to_register, Block_Logger_Definitions)
    
    # Create Scene Property to hold listener state info
    bpy.types.Scene.dgblocks_event_listener_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Event_Listener_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    unregister_block_components(_block_classes_to_register)
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_event_listener_props"):
        del bpy.types.Scene.dgblocks_event_listener_props
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")