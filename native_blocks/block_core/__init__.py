import os
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import force_reload_all_scripts, get_self_block_module, force_redraw_ui
from ...addon_helpers.data_structures import Enum_Sync_Events, Global_Addon_State, RTC_FWC_Data_Mirror_List_Reference
from ...my_addon_config import Documentation_URLs, should_show_developer_ui_panels, addon_name, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Core block imports
# --------------------------------------------------------------
from .core_helpers.constants import Core_Block_Hook_Sources, Core_Block_Loggers, Core_Runtime_Cache_Members, _BLOCK_ID as core_block_id
from .core_features.feature_logs import DGBLOCKS_PG_Logger_Instance, DGBLOCKS_UL_Loggers, Wrapper_Loggers, get_logger
from .core_features.feature_block_manager import DGBLOCKS_PG_Debug_Block_Reference, DGBLOCKS_UL_Blocks, Wrapper_Block_Management
from .core_features.feature_hooks import DGBLOCKS_PG_Hook_Reference, Wrapper_Hooks, DGBLOCKS_UL_Hooks
from .core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .core_features.feature_tracked_datablock_types import Wrapper_Tracked_Datablock_Types
from .core_helpers.helper_uilayouts import uilayout_draw_core_block_settings

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_hook_subs = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = core_block_id # Defined in constants, To Prevent circular imports. Other Blocks can assign directly
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [] # Core block depends on no others

# ==============================================================================================================================
# BLOCK PROPERTIES
# ==============================================================================================================================

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
    debug_log_all_RTC_BL_sync_actions: bpy.props.BoolProperty(default = False)# type: ignore

    # Empties all CollectionProps created by this addon eveyr startup
    debug_clear_BL_data_on_startup: bpy.props.BoolProperty(default = False)# type: ignore

    # --------------------------------------------------------------
    # Persistent, undo/redo-enabled Scene data for each feature-wrapper's mirrored  RTC data
    # More info for structure/metadata is found inside each DGBLOCKS_* class
    # --------------------------------------------------------------
    managed_blocks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Debug_Block_Reference) # type: ignore
    managed_blocks_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_hooks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Hook_Reference)  # type: ignore
    managed_hooks_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_loggers_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_loggers: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Logger_Instance) # type: ignore

# ==============================================================================================================================
# OPERATORS - used by all blocks
# ==============================================================================================================================

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
    bl_idname = "dgblocks.debug_force_reload_scripts"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    web_documentation_url: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):
        
        force_reload_all_scripts(context)
            
        return {"FINISHED"}

class DGBLOCKS_OT_Force_Reload_Refresh_UI(bpy.types.Operator):
    bl_idname = "dgblocks.debug_force_refresh_ui"
    bl_label = "Refresh UI"
    bl_options = {"REGISTER"}
    
    def execute(self, context):
        
        force_redraw_ui(context)
        return {"FINISHED"}
   
class DGBLOCKS_OT_Debug_Clear_And_Restore_Caches(bpy.types.Operator):
    bl_idname = "dgblocks.debug_clear_and_restore_caches"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    action: bpy.props.StringProperty() # type: ignore 
    target: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):

        # Clearing these would prevent restore-action
        rtc_members_to_skip = ["REGISTRY_ALL_BLOCKS", "REGISTRY_ALL_FWCS"]
        
        # Clear or restore the RTC, Blender data is unaffected
        if self.target == "RTC":

            # Clearing data does not use destroy_instance function. It directly updates the RTC's _cache. This should not be done in a production setting
            if self.action == "CLEAR":
                for cache_key, cache_data in Wrapper_Runtime_Cache._cache.items():
                    if cache_key in rtc_members_to_skip:
                        continue
                    if isinstance(cache_data, list):
                        print(f"Clearing RTC list {cache_key}")
                        Wrapper_Runtime_Cache.set_cache(cache_key, [])

            # Use Block-mgmt FWC's native restoration feature
            elif self.action == "RESTORE":
                Wrapper_Block_Management.update_all_FWC_RTC_caches_to_match_BL_data(event_type = "debug-restore") 

        # Clear or restore Blender data, RTC is unaffected
        if self.target == "BL":
            if self.action == "CLEAR":
                for cache_key, cache_data in Wrapper_Runtime_Cache._cache.items():
                    if cache_key in rtc_members_to_skip:
                        continue
                    if isinstance(cache_data, list):
                        print(f"Clearing RTC list {cache_key}")
                        Wrapper_Runtime_Cache.set_cache(cache_key, [])
            elif self.action == "RESTORE":
                Wrapper_Block_Management.update_all_FWC_RTC_caches_to_match_BL_data(event_type = "debug-restore") 

        return {"FINISHED"}

# ==============================================================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
# ==============================================================================================================================

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
        ui_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "FILE_3D")

    def draw(self, context):
        
        uilayout_draw_core_block_settings(context, self.layout)

# ==============================================================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Debug_Block_Reference,
    DGBLOCKS_PG_Logger_Instance,
    DGBLOCKS_PG_Hook_Reference,
    DGBLOCKS_PG_Core_Props,
    DGBLOCKS_OT_Open_Help_Page,
    DGBLOCKS_OT_Copy_To_Clipboard,
    DGBLOCKS_OT_Force_Reload_Refresh_UI,
    DGBLOCKS_OT_Force_Reload_Scripts,
    DGBLOCKS_OT_Debug_Clear_And_Restore_Caches,
    DGBLOCKS_PT_Core_Block_Panel,
    DGBLOCKS_UL_Blocks,
    DGBLOCKS_UL_Hooks,
    DGBLOCKS_UL_Loggers,
    DGBLOCKS_UP_Core_Preferences
]

# All core-block feature wrapper
_feature_wrapper_classes_to_register = [
    Wrapper_Block_Management,
    Wrapper_Runtime_Cache,
    Wrapper_Loggers,
    Wrapper_Hooks,
    Wrapper_Tracked_Datablock_Types,  
]

def register_block(event: Enum_Sync_Events):

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    initial_state = Global_Addon_State()
    # Wrapper_Block_Management.set

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        event,
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_feature_wrapper_classes = _feature_wrapper_classes_to_register, 
        block_hook_source_enums = Core_Block_Hook_Sources,
        block_RTC_member_enums = Core_Runtime_Cache_Members,
        block_logger_enums = Core_Block_Loggers 
    )
    
    # Add block-core Properties to Scene
    bpy.types.Scene.dgblocks_core_props = bpy.props.PointerProperty(type = DGBLOCKS_PG_Core_Props)

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(event, block_id = _BLOCK_ID)
    
    # Delete block-core Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_core_props"):
        del bpy.types.Scene.dgblocks_core_props

    # For core-block, delay destruction of RTC, Loggers, & hooks until the end of addon-level unregister()
    # Other blocks will likely want to populate block_runtime_cache_members, block_hooks, & block_loggers

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")

