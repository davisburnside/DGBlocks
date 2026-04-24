import os
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_data_structures import DGBLOCKS_PG_General_Purpose_Tag
from ...addon_helper_funcs import force_reload_all_scripts, get_self_block_module
from ...my_addon_config import Documentation_URLs, should_show_developer_ui_panels, default_disabled_icon, addon_name, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Core block imports
# --------------------------------------------------------------
from .core_helpers.constants import Core_Block_Hook_Sources, Core_Block_Loggers, Core_Runtime_Cache_Members, _BLOCK_ID as core_block_id
from .core_features.feature_logs import DGBLOCKS_PG_Logger_Instance, Wrapper_Loggers, get_logger
from .core_features.feature_block_manager import DGBLOCKS_PG_Debug_Block_Reference, DGBLOCKS_UL_Blocks, Wrapper_Block_Management
from .core_features.feature_hooks import DGBLOCKS_PG_Hook_Reference, Wrapper_Hooks, DGBLOCKS_UL_Hooks
from .core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .core_helpers.helper_uilayouts import uilayout_draw_block_panel_header
from .core_helpers.helper_functions import uilayout_draw_core_block_settings

#=================================================================================
# BLOCK DEFINITION
#=================================================================================

_BLOCK_ID = core_block_id # Defined in constants, To Prevent circular imports. Other Blocks can assign directly
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [] # Core block depends on no others

#=================================================================================
# BLENDER DATA FOR BLOCK
#=================================================================================

class DGBLOCKS_PG_Core_Props(bpy.types.PropertyGroup):
    
    # The "lights-off switch". When false, all addon features should be disabled. The only available action should be to toggle this value
    addon_is_active: bpy.props.BoolProperty(default = False, name = "Addon is Enabled?") # type: ignore
    
    # General settings
    documentation_weblinks_enabled: bpy.props.BoolProperty(default = True, name = "Enable [ ? ] Webpage Links") # type: ignore  
    
    # Enables extra UI options for debugging. Most properties & functions that begin with "debug_" are not used when this value is false
    debug_mode_enabled: bpy.props.BoolProperty(default = False, name = "Is in Debug Mode?") # type: ignore
    
    # When true, all create/edit/move/remove actions are console printed for:
    # - update_dataclasses_to_match_collectionprop
    # - update_collectionprop_to_match_dataclasses
    debug_log_all_RTC_BL_sync_actions: bpy.props.BoolProperty()# type: ignore

    # --------------------------------------------------------------
    # Persistent, undo/redo-enabled Scene data for each feature-wrapper's mirrored  RTC data
    # More info for structure/metadata is found inside each DGBLOCKS_* class
    # --------------------------------------------------------------
    managed_blocks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Debug_Block_Reference) # type: ignore
    managed_blocks_selected_idx: bpy.props.IntProperty()  # type: ignore
    scene_RTC_mirror_for_loggers: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Logger_Instance) # type: ignore
    managed_hooks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Hook_Reference)  # type: ignore
    managed_hooks_selected_idx: bpy.props.IntProperty()  # type: ignore

#=================================================================================
# OPERATORS - used by all blocks
#=================================================================================

class DGBLOCKS_OT_Open_Help_Page(bpy.types.Operator):
    bl_idname = "dgblocks.open_help_page"
    bl_label = "Learn more"
    # bl_description = "Opens a webpage that describes this feature"
    bl_options = {"REGISTER"}
    
    web_documentation_url: bpy.props.StringProperty() # type: ignore 
    
    @classmethod
    def description(cls, context, properties):
        print(cls)
        print(dir(properties))
        return properties.web_documentation_url

    def execute(self, context):
        
        import webbrowser
        webbrowser.open(self.web_documentation_url)
        return {"FINISHED"}

class DGBLOCKS_OT_Copy_To_Clipboard(bpy.types.Operator):
    bl_idname = "dgblocks.copy_to_clipboard"
    bl_label = "Copy"
    bl_description = "Copy to clipboard"

    text: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({'INFO'}, "Copied to clipboard")
        return {'FINISHED'}

class DGBLOCKS_OT_Force_Reload_Scripts(bpy.types.Operator):
    bl_idname = "dgblocks.debug_force_reload_scipts"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    web_documentation_url: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):
        
        force_reload_all_scripts(context)
            
        return {"FINISHED"}

#=================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
#=================================================================================

class DGBLOCKS_UP_Core_Preferences(bpy.types.AddonPreferences):
    bl_idname = addon_name 

    addon_saved_data_folder: bpy.props.StringProperty(
            default = os.path.expanduser(f"~/.blender_dgblocks_data/"),
            description="Folder where Python libraries will be installed",
            subtype='DIR_PATH') # type: ignore  
    
    # profiles: bpy.props.CollectionProperty(type=test_feature_prefs_profiles.DGBLOCKS_PG_ProfileStateItem) # type: ignore  
    # profiles_active_index: bpy.props.IntProperty(default=0)  # type: ignore  – required by DGBLOCKS_UL_Profiles

    def draw(self, context):
        
        layout = self.layout
        box = layout.box()
        box.label(text = "Data Home for Addon")
        box.prop(self, "addon_saved_data_folder", text="")

class DGBLOCKS_PT_Core_Block_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_General_Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return should_show_developer_ui_panels # The toggle to enable/disable the addon is in core-block dev panel
    
    def draw_header(self, context):
        addon_is_active = context.scene.dgblocks_core_props.addon_is_active
        header_str = _BLOCK_ID.upper() if addon_is_active else f"{_BLOCK_ID.upper()} ( Disabled )"
        icon_name = "FILE_3D" if addon_is_active else default_disabled_icon
        uilayout_draw_block_panel_header(context, self.layout, header_str, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name=icon_name)

    def draw(self, context):
        
        uilayout_draw_core_block_settings(context, self.layout)

#=================================================================================
# DOWNSTREAM HOOKS
#=================================================================================

# def hook_debug_uilayout_draw_console_print_settings(context, container):
    
#     container.label(text = "asdasad")

#=================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#=================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_General_Purpose_Tag,
    DGBLOCKS_PG_Debug_Block_Reference,
    DGBLOCKS_PG_Logger_Instance,
    DGBLOCKS_PG_Hook_Reference,
    DGBLOCKS_PG_Core_Props,
    DGBLOCKS_OT_Open_Help_Page,
    DGBLOCKS_OT_Copy_To_Clipboard,
    DGBLOCKS_OT_Force_Reload_Scripts,
    DGBLOCKS_PT_Core_Block_Panel,
    DGBLOCKS_UL_Blocks,
    DGBLOCKS_UL_Hooks,
    DGBLOCKS_UP_Core_Preferences
]

# All core-block feature wrapper
_feature_wrapper_classes_to_register = [
    Wrapper_Block_Management,
    Wrapper_Runtime_Cache,
    Wrapper_Loggers,
    Wrapper_Hooks,
]

def register_block():

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_feature_wrapper_classes = _feature_wrapper_classes_to_register, 
        block_hook_source_enums = Core_Block_Hook_Sources,
        block_RTC_member_enums = Core_Runtime_Cache_Members, 
        block_logger_enums = Core_Block_Loggers 
    )
    
    # Add block-core Properties to Scene
    bpy.types.Scene.dgblocks_core_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Core_Props)

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    # Delete block-core Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_core_props"):
        del bpy.types.Scene.dgblocks_core_props

    # For core-block, delay destruction of RTC, Loggers, & hooks until the end of addon-level unregister()
    # Other blocks will likely want to populate block_runtime_cache_members, block_hooks, & block_loggers

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")



def func_t1():

    print("sdlfhasfuksdhfuklasfhsuadklfhdukhsaufs@###########3\n\n\n\n sdfjsdhfj")
    return {"adasdsd" : "4wersdf"}